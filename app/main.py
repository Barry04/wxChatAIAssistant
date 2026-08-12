from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import (
    Contact,
    ContactStyleUpdate,
    AutoReplyContactSettings,
    FeedbackRequest,
    GenerateRequest,
    ImportTextRequest,
    RuntimeSettings,
    AutoReplySettings,
    AutomationConfirmationRequest,
    WeChatContactImportRequest,
    WeChatHistoryImportRequest,
)
from .self_skill import (
    distill_girls_chat_style,
    distill_self_skill,
    get_girls_chat_style,
    get_self_skill,
    get_style_presets,
)
from .services import (
    corpus_stats,
    distill_profile,
    generate_reply,
    get_public_settings,
    get_runtime_settings,
    import_records,
    import_raw_messages,
    parse_csv_bytes,
    parse_plain_text,
    save_feedback,
    save_public_settings,
)
from .storage import (
    MESSAGES_FILE,
    AUTOMATION_STATE_FILE,
    FRONTEND_DIST,
    ensure_storage,
    load_auto_reply_config,
    load_all_skills,
    load_contacts,
    save_auto_reply_config,
    save_contacts,
    read_json,
    read_jsonl,
    write_json,
    AUTOMATION_EVENTS_FILE,
    SELF_SKILL_META_FILE,
    WECHAT_COVERAGE_FILE,
    WECHAT_RAW_MESSAGES_FILE,
)
from .wechat_bridge import get_wechat_status, inspect_visible_controls
from .wechat_cli_bridge import (
    WeChatCliError,
    get_full_timeline,
    get_reader_status,
    get_timeline,
    list_sessions,
    recent_self_history,
    timeline_participant_count,
    timeline_to_raw_messages,
    timeline_to_records,
)
from .automation import AutomationWorker
from .agent.llm import chat_completion
from .chat_analysis import analyze_chat_records


app = FastAPI(title="关系型微信聊天助手", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNTIME_API_KEY = ""
AUTOMATION_WORKER = AutomationWorker(lambda: RUNTIME_API_KEY)


@app.on_event("startup")
def startup() -> None:
    global RUNTIME_API_KEY
    ensure_storage()
    RUNTIME_API_KEY = get_runtime_settings().api_key
    AUTOMATION_WORKER.start()


@app.on_event("shutdown")
def shutdown() -> None:
    AUTOMATION_WORKER.stop()


def get_contacts() -> list[dict]:
    return load_contacts()


def find_contact(contact_id: str) -> Contact:
    for item in get_contacts():
        if item.get("contact_id") == contact_id:
            return Contact(**item)
    raise HTTPException(status_code=404, detail="联系人不存在")


def _validate_style_preset_id(style_preset_id: str) -> None:
    if not style_preset_id:
        return
    available_ids = {item.get("id") for item in get_style_presets()}
    if style_preset_id not in available_ids:
        raise HTTPException(
            status_code=400,
            detail="指定的回复风格不存在或尚未生成",
        )


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


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "local_only": True}


@app.get("/api/contacts")
def list_contacts() -> list[dict]:
    return get_contacts()


@app.post("/api/contacts")
def upsert_contact(contact: Contact) -> Contact:
    _validate_style_preset_id(contact.style_preset_id)
    contacts = get_contacts()
    updated = False
    for index, item in enumerate(contacts):
        if item.get("contact_id") == contact.contact_id:
            contacts[index] = contact.model_dump()
            updated = True
            break
    if not updated:
        contacts.append(contact.model_dump())
    save_contacts(contacts)
    return contact


@app.patch("/api/contacts/{contact_id}/style")
def update_contact_style(contact_id: str, payload: ContactStyleUpdate) -> Contact:
    _validate_style_preset_id(payload.style_preset_id)
    contacts = get_contacts()
    for item in contacts:
        if item.get("contact_id") == contact_id:
            item["style_preset_id"] = payload.style_preset_id
            save_contacts(contacts)
            return Contact.model_validate(item)
    raise HTTPException(status_code=404, detail="联系人不存在")


@app.delete("/api/contacts/{contact_id}")
def delete_contact(contact_id: str) -> dict:
    contacts = get_contacts()
    remaining = [item for item in contacts if item.get("contact_id") != contact_id]
    if len(remaining) == len(contacts):
        raise HTTPException(status_code=404, detail="联系人不存在")
    save_contacts(remaining)
    return {"deleted": contact_id}


@app.get("/api/skills")
def skills() -> list[dict]:
    return load_all_skills()


@app.get("/api/stats")
def stats() -> dict:
    return corpus_stats()


@app.post("/api/import/text")
def import_text(payload: ImportTextRequest) -> dict:
    find_contact(payload.contact_id)
    records = parse_plain_text(
        payload.content,
        payload.contact_id,
        payload.relationship,
        payload.self_label,
    )
    if not records:
        raise HTTPException(
            status_code=400,
            detail="没有识别到有效对话，请使用“对方: 内容”和“我: 内容”的格式。",
        )
    imported = import_records(records)
    if imported:
        distill_self_skill()
    return {"imported": imported, "preview": records[:3]}


@app.post("/api/import/file")
async def import_file(
    file: Annotated[UploadFile, File()],
    contact_id: Annotated[str, Form()],
    relationship: Annotated[str, Form()],
    self_label: Annotated[str, Form()] = "我",
) -> dict:
    find_contact(contact_id)
    content = await file.read()
    suffix = Path(file.filename or "").suffix.lower()
    if suffix == ".csv":
        records = parse_csv_bytes(content, contact_id, relationship, self_label)
    elif suffix in {".txt", ".md"}:
        records = parse_plain_text(
            content.decode("utf-8-sig"),
            contact_id,
            relationship,
            self_label,
        )
    else:
        raise HTTPException(status_code=400, detail="目前只支持 TXT、MD 和 CSV 文件。")
    if not records:
        raise HTTPException(status_code=400, detail="文件中没有识别到有效对话。")
    imported = import_records(records)
    if imported:
        distill_self_skill()
    return {"imported": imported, "preview": records[:3]}


@app.post("/api/distill")
def distill() -> dict:
    return distill_profile()


@app.post("/api/self-skill/distill")
def distill_personal_skill() -> dict:
    return distill_self_skill()


@app.get("/api/self-skill/girls-chat-style")
def girls_chat_style() -> dict:
    return get_girls_chat_style()


@app.post("/api/self-skill/girls-chat-style/distill")
def distill_girls_chat() -> dict:
    return distill_girls_chat_style()


@app.get("/api/self-skill")
def self_skill() -> dict:
    return get_self_skill()


@app.get("/api/style-presets")
def style_presets() -> list[dict]:
    return get_style_presets()


@app.get("/api/wechat/analysis")
def wechat_analysis() -> dict:
    return analyze_chat_records(read_jsonl(MESSAGES_FILE))


@app.get("/api/wechat/coverage")
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


@app.get("/api/wechat/status")
def wechat_status() -> dict:
    return {**get_wechat_status(), "reader": get_reader_status()}


@app.get("/api/wechat/sessions")
def wechat_sessions(limit: int = 50, offset: int = 0) -> dict:
    try:
        return {"sessions": list_sessions(limit, offset=offset)}
    except WeChatCliError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/wechat/import-recent")
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


@app.post("/api/wechat/import-contact/{contact_id}")
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


@app.get("/api/wechat/inspect")
def wechat_inspect() -> dict:
    status = get_wechat_status()
    return {
        "status": status,
        "controls": inspect_visible_controls() if status["running"] else [],
    }


@app.get("/api/automation/settings")
def automation_settings() -> dict:
    settings = AutoReplySettings(
        **load_auto_reply_config()
    )
    return settings.model_dump()


@app.put("/api/automation/settings")
def update_automation_settings(payload: AutoReplySettings) -> dict:
    if payload.enabled and not payload.dry_run and not payload.real_send_acknowledged:
        raise HTTPException(
            status_code=400,
            detail="开启真实发送前，请先关闭 Dry-run 并明确确认发送保护",
        )
    save_auto_reply_config(payload.model_dump())
    AUTOMATION_WORKER.wake()
    return payload.model_dump()


@app.get("/api/automation/contact-settings/{contact_id:path}")
def automation_contact_settings(contact_id: str) -> dict:
    settings = AutoReplySettings(
        **load_auto_reply_config()
    )
    override = settings.contact_settings.get(contact_id)
    if override is None:
        effective = settings
    else:
        values = settings.model_dump()
        values.pop("contact_settings", None)
        values.update(
            {
                key: value
                for key, value in override.model_dump().items()
                if value is not None
            }
        )
        effective = AutoReplySettings(**values)
    return {
        "contact_id": contact_id,
        "settings": {
            "memory_sync_enabled": effective.memory_sync_enabled,
            "enabled": effective.enabled,
            "dry_run": effective.dry_run,
            "real_send_acknowledged": effective.real_send_acknowledged,
            "auto_send_levels": [
                level for level in effective.auto_send_levels if level != "L3"
            ],
        },
        "has_override": override is not None,
    }


@app.put("/api/automation/contact-settings/{contact_id:path}")
def update_automation_contact_settings(
    contact_id: str,
    payload: AutoReplyContactSettings,
) -> dict:
    settings = AutoReplySettings(
        **load_auto_reply_config()
    )
    values = {
        key: value
        for key, value in payload.model_dump().items()
        if value is not None
    }
    if "auto_send_levels" in values:
        values["auto_send_levels"] = [
            level for level in values["auto_send_levels"] if level != "L3"
        ]
    if (
        values.get("enabled")
        and values.get("dry_run") is False
        and values.get("real_send_acknowledged") is not True
    ):
        raise HTTPException(
            status_code=400,
            detail="开启该联系人的真实发送前，请先确认发送保护",
        )
    settings.contact_settings[contact_id] = AutoReplyContactSettings(**values)
    save_auto_reply_config(settings.model_dump())
    AUTOMATION_WORKER.wake()
    return automation_contact_settings(contact_id)


@app.get("/api/automation/status")
def automation_status() -> dict:
    return AUTOMATION_WORKER.status()


@app.get("/api/automation/pending")
def automation_pending() -> list[dict]:
    state = read_json(
        AUTOMATION_STATE_FILE,
        {"cursors": {}, "pending_confirmations": [], "paused": False},
    )
    return state.get("pending_confirmations", [])


@app.post("/api/automation/confirm/{confirmation_id}")
async def automation_confirm(
    confirmation_id: str,
    payload: AutomationConfirmationRequest,
) -> dict:
    result = await AUTOMATION_WORKER.confirm(confirmation_id, payload.text)
    if not result.get("ok"):
        error = result.get("error")
        if error in {"dry_run_enabled", "real_send_not_acknowledged", "cycle_already_running"}:
            status_code = 409
        elif error == "confirmation_not_found":
            status_code = 404
        else:
            status_code = 503
        raise HTTPException(
            status_code=status_code,
            detail=error or result.get("event", {}).get("send_error"),
        )
    return result


@app.delete("/api/automation/pending/{confirmation_id}")
def discard_automation_pending(confirmation_id: str) -> dict:
    result = AUTOMATION_WORKER.discard_confirmation(confirmation_id)
    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="待确认项不存在")
    return result


@app.post("/api/automation/pause")
def pause_automation() -> dict:
    return AUTOMATION_WORKER.set_paused(True)


@app.post("/api/automation/resume")
def resume_automation() -> dict:
    return AUTOMATION_WORKER.set_paused(False)


@app.post("/api/automation/reset-cursors")
def reset_automation_cursors(contact_id: str | None = None) -> dict:
    result = AUTOMATION_WORKER.reset_cursors(contact_id)
    if not result.get("reset"):
        raise HTTPException(status_code=404, detail=result.get("error", "重置游标失败"))
    return result


@app.get("/api/automation/events")
def automation_events(limit: int = 50) -> list[dict]:
    return read_jsonl(AUTOMATION_EVENTS_FILE)[-max(1, min(limit, 200)) :]


@app.post("/api/automation/run-once")
async def automation_run_once(contact_id: str | None = None) -> dict:
    if contact_id and not find_contact(contact_id):
        raise HTTPException(status_code=404, detail="联系人不存在")
    return await AUTOMATION_WORKER.run_once(
        catch_up_unanswered=True,
        wait_for_cycle=True,
        contact_id=contact_id,
    )


@app.post("/api/generate")
async def generate(payload: GenerateRequest) -> dict:
    contact = find_contact(payload.contact_id)
    _validate_style_preset_id(payload.style_preset_id)
    stored = get_public_settings()
    settings = RuntimeSettings(**{**stored, "api_key": RUNTIME_API_KEY})
    return await generate_reply(
        contact,
        payload.conversation,
        settings,
        style_preset_id=payload.style_preset_id,
    )


@app.post("/api/feedback")
def feedback(payload: FeedbackRequest) -> dict:
    contact = find_contact(payload.contact_id)
    save_feedback(
        contact,
        payload.conversation,
        payload.selected_text,
        payload.final_text,
        payload.scene,
    )
    return {"saved": True}


@app.get("/api/settings")
def settings() -> dict:
    return {
        **get_public_settings(),
        "api_key_configured": bool(RUNTIME_API_KEY),
    }


@app.put("/api/settings")
def update_settings(payload: RuntimeSettings) -> dict:
    global RUNTIME_API_KEY
    current = get_runtime_settings()
    api_key = payload.api_key or current.api_key
    settings_to_save = payload.model_copy(update={"api_key": api_key})
    RUNTIME_API_KEY = api_key
    save_public_settings(settings_to_save)
    return {
        **get_public_settings(),
        "api_key_configured": bool(RUNTIME_API_KEY),
    }


@app.post("/api/settings/test")
async def test_settings() -> dict:
    stored = get_public_settings()
    settings = RuntimeSettings(**{**stored, "api_key": RUNTIME_API_KEY})
    if settings.provider == "demo":
        return {
            "ok": False,
            "provider": settings.provider,
            "api_key_configured": False,
            "error": "离线演示模式不会调用外部模型",
        }
    try:
        content = await chat_completion(
            settings,
            '只输出 JSON：{"ok":true}',
            temperature=0,
            force_json=True,
        )
        return {
            "ok": True,
            "provider": settings.provider,
            "model": settings.model,
            "api_key_configured": bool(RUNTIME_API_KEY),
            "response_received": bool(content.strip()),
        }
    except Exception as exc:  # noqa: BLE001 - return a safe connection diagnostic
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.model,
            "api_key_configured": bool(RUNTIME_API_KEY),
            "error": str(exc) or exc.__class__.__name__,
        }


if (FRONTEND_DIST / "assets").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="frontend-assets",
    )


@app.get("/{full_path:path}")
def frontend(full_path: str):
    index = FRONTEND_DIST / "index.html"
    requested = FRONTEND_DIST / full_path
    if full_path and requested.is_file():
        return FileResponse(requested)
    if index.exists():
        return FileResponse(
            index,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
        )
    return {
        "message": "前端尚未构建，请在 frontend 目录执行 npm install 和 npm run build。"
    }
