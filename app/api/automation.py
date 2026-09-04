"""自动回复工作线程配置、确认流与运行控制路由。"""

from fastapi import APIRouter, HTTPException

from ..models import (
    AutomationConfirmationRequest,
    AutoReplyContactSettings,
    AutoReplySettings,
)
from ..storage import (
    AUTOMATION_EVENTS_FILE,
    AUTOMATION_STATE_FILE,
    load_auto_reply_config,
    read_json,
    read_jsonl,
    save_auto_reply_config,
)
from .contacts import find_contact
from .state import AUTOMATION_WORKER

router = APIRouter()


@router.get("/api/automation/settings")
def automation_settings() -> dict:
    settings = AutoReplySettings(
        **load_auto_reply_config()
    )
    return settings.model_dump()


@router.put("/api/automation/settings")
def update_automation_settings(payload: AutoReplySettings) -> dict:
    if payload.enabled and not payload.dry_run and not payload.real_send_acknowledged:
        raise HTTPException(
            status_code=400,
            detail="开启真实发送前，请先关闭 Dry-run 并明确确认发送保护",
        )
    save_auto_reply_config(payload.model_dump())
    AUTOMATION_WORKER.wake()
    return payload.model_dump()


@router.get("/api/automation/contact-settings/{contact_id:path}")
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


@router.put("/api/automation/contact-settings/{contact_id:path}")
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


@router.get("/api/automation/status")
def automation_status() -> dict:
    return AUTOMATION_WORKER.status()


@router.get("/api/automation/pending")
def automation_pending() -> list[dict]:
    state = read_json(
        AUTOMATION_STATE_FILE,
        {"cursors": {}, "pending_confirmations": [], "paused": False},
    )
    return state.get("pending_confirmations", [])


@router.post("/api/automation/confirm/{confirmation_id}")
async def automation_confirm(
    confirmation_id: str,
    payload: AutomationConfirmationRequest,
) -> dict:
    result = await AUTOMATION_WORKER.confirm(confirmation_id, payload.text)
    if not result.get("ok"):
        error = result.get("error")
        if error in {
            "dry_run_enabled",
            "real_send_not_acknowledged",
            "cycle_already_running",
            "contact_binding_changed",
        }:
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


@router.delete("/api/automation/pending/{confirmation_id}")
def discard_automation_pending(confirmation_id: str) -> dict:
    result = AUTOMATION_WORKER.discard_confirmation(confirmation_id)
    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="待确认项不存在")
    return result


@router.post("/api/automation/pause")
def pause_automation() -> dict:
    return AUTOMATION_WORKER.set_paused(True)


@router.post("/api/automation/resume")
def resume_automation() -> dict:
    return AUTOMATION_WORKER.set_paused(False)


@router.post("/api/automation/reset-cursors")
def reset_automation_cursors(contact_id: str | None = None) -> dict:
    result = AUTOMATION_WORKER.reset_cursors(contact_id)
    if not result.get("reset"):
        raise HTTPException(status_code=404, detail=result.get("error", "重置游标失败"))
    return result


@router.get("/api/automation/events")
def automation_events(limit: int = 50) -> list[dict]:
    return read_jsonl(AUTOMATION_EVENTS_FILE)[-max(1, min(limit, 200)) :]


@router.post("/api/automation/run-once")
async def automation_run_once(contact_id: str | None = None) -> dict:
    if contact_id and not find_contact(contact_id):
        raise HTTPException(status_code=404, detail="联系人不存在")
    return await AUTOMATION_WORKER.run_once(
        catch_up_unanswered=True,
        wait_for_cycle=True,
        contact_id=contact_id,
    )
