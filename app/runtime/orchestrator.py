import asyncio
from typing import Any

from app.models import AutoReplySettings, Contact, RuntimeSettings
from app.operator.agent import execute_send
from app.runtime.messages import conversation_text
from app.runtime.policy import evaluate_send_policy
from app.runtime.watcher import inspect_incoming, load_timeline, ordered_timeline_messages


async def run_cycle(
    worker: Any,
    host: Any,
    allow_reply: bool | None = None,
    catch_up_unanswered: bool = False,
    *,
    contact_id: str | None = None,
) -> dict[str, Any]:
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
        has_contact_override = contact.contact_id in settings.contact_settings
        reply_enabled = (
            (not has_contact_override or contact_settings.enabled)
            if allow_reply is None
            else allow_reply and contact_settings.enabled
        )
        confirmation_id = ""
        talker = contact.wechat_username
        try:
            if catch_up_unanswered:
                timeline = await asyncio.to_thread(
                    load_timeline,
                    host,
                    talker,
                    True,
                )
            else:
                timeline = load_timeline(host, talker, False)
        except Exception as exc:
            actions.append(
                {
                    "agent": "watch",
                    "contact_id": contact.contact_id,
                    "display_name": contact.display_name,
                    "talker": talker,
                    "action": "read_error",
                    "error": str(exc),
                }
            )
            continue

        messages = ordered_timeline_messages(timeline)
        if not messages:
            continue
        memory_imported = (
            host.sync_timeline_to_memory(contact, timeline)
            if contact_settings.memory_sync_enabled
            else 0
        )
        watched = inspect_incoming(
            contact=contact,
            messages=messages,
            talker=talker,
            catch_up_unanswered=catch_up_unanswered,
            cursors=cursors,
            reply_waits=reply_waits,
            candidate_cache=candidate_cache,
            send_failures=send_failures,
            memory_imported=memory_imported,
        )
        if watched["status"] == "empty":
            continue
        if watched["status"] == "skip":
            actions.append(watched["action"])
            continue

        incoming = watched["incoming"]
        newest_id = watched["newest_id"]
        previous_id = watched["previous_id"]
        trigger_reason = watched["trigger_reason"]

        if not reply_enabled:
            continue

        wait = reply_waits.get(talker)
        now = host.time.time()
        if wait is None:
            wait = {
                "started_at": now,
                "incoming_id": int(
                    (incoming[0].get("id") or {}).get("local_id") or 0
                ),
                "takeover_ready": catch_up_unanswered
                or contact_settings.takeover_delay_seconds == 0,
            }
            reply_waits[talker] = wait
        elif not wait.get("takeover_ready"):
            started_at = float(wait.get("started_at") or now)
            wait["takeover_ready"] = (
                now - started_at >= contact_settings.takeover_delay_seconds
            )

        if not wait.get("takeover_ready"):
            actions.append(
                {
                    "agent": "watch",
                    "contact_id": contact.contact_id,
                    "display_name": contact.display_name,
                    "talker": talker,
                    "action": "waiting_for_user",
                    "newest_local_id": newest_id,
                    "started_at": wait["started_at"],
                    "takeover_delay_seconds": contact_settings.takeover_delay_seconds,
                    "remaining_seconds": max(
                        0,
                        int(
                            contact_settings.takeover_delay_seconds
                            - (now - float(wait["started_at"]))
                        ),
                    ),
                    "memory_imported": memory_imported,
                }
            )
            continue

        retry_key = f"{talker}:{newest_id}"
        retry_state = send_failures.get(retry_key) or {}
        retry_after = float(retry_state.get("retry_after") or 0)
        if retry_after > host.time.time():
            actions.append(
                {
                    "agent": "watch",
                    "contact_id": contact.contact_id,
                    "display_name": contact.display_name,
                    "talker": talker,
                    "action": "retry_backoff",
                    "newest_local_id": newest_id,
                    "retry_after": retry_after,
                    "attempts": int(retry_state.get("attempts") or 0),
                }
            )
            continue

        cached = candidate_cache.get(retry_key)
        if cached:
            result = cached
        else:
            result = await host.generate_reply(
                contact,
                conversation_text(messages),
                runtime,
            )
            candidate_cache[retry_key] = result
        risk_level = result["risk"]["level"]
        response_plan = (result.get("dialogue") or {}).get("response_plan") or {}
        requires_confirmation = bool(response_plan) and (
            response_plan.get("action") == "acknowledge_then_explore"
            or float(response_plan.get("confidence") or 0) < 0.75
        )
        candidate = (result.get("candidates") or [{}])[0].get("text", "")
        candidate_options = [
            str(item.get("text") or "").strip()
            for item in (result.get("candidates") or [])[:3]
            if str(item.get("text") or "").strip()
        ]
        model_fallback = any(
            item.get("role") == "writer" and item.get("status") == "fallback"
            for item in (result.get("trace") or [])
        )
        policy = evaluate_send_policy(
            candidate=candidate,
            risk_level=risk_level,
            auto_send_levels=contact_settings.auto_send_levels,
            requires_confirmation=requires_confirmation,
            provider=runtime.provider,
            model_fallback=model_fallback,
            dry_run=contact_settings.dry_run,
            enabled=contact_settings.enabled,
            real_send_acknowledged=contact_settings.real_send_acknowledged,
        )
        action = "blocked"
        sent = False
        send_verified = False
        send_error = ""
        advance_cursor = True
        agent = "policy"
        if policy.decision == "auto_send":
            confirmation_id = worker._confirmation_id(talker, newest_id, candidate)
            try:
                operator_result = execute_send(
                    display_name=contact.display_name,
                    talker=talker,
                    text=candidate,
                    newest_local_id=newest_id,
                )
                send_verified = bool(operator_result.get("send_verified"))
                send_error = str(operator_result.get("send_error") or "")
            except Exception as exc:
                send_error = str(exc)
                send_verified = False
            agent = "operator"
            if send_verified:
                action = "sent"
                sent = True
                candidate_cache.pop(retry_key, None)
                send_failures.pop(retry_key, None)
            else:
                action = "send_unverified"
                advance_cursor = False
                failure = send_failures.setdefault(
                    retry_key,
                    {"attempts": 0, "last_error": ""},
                )
                failure["attempts"] = int(failure.get("attempts") or 0) + 1
                failure["last_error"] = send_error
                failure["retry_after"] = host.time.time() + min(
                    30.0,
                    3.0 * (2 ** min(failure["attempts"] - 1, 3)),
                )
        elif policy.decision == "needs_confirmation":
            action = "needs_confirmation"
            confirmation_id = worker._confirmation_id(talker, newest_id, candidate)
            worker._enqueue_confirmation(
                pending,
                confirmation_id=confirmation_id,
                contact=contact,
                talker=talker,
                incoming=incoming,
                candidate=candidate,
                candidate_options=candidate_options,
                risk=result["risk"],
                newest_id=newest_id,
                conversation=conversation_text(messages),
                reason=policy.reason,
            )
        else:
            action = "blocked"

        if action in {"needs_confirmation", "blocked", "ignored"}:
            candidate_cache.pop(retry_key, None)
            send_failures.pop(retry_key, None)
            reply_waits.pop(talker, None)
        elif action == "send_unverified":
            reply_waits[talker] = {
                **reply_waits.get(talker, {}),
                "takeover_ready": True,
            }
        else:
            reply_waits.pop(talker, None)
        cursors[talker] = newest_id if advance_cursor else previous_id
        event = {
            "created_at": host._now(),
            "agent": agent,
            "contact_id": contact.contact_id,
            "display_name": contact.display_name,
            "talker": talker,
            "chat_type": contact.chat_type,
            "trigger_reason": trigger_reason,
            "incoming": [message.get("text", "") for message in incoming],
            "risk": result["risk"],
            "candidate": candidate,
            "action": action,
            "sent": sent,
            "send_verified": send_verified,
            "send_error": send_error,
            "dry_run": contact_settings.dry_run,
            "settings_scope": "contact",
            "confirmation_id": confirmation_id,
            "newest_local_id": newest_id,
            "memory_imported": memory_imported,
            "generation": {
                "provider": result.get("provider") or runtime.provider,
                "model_fallback": model_fallback,
                "dialogue": result.get("dialogue") or {},
                "review": result.get("review") or {},
                "warning": result.get("warning") or "",
                "trace": result.get("trace") or [],
                "example_sources": [
                    {
                        "contact_id": item.get("contact_id"),
                        "source": item.get("source"),
                        "score": item.get("score"),
                    }
                    for item in (result.get("examples") or [])[:3]
                ],
            },
        }
        host.append_jsonl(host.AUTOMATION_EVENTS_FILE, event)
        actions.append(event)

    state["last_run_at"] = host._now()
    host.write_json(host.AUTOMATION_STATE_FILE, state)
    worker._last_error = ""
    return {"processed": len(contacts), "actions": actions}
