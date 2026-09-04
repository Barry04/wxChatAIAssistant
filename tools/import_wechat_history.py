"""Resumable full WeChat history importer.

The importer intentionally stores per-session completion state so a slow or
broken session cannot discard progress made by earlier sessions.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow direct execution from the repository root:
# `.venv\Scripts\python.exe tools\import_wechat_history.py`.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.self_skill import distill_self_skill
from app.services import import_raw_messages, import_records
from app.storage import (
    WECHAT_COVERAGE_FILE,
    ensure_storage,
    read_json,
    write_json,
)
from app.wechat_cli_bridge import (
    WeChatCliError,
    get_full_timeline,
    list_sessions,
    timeline_participant_count,
    timeline_to_raw_messages,
    timeline_to_records,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_sessions() -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = list_sessions(500, offset=offset)
        sessions.extend(page)
        if len(page) < 500:
            return sessions
        offset += len(page)


def _session_results(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = report.get("session_results") or {}
    normalized = {
        str(username): dict(result)
        for username, result in results.items()
        if username
    }
    for item in report.get("failed_sessions") or []:
        username = str(item.get("username") or "").strip()
        if username and username not in normalized:
            normalized[username] = {
                "username": username,
                "display_name": item.get("display_name") or username,
                "chat_type": item.get("chat_type") or "unknown",
                "status": "failed",
                "error": item.get("reason") or "读取失败",
            }
    for item in report.get("readable_session_ids") or []:
        username = str(
            item.get("username") if isinstance(item, dict) else item
        ).strip()
        if username and username not in normalized:
            normalized[username] = {
                "username": username,
                "status": "legacy_pending",
                "note": "历史报告只有已写入原始文件的记录，尚未验证 has_more=false",
            }
    return normalized


def _write_progress(
    report: dict[str, Any],
    sessions: list[dict[str, Any]],
    results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    failed = [
        {
            "username": username,
            "display_name": result.get("display_name") or username,
            "chat_type": result.get("chat_type") or "unknown",
            "reason": result.get("error") or "读取失败",
        }
        for username, result in results.items()
        if result.get("status") == "failed"
    ]
    verified_readable = [
        username
        for username, result in results.items()
        if result.get("status") in {"complete", "truncated"}
    ]
    legacy_readable = [
        username
        for username, result in results.items()
        if result.get("status") == "legacy_pending"
    ]
    ignored = [
        username
        for username, result in results.items()
        if result.get("status") == "ignored"
    ]
    complete = [
        username
        for username, result in results.items()
        if result.get("status") == "complete" and not result.get("has_more")
    ]
    pending = [
        str(session.get("username"))
        for session in sessions
        if str(session.get("username")) not in results
        or results[str(session.get("username"))].get("status")
        not in {"complete", "failed", "ignored"}
    ]
    next_report = {
        **report,
        "generated_at": _utc_now(),
        "total_sessions": len(sessions),
        "readable_sessions": len(verified_readable) + len(legacy_readable),
        "readable_session_ids": sorted(verified_readable + legacy_readable),
        "verified_readable_sessions": len(verified_readable),
        "complete_sessions": len(complete),
        "complete_session_ids": sorted(complete),
        "pending_sessions": len(pending),
        "ignored_sessions": len(ignored),
        "ignored_session_ids": sorted(ignored),
        "failed_sessions": sorted(
            failed,
            key=lambda item: (item["display_name"], item["username"]),
        ),
        "failed_count": len(failed),
        "session_results": results,
        "verification": {
            "timeline": (
                "每个成功会话均记录 timeline query.has_more；"
                "complete 表示 has_more=false"
            ),
            "history_agent": "completed turns are deduplicated in data/messages.jsonl",
            "context": "not used",
            "search": "not used",
        },
    }
    write_json(WECHAT_COVERAGE_FILE, next_report)
    return next_report


def _read_one_session(
    session: dict[str, Any],
    max_messages: int,
) -> dict[str, Any]:
    username = str(session.get("username") or "").strip()
    try:
        return {
            "session": session,
            "timeline": get_full_timeline(
                username,
                max_messages=max_messages,
            ),
        }
    except WeChatCliError as exc:
        return {"session": session, "error": str(exc)}


def run(
    *,
    start: int = 0,
    limit: int = 20,
    max_messages: int = 200000,
    retry_failed: bool = False,
    distill: bool = True,
    workers: int = 1,
) -> dict[str, Any]:
    ensure_storage()
    sessions = _load_sessions()
    report = read_json(WECHAT_COVERAGE_FILE, {})
    results = _session_results(report)
    selected = sessions[start : start + limit] if limit > 0 else sessions[start:]
    processed: list[dict[str, Any]] = []

    to_read: list[dict[str, Any]] = []
    for session in selected:
        username = str(session.get("username") or "").strip()
        if not username:
            continue
        previous = results.get(username) or {}
        if previous.get("status") == "complete" and not previous.get("has_more"):
            processed.append(
                {"username": username, "status": "skipped_complete"}
            )
            continue
        if previous.get("status") == "failed" and not retry_failed:
            processed.append({"username": username, "status": "skipped_failed"})
            continue
        to_read.append(session)

    retrieved: list[dict[str, Any]] = []
    if max(1, workers) == 1:
        retrieved = [
            _read_one_session(session, max_messages)
            for session in to_read
        ]
    else:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as executor:
            futures = {
                executor.submit(
                    _read_one_session,
                    session,
                    max_messages,
                ): session
                for session in to_read
            }
            for future in as_completed(futures):
                retrieved.append(future.result())

    for item in retrieved:
        session = item["session"]
        username = str(session.get("username") or "").strip()
        base = {
            "username": username,
            "display_name": str(session.get("display_name") or username),
            "chat_type": str(session.get("chat_type") or "unknown"),
            "started_at": _utc_now(),
        }
        try:
            if item.get("error"):
                raise WeChatCliError(str(item["error"]))
            timeline = item["timeline"]
            messages = timeline.get("messages", [])
            query = dict(timeline.get("query") or {})
            participant_count = timeline_participant_count(messages)
            chat_type = str(session.get("chat_type") or "private")
            contact_id = f"wechat:{username}"
            raw_imported = import_raw_messages(
                timeline_to_raw_messages(
                    messages,
                    contact_id=contact_id,
                    relationship="friend",
                    talker=username,
                    chat_type=chat_type,
                    display_name=str(session.get("display_name") or username),
                    participant_count=participant_count,
                )
            )
            records = timeline_to_records(
                messages,
                contact_id=contact_id,
                relationship="friend",
                talker=username,
                chat_type=chat_type,
                display_name=str(session.get("display_name") or username),
                participant_count=participant_count,
            )
            records_imported = import_records(records)
            has_more = bool(query.get("has_more"))
            results[username] = {
                **base,
                "status": "truncated" if has_more else "complete",
                "has_more": has_more,
                "messages_read": len(messages),
                "pages_read": int(query.get("pages_read") or 0),
                "raw_imported": raw_imported,
                "records_read": len(records),
                "records_imported": records_imported,
                "finished_at": _utc_now(),
            }
            processed.append(
                {
                    "username": username,
                    "status": results[username]["status"],
                    "messages_read": len(messages),
                    "pages_read": int(query.get("pages_read") or 0),
                    "records_read": len(records),
                }
            )
        except WeChatCliError as exc:
            results[username] = {
                **base,
                "status": "failed",
                "error": str(exc),
                "finished_at": _utc_now(),
            }
            processed.append(
                {"username": username, "status": "failed", "error": str(exc)}
            )
        finally:
            _write_progress(report, sessions, results)
            report = read_json(WECHAT_COVERAGE_FILE, {})

    if distill and any(
        item.get("status") in {"complete", "truncated"}
        for item in results.values()
    ):
        distill_self_skill()
        report = read_json(WECHAT_COVERAGE_FILE, {})
        report["distilled_at"] = _utc_now()
        report["distilled_reply_count"] = int(
            read_json(WECHAT_COVERAGE_FILE, {}).get("distilled_reply_count") or 0
        )
        write_json(WECHAT_COVERAGE_FILE, report)

    return {
        "start": start,
        "limit": limit,
        "selected": len(selected),
        "processed": processed,
        "coverage": read_json(WECHAT_COVERAGE_FILE, {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-messages", type=int, default=200000)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--no-distill", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    result = run(
        start=max(0, args.start),
        limit=args.limit,
        max_messages=max(20, args.max_messages),
        retry_failed=args.retry_failed,
        distill=not args.no_distill,
        workers=max(1, min(args.workers, 4)),
    )
    print(
        json.dumps(
            {
                "selected": result["selected"],
                "processed": result["processed"],
                "coverage": {
                    key: result["coverage"].get(key)
                    for key in (
                        "total_sessions",
                        "readable_sessions",
                        "complete_sessions",
                        "pending_sessions",
                        "failed_count",
                    )
                },
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
