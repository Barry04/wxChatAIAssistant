"""微信本地读取、覆盖率报告与历史导入路由。"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..chat_analysis import analyze_chat_records
from ..models import WeChatContactImportRequest, WeChatHistoryImportRequest
from ..self_skill import distill_self_skill
from ..services import import_raw_messages, import_records
from ..storage import (
    MESSAGES_FILE,
    SELF_SKILL_META_FILE,
    WECHAT_COVERAGE_FILE,
    WECHAT_RAW_MESSAGES_FILE,
    read_json,
    read_jsonl,
    write_json,
)
from ..wechat_bridge import get_wechat_status, inspect_visible_controls
from ..wechat_cli_bridge import (
    WeChatCliError,
    get_full_timeline,
    get_reader_status,
    list_sessions,
    recent_self_history,
    timeline_participant_count,
    timeline_to_raw_messages,
    timeline_to_records,
)
from .contacts import find_contact

router = APIRouter()


def _update_wechat_coverage(
    batch: dict,
    imported_sessions: list[dict],
) -> dict:
    """Merge one paginated import result into the durable coverage report."""
    report = read_json(WECHAT_COVERAGE_FILE, {})
    failed_by_username = {
        str(item.get("username")): item
        for item in (report.get("failed_sessions") or [])
        if item.get("username")
    }
    readable_by_username = {
        str(item.get("username") if isinstance(item, dict) else item): item
        for item in (report.get("readable_session_ids") or [])
        if item and str(item.get("username") if isinstance(item, dict) else item).strip()
    }
    # Older reports stored only the count. Reconstruct the IDs from raw
    # messages before merging a new single-session batch.
    if not readable_by_username and int(report.get("readable_sessions") or 0):
        readable_by_username = {
            talker: talker
            for talker in {
                str(row.get("wechat_talker") or "").strip()
                for row in read_jsonl(WECHAT_RAW_MESSAGES_FILE)
                if str(row.get("wechat_talker") or "").strip()
            }
        }
    for item in imported_sessions:
        username = str(item.get("username") or "").strip()
        if not username:
            continue
        if item.get("error"):
            failed_by_username[username] = {
                "username": username,
                "display_name": item.get("display_name") or username,
                "chat_type": item.get("chat_type") or "unknown",
                "reason": str(item.get("error")),
            }
            readable_by_username.pop(username, None)
        else:
            readable_by_username[username] = username
            failed_by_username.pop(username, None)

    total_sessions = int(
        batch.get("total_sessions")
        or report.get("total_sessions")
        or len(readable_by_username) + len(failed_by_username)
    )
    failed_sessions = sorted(
        failed_by_username.values(),
        key=lambda item: (
            str(item.get("display_name") or ""),
            str(item.get("username") or ""),
        ),
    )
    next_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_sessions": total_sessions,
        "readable_sessions": len(readable_by_username),
        "readable_session_ids": sorted(readable_by_username),
        "failed_sessions": failed_sessions,
        "failed_count": len(failed_sessions),
        "verification": {
            "timeline": "readable sessions present in raw file",
            "history_agent": "readable sessions present in completed-turn file",
            "context": "not used",
            "search": "not used",
        },
        "policy": (
            "仅将成功读取的会话写入原始消息；缺失 Msg_* 表的会话保留在失败列表，"
            "不计入蒸馏样本"
        ),
    }
    write_json(WECHAT_COVERAGE_FILE, next_report)
    return next_report


@router.get("/api/wechat/analysis")
def wechat_analysis() -> dict:
    return analyze_chat_records(read_jsonl(MESSAGES_FILE))


@router.get("/api/wechat/coverage")
def wechat_coverage() -> dict:
    report = read_json(WECHAT_COVERAGE_FILE, {})
    policy = (
        "仅将成功读取的会话写入原始消息；缺失 Msg_* 表的会话保留在失败列表，"
        "不计入蒸馏样本。"
    )
    if report.get("policy") != policy:
        report["policy"] = policy
        write_json(WECHAT_COVERAGE_FILE, report)
    total_sessions = int(report.get("total_sessions") or 0)
    readable_sessions = int(report.get("readable_sessions") or 0)
    failed_sessions = report.get("failed_sessions") or []
    raw_messages = read_jsonl(WECHAT_RAW_MESSAGES_FILE)
    completed_turns = read_jsonl(MESSAGES_FILE)
    distilled = read_json(SELF_SKILL_META_FILE, {})
    return {
        **report,
        "total_sessions": total_sessions,
        "readable_sessions": readable_sessions,
        "failed_sessions": failed_sessions,
        "failed_count": len(failed_sessions),
        "session_coverage_percent": round(
            readable_sessions / total_sessions * 100, 1
        )
        if total_sessions
        else 0,
        "raw_message_count": len(raw_messages),
        "completed_turn_count": len(completed_turns),
        "distilled_reply_count": int(distilled.get("sample_count") or 0),
    }


@router.get("/api/wechat/status")
def wechat_status() -> dict:
    return {**get_wechat_status(), "reader": get_reader_status()}


@router.get("/api/wechat/sessions")
def wechat_sessions(limit: int = 50, offset: int = 0) -> dict:
    try:
        return {"sessions": list_sessions(limit, offset=offset)}
    except WeChatCliError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/api/wechat/import-recent")
def import_recent_wechat(payload: WeChatHistoryImportRequest) -> dict:
    try:
        records, imported_sessions, batch = recent_self_history(
            session_limit=payload.session_limit,
            session_offset=payload.session_offset,
            messages_per_session=payload.messages_per_session,
            include_groups=payload.include_groups,
        )
    except WeChatCliError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    imported = import_records(records)
    if imported:
        distill_self_skill()
    coverage = _update_wechat_coverage(batch, imported_sessions)
    return {
        "imported": imported,
        "recognized_records": len(records),
        "sessions": imported_sessions,
        "batch": batch,
        "raw_messages": sum(item.get("raw_messages", 0) for item in imported_sessions),
        "raw_imported": sum(item.get("raw_imported", 0) for item in imported_sessions),
        "failed_sessions": [
            {
                "username": item.get("username"),
                "display_name": item.get("display_name"),
                "error": item.get("error"),
            }
            for item in imported_sessions
            if item.get("error")
        ],
        "next_session_offset": (
            batch["session_end"] if batch["has_next_batch"] else None
        ),
        "coverage": coverage,
    }


@router.post("/api/wechat/import-contact/{contact_id}")
def import_wechat_contact(
    contact_id: str,
    payload: WeChatContactImportRequest,
) -> dict:
    contact = find_contact(contact_id)
    if not contact.wechat_username:
        raise HTTPException(status_code=400, detail="联系人尚未绑定微信会话 ID")
    try:
        timeline = get_full_timeline(
            contact.wechat_username,
            payload.message_limit,
        )
    except WeChatCliError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    records = timeline_to_records(
        timeline.get("messages", []),
        contact.contact_id,
        contact.relationship,
        contact.wechat_username,
        chat_type=contact.chat_type,
        display_name=contact.display_name,
        participant_count=contact.participant_count
        or timeline_participant_count(timeline.get("messages", [])),
    )
    raw_imported = import_raw_messages(
        timeline_to_raw_messages(
            timeline.get("messages", []),
            contact.contact_id,
            contact.relationship,
            contact.wechat_username,
            chat_type=contact.chat_type,
            display_name=contact.display_name,
            participant_count=contact.participant_count
            or timeline_participant_count(timeline.get("messages", [])),
        )
    )
    imported = import_records(records)
    if imported:
        distill_self_skill()
    return {
        "imported": imported,
        "recognized_records": len(records),
        "raw_messages": len(timeline.get("messages", [])),
        "raw_imported": raw_imported,
        "query": timeline.get("query", {}),
    }


@router.get("/api/wechat/inspect")
def wechat_inspect() -> dict:
    status = get_wechat_status()
    return {
        "status": status,
        "controls": inspect_visible_controls() if status["running"] else [],
    }
