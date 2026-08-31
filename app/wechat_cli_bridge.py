import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from .message_text import display_message_text
from .storage import ROOT


PRIVATE_CONFIG = ROOT / "private" / "wechat-cli-config.json"


class WeChatCliError(RuntimeError):
    pass


def _find_executable() -> Path | None:
    explicit = os.environ.get("WECHAT_CLI_EXE", "").strip()
    if explicit and Path(explicit).is_file():
        return Path(explicit)
    candidates = sorted(
        (ROOT / ".runtime").glob("wechat-cli-v*/wechat-cli.exe"),
        reverse=True,
    )
    return candidates[0] if candidates else None


def _load_private_config() -> dict[str, Any]:
    if not PRIVATE_CONFIG.exists():
        return {}
    with PRIVATE_CONFIG.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _run(*args: str, timeout: int = 90) -> dict[str, Any]:
    executable = _find_executable()
    if executable is None:
        raise WeChatCliError("wechat-cli 尚未安装")
    config = _load_private_config()
    env = os.environ.copy()
    env["WECHAT_CLI_CONFIG"] = str(PRIVATE_CONFIG)
    if config.get("db_root"):
        env["WECHAT_CLI_DB_ROOT"] = str(config["db_root"])
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    completed = subprocess.run(
        [str(executable), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=creationflags,
        check=False,
    )
    output = completed.stdout.strip()
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        detail = completed.stderr.strip() or output or f"退出码 {completed.returncode}"
        raise WeChatCliError(f"wechat-cli 输出无法解析: {detail}") from exc
    if not payload.get("ok"):
        error = payload.get("error") or {}
        raise WeChatCliError(str(error.get("message") or "wechat-cli 调用失败"))
    return payload


def get_reader_status() -> dict[str, Any]:
    executable = _find_executable()
    if executable is None:
        return {
            "installed": False,
            "ready": False,
            "message": "wechat-cli 尚未安装",
        }
    try:
        payload = _run("status")
        status = payload["data"]["status"]
        return {
            "installed": True,
            "ready": bool(status.get("live_read_ok")),
            "executable": str(executable),
            **status,
        }
    except Exception as exc:
        return {
            "installed": True,
            "ready": False,
            "executable": str(executable),
            "message": str(exc),
        }


def list_sessions(
    limit: int = 50,
    *,
    offset: int = 0,
) -> list[dict[str, Any]]:
    args = [
        "sessions",
        "--type-filter",
        "private,group",
        "--limit",
        str(limit),
    ]
    if offset:
        args.extend(["--offset", str(offset)])
    payload = _run(
        *args,
    )
    return payload["data"].get("sessions", [])


def resolve_session_display_name(
    username: str,
    fallback: str = "",
) -> str:
    """Resolve the current remark or nickname from the stable WeChat session ID."""
    username = str(username or "").strip()
    if not username:
        return fallback
    offset = 0
    while True:
        sessions = list_sessions(500, offset=offset)
        for session in sessions:
            if str(session.get("username") or "").strip() != username:
                continue
            return str(session.get("display_name") or fallback or username).strip()
        if len(sessions) < 500:
            break
        offset += len(sessions)
    return fallback or username


def get_timeline(
    talker: str,
    limit: int = 200,
    *,
    offset: int = 0,
) -> dict[str, Any]:
    args = [
        "timeline",
        "--talker",
        talker,
        "--limit",
        str(limit),
        "--display-order",
        "asc",
    ]
    if offset:
        args.extend(["--offset", str(offset)])
    payload = _run(*args, timeout=120)
    return payload["data"]


def get_full_timeline(
    talker: str,
    max_messages: int = 50000,
    *,
    page_size: int = 200,
) -> dict[str, Any]:
    """Read all available timeline pages up to max_messages."""
    page_size = max(1, min(page_size, max_messages))
    messages: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    offset = 0
    pages = 0
    last_query: dict[str, Any] = {}
    while len(messages) < max_messages:
        page = get_timeline(
            talker,
            min(page_size, max_messages - len(messages)),
            offset=offset,
        )
        pages += 1
        last_query = dict(page.get("query") or {})
        batch = page.get("messages", [])
        if not batch:
            break
        added = 0
        for message in batch:
            local_id = int((message.get("id") or {}).get("local_id") or 0)
            key = local_id or hash(
                json.dumps(message, sort_keys=True, ensure_ascii=False)
            )
            if key in seen_ids:
                continue
            seen_ids.add(key)
            messages.append(message)
            added += 1
            if len(messages) >= max_messages:
                break
        if not last_query.get("has_more") or added == 0:
            break
        offset += len(batch)
    last_query.update(
        {
            "has_more": bool(last_query.get("has_more"))
            and len(messages) >= max_messages,
            "pages_read": pages,
            "messages_read": len(messages),
            "max_messages": max_messages,
        }
    )
    return {"messages": messages, "query": last_query}


def _message_text(message: dict[str, Any]) -> str:
    return display_message_text(message)


def _message_timestamp(message: dict[str, Any]) -> int:
    timestamp = message.get("create_time")
    if timestamp:
        return int(timestamp)
    iso_value = str(message.get("time_iso") or "").strip()
    if iso_value:
        try:
            return int(datetime.fromisoformat(iso_value).timestamp())
        except ValueError:
            pass
    return 0


def timeline_participant_count(messages: list[dict[str, Any]]) -> int | None:
    participants = {
        str(message.get("sender_wxid") or message.get("sender") or "").strip()
        for message in messages
        if str(message.get("sender_wxid") or message.get("sender") or "").strip()
    }
    if any(message.get("is_from_me") for message in messages):
        participants.add("__self__")
    return len(participants) or None


def timeline_to_raw_messages(
    messages: list[dict[str, Any]],
    contact_id: str,
    relationship: str,
    talker: str,
    *,
    chat_type: str = "private",
    display_name: str = "",
    participant_count: int | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for message in messages:
        local_id = int((message.get("id") or {}).get("local_id") or 0)
        source_id = (
            f"wechat:{talker}:{local_id}"
            if local_id
            else f"wechat:{talker}:{hash(json.dumps(message, sort_keys=True, ensure_ascii=False))}"
        )
        rows.append(
            {
                "contact_id": contact_id,
                "relationship": relationship,
                "wechat_talker": talker,
                "display_name": display_name,
                "chat_type": chat_type,
                "participant_count": participant_count,
                "source": "wechat_raw",
                "source_message_id": source_id,
                "local_id": local_id,
                "create_time": _message_timestamp(message),
                "is_from_me": bool(message.get("is_from_me")),
                "kind": str(message.get("kind") or "unknown"),
                "text": _message_text(message),
            }
        )
    return rows


def timeline_to_records(
    messages: list[dict[str, Any]],
    contact_id: str,
    relationship: str,
    talker: str,
    *,
    chat_type: str = "private",
    display_name: str = "",
    participant_count: int | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    incoming: list[str] = []
    replies: list[str] = []
    incoming_ids: list[int] = []
    reply_ids: list[int] = []
    incoming_times: list[int] = []
    reply_times: list[int] = []
    incoming_kinds: list[str] = []
    reply_kinds: list[str] = []

    def flush() -> None:
        nonlocal incoming, replies, incoming_ids, reply_ids
        nonlocal incoming_times, reply_times, incoming_kinds, reply_kinds
        if incoming and replies:
            from .services import classify_scene

            record_id = f"wechat:{talker}:{reply_ids[-1]}"
            response_seconds = None
            if incoming_times and reply_times:
                response_seconds = max(0, reply_times[0] - incoming_times[-1])
            records.append(
                {
                    "contact_id": contact_id,
                    "relationship": relationship,
                    "scene": classify_scene("\n".join(incoming)),
                    "incoming": incoming.copy(),
                    "my_reply": replies.copy(),
                    "source": "wechat",
                    "source_record_id": record_id,
                    "wechat_talker": talker,
                    "display_name": display_name,
                    "chat_type": chat_type,
                    "participant_count": participant_count,
                    "incoming_local_ids": incoming_ids.copy(),
                    "reply_local_ids": reply_ids.copy(),
                    "incoming_times": incoming_times.copy(),
                    "reply_times": reply_times.copy(),
                    "incoming_kinds": incoming_kinds.copy(),
                    "reply_kinds": reply_kinds.copy(),
                    "response_seconds": response_seconds,
                }
            )
        incoming, replies, incoming_ids, reply_ids = [], [], [], []
        incoming_times, reply_times = [], []
        incoming_kinds, reply_kinds = [], []

    for message in messages:
        local_id = int((message.get("id") or {}).get("local_id") or 0)
        text = _message_text(message)
        timestamp = _message_timestamp(message)
        kind = str(message.get("kind") or "unknown")
        if message.get("is_from_me"):
            if incoming:
                replies.append(text)
                reply_ids.append(local_id)
                reply_times.append(timestamp)
                reply_kinds.append(kind)
        else:
            if replies:
                flush()
            incoming.append(text)
            incoming_ids.append(local_id)
            incoming_times.append(timestamp)
            incoming_kinds.append(kind)
    flush()
    return records


def recent_self_history(
    session_limit: int = 100,
    session_offset: int = 0,
    messages_per_session: int = 50000,
    include_groups: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    session_offset = max(0, session_offset)
    session_limit = max(1, session_limit)
    # Page the session directory first. The CLI's limit is not the total count.
    all_sessions: list[dict[str, Any]] = []
    directory_offset = 0
    while True:
        page = list_sessions(500, offset=directory_offset)
        all_sessions.extend(page)
        if len(page) < 500:
            break
        directory_offset += len(page)
    sessions = all_sessions[session_offset : session_offset + session_limit]
    records: list[dict[str, Any]] = []
    imported_sessions: list[dict[str, Any]] = []
    for session in sessions:
        if session.get("chat_type") == "group" and not include_groups:
            continue
        talker = str(session["username"])
        try:
            timeline = get_full_timeline(talker, messages_per_session)
        except WeChatCliError as exc:
            imported_sessions.append(
                {
                    "username": talker,
                    "display_name": session.get("display_name") or talker,
                    "chat_type": session.get("chat_type"),
                    "records": 0,
                    "raw_messages": 0,
                    "raw_imported": 0,
                    "error": str(exc),
                }
            )
            continue
        participant_count = timeline_participant_count(timeline.get("messages", []))
        from .services import import_raw_messages

        raw_imported = import_raw_messages(
            timeline_to_raw_messages(
                timeline.get("messages", []),
                contact_id=f"wechat:{talker}",
                relationship="friend",
                talker=talker,
                chat_type=str(session.get("chat_type") or "private"),
                display_name=str(session.get("display_name") or talker),
                participant_count=participant_count,
            )
        )
        session_records = timeline_to_records(
            timeline.get("messages", []),
            contact_id=f"wechat:{talker}",
            relationship="friend",
            talker=talker,
            chat_type=str(session.get("chat_type") or "private"),
            display_name=str(session.get("display_name") or talker),
            participant_count=participant_count,
        )
        records.extend(session_records)
        messages = timeline.get("messages", [])
        latest = messages[-1] if messages else {}
        imported_sessions.append(
            {
                "username": talker,
                "display_name": session.get("display_name") or talker,
                "chat_type": session.get("chat_type"),
                "records": len(session_records),
                "raw_messages": len(timeline.get("messages", [])),
                "raw_imported": raw_imported,
                "participant_count": participant_count,
                "waiting_for_reply": bool(
                    latest and not latest.get("is_from_me")
                ),
            }
        )
    return records, imported_sessions, {
        "session_offset": session_offset,
        "session_limit": session_limit,
        "session_end": session_offset + len(sessions),
        "total_sessions": len(all_sessions),
        "has_next_batch": session_offset + len(sessions) < len(all_sessions),
        "failed_sessions": sum(1 for item in imported_sessions if item.get("error")),
    }
