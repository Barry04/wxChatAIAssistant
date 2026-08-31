from __future__ import annotations

from typing import Any

from app.models import AutoReplySettings, Contact, RuntimeSettings
from app.runtime.hub_graph import run_automation_hub


async def run_cycle(
    worker: Any,
    host: Any,
    allow_reply: bool | None = None,
    catch_up_unanswered: bool = False,
    *,
    contact_id: str | None = None,
) -> dict[str, Any]:
    """Run one policy-gated LangGraph Hub cycle.

    The Hub owns task sequencing only. Policy and Operator remain hard-coded
    downstream gates, so a model route can never select a chat or send text.
    """
    settings = AutoReplySettings(**host.load_auto_reply_config())
    contacts = [
        Contact(**item)
        for item in host.load_contacts()
        if (
            item.get("contact_id") in settings.allowed_contact_ids
            or item.get("contact_id") in settings.contact_settings
        )
        and (contact_id is None or item.get("contact_id") == contact_id)
        and item.get("wechat_username")
    ]
    state = host.read_json(
        host.AUTOMATION_STATE_FILE,
        {
            "cursors": {},
            "pending_confirmations": [],
            "candidate_cache": {},
            "send_failures": {},
            "reply_waits": {},
            "paused": False,
        },
    )
    if state.get("paused"):
        return {
            "processed": 0,
            "actions": [],
            "skipped": "paused",
            "orchestration_mode": "langgraph-hub",
            "pending_confirmations": state.get("pending_confirmations", []),
        }

    cursors = state.setdefault("cursors", {})
    pending = state.setdefault("pending_confirmations", [])
    candidate_cache = state.setdefault("candidate_cache", {})
    send_failures = state.setdefault("send_failures", {})
    reply_waits = state.setdefault("reply_waits", {})
    actions: list[dict[str, Any]] = []
    stored = host.get_public_settings()
    runtime = RuntimeSettings(**{**stored, "api_key": worker.api_key_provider()})

    for contact in contacts:
        contact_settings = host._effective_settings(settings, contact.contact_id)
        try:
            final_state = await run_automation_hub(
                contact=contact,
                contact_settings=contact_settings,
                runtime=runtime,
                worker=worker,
                host=host,
                settings=settings,
                cursors=cursors,
                pending=pending,
                candidate_cache=candidate_cache,
                send_failures=send_failures,
                reply_waits=reply_waits,
                allow_reply=allow_reply,
                catch_up_unanswered=catch_up_unanswered,
                has_contact_override=contact.contact_id in settings.contact_settings,
            )
        except Exception as exc:  # noqa: BLE001 - isolate one contact from the cycle
            actions.append(
                {
                    "agent": "hub",
                    "orchestration_mode": "langgraph-hub",
                    "contact_id": contact.contact_id,
                    "display_name": contact.display_name,
                    "talker": contact.wechat_username,
                    "action": "hub_error",
                    "error": type(exc).__name__,
                    "hub_reason": "graph_error",
                }
            )
            continue
        event = final_state.get("event") or {}
        if event:
            actions.append(event)

    state["last_run_at"] = host._now()
    host.write_json(host.AUTOMATION_STATE_FILE, state)
    worker._last_error = ""
    return {
        "processed": len(contacts),
        "actions": actions,
        "orchestration_mode": "langgraph-hub",
        "pending_confirmations": pending,
    }
