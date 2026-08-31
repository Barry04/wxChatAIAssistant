from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.llm import chat_completion, extract_json
from app.models import AutoReplySettings, Contact, RuntimeSettings
from app.operator.agent import execute_send
from app.runtime.messages import conversation_text
from app.runtime.policy import evaluate_send_policy
from app.runtime.watcher import inspect_incoming, load_timeline, ordered_timeline_messages


HubTask = Literal[
    "watch_read",
    "memory_sync",
    "watch_evaluate",
    "draft",
    "policy",
    "operator",
    "queue",
    "finish",
]


class AutomationHubState(TypedDict, total=False):
    # Only business data belongs in graph state. Secrets and runtime objects live
    # in HubRuntimeContext and are never returned by the graph.
    contact: dict[str, Any]
    contact_settings: dict[str, Any]
    reply_enabled: bool
    catch_up_unanswered: bool
    talker: str
    phase: str
    next_task: HubTask
    timeline: dict[str, Any]
    messages: list[dict[str, Any]]
    memory_imported: int
    memory_error: str
    watched: dict[str, Any]
    incoming: list[dict[str, Any]]
    newest_id: int
    previous_id: int
    trigger_reason: str
    retry_key: str
    wait_action: dict[str, Any]
    result: dict[str, Any]
    generation_error: str
    policy: dict[str, Any]
    action: str
    event: dict[str, Any]
    confirmation_id: str
    candidate: str
    candidate_options: list[str]
    risk: dict[str, Any]
    send_verified: bool
    send_error: str
    sent: bool
    advance_cursor: bool
    hub_model_called: bool
    hub_trace: list[dict[str, Any]]
    finished: bool


@dataclass
class HubRuntimeContext:
    """Run-scoped dependencies; never serialized into LangGraph state."""

    host: Any
    worker: Any
    runtime: RuntimeSettings
    settings: AutoReplySettings
    cursors: dict[str, Any]
    pending: list[dict[str, Any]]
    candidate_cache: dict[str, Any]
    send_failures: dict[str, Any]
    reply_waits: dict[str, Any]


def _contact(state: AutomationHubState) -> Contact:
    return Contact.model_validate(state["contact"])


def _contact_settings(state: AutomationHubState) -> AutoReplySettings:
    return AutoReplySettings(**state["contact_settings"])


def _contact_label(state: AutomationHubState) -> str:
    return str(state["contact"].get("display_name") or state.get("talker") or "联系人")


def _append_hub_trace(
    state: AutomationHubState,
    *,
    task: str,
    status: str,
    next_task: str,
    reason_code: str,
    decision_source: str = "rule",
    started: float,
) -> list[dict[str, Any]]:
    trace = list(state.get("hub_trace") or [])
    trace.append(
        {
            "task": task,
            "status": status,
            "next_task": next_task,
            "reason_code": reason_code,
            "decision_source": decision_source,
            "duration_ms": max(0, round((time.perf_counter() - started) * 1000)),
        }
    )
    return trace


def _phase_route(state: AutomationHubState) -> tuple[list[HubTask], str]:
    phase = state.get("phase") or "start"
    if phase == "start":
        return ["watch_read"], "cycle_started"
    if phase == "after_watch_read":
        if not state.get("messages"):
            return ["finish"], "no_messages"
        if _contact_settings(state).memory_sync_enabled:
            return ["memory_sync"], "memory_required"
        return ["watch_evaluate"], "memory_disabled"
    if phase == "after_memory":
        return ["watch_evaluate"], "memory_synced"
    if phase == "after_watch_evaluate":
        watched = state.get("watched") or {}
        if watched.get("status") != "ready":
            return ["finish"], str((state.get("wait_action") or {}).get("action") or "watch_skip")
        if not state.get("reply_enabled"):
            return ["finish"], "reply_disabled"
        if state.get("wait_action"):
            return ["finish"], str(state["wait_action"].get("action") or "wait")
        # The model may explain/confirm the handoff, but an actionable message
        # cannot be silently dropped by a Hub decision.
        return ["draft", "finish"], "draft_required"
    if phase == "after_draft":
        return ["policy"], "policy_required"
    return ["finish"], "cycle_finished"


async def _model_route(
    state: AutomationHubState,
    context: HubRuntimeContext,
    allowed: list[HubTask],
) -> tuple[str | None, str]:
    """Ask the configured model for a bounded route, never for a send decision."""
    if (
        context.runtime.provider == "demo"
        or context.runtime.model == "demo"
        or len(allowed) <= 1
    ):
        return None, "rule"
    prompt = (
        "你是自动回复流程 Hub，只能在给定的 allowed_next 中选择下一个任务。"
        "你不能选择联系人、发送消息、改写候选，也不能绕过 PolicyGate。"
        "若 allowed_next 只有一个值必须选择它。只输出 JSON。\n"
        f"allowed_next={json.dumps(allowed, ensure_ascii=False)}\n"
        f"phase={state.get('phase')}\n"
        f"message_count={len(state.get('messages') or [])}\n"
        f"incoming_count={len(state.get('incoming') or [])}\n"
        f"reply_enabled={bool(state.get('reply_enabled'))}\n"
        f"trigger_reason={state.get('trigger_reason') or ''}\n"
        '{"next_task":"..."}'
    )
    try:
        content = await chat_completion(
            context.runtime,
            prompt,
            temperature=0.0,
            force_json=True,
        )
        payload = extract_json(content)
        candidate = str(payload.get("next_task") or "").strip()
        if candidate in allowed:
            return candidate, "model"
    except Exception:
        pass
    return None, "fallback"


async def hub_node(
    state: AutomationHubState,
    runtime: Any,
) -> dict[str, Any]:
    context: HubRuntimeContext = runtime.context
    started = time.perf_counter()
    allowed, reason = _phase_route(state)
    decision_source = "rule"
    selected: HubTask = allowed[0]

    # The model is consulted only for a genuinely ambiguous route and can never
    # widen the code-owned transition table. Current watcher states normally have
    # one safe next task; this keeps no-op polling cheap and deterministic.
    if len(allowed) > 1 and not state.get("hub_model_called"):
        model_selected, decision_source = await _model_route(state, context, allowed)
        selected = model_selected or selected  # type: ignore[assignment]
        if selected == "finish" and state.get("phase") == "after_watch_evaluate":
            # A ready incoming turn must reach Draft; finish remains valid only
            # for the watcher skip/wait states handled above.
            selected = "draft"
            decision_source = "rule_guard"

    trace = _append_hub_trace(
        state,
        task="hub",
        status="running" if selected != "finish" else "done",
        next_task=selected,
        reason_code=reason,
        decision_source=decision_source,
        started=started,
    )
    return {
        "next_task": selected,
        "hub_trace": trace,
        "hub_model_called": bool(state.get("hub_model_called") or len(allowed) > 1),
    }


async def watch_read_node(
    state: AutomationHubState,
    runtime: Any,
) -> dict[str, Any]:
    context: HubRuntimeContext = runtime.context
    started = time.perf_counter()
    try:
        if state.get("catch_up_unanswered"):
            timeline = await asyncio.to_thread(
                load_timeline,
                context.host,
                state["talker"],
                True,
            )
        else:
            timeline = load_timeline(context.host, state["talker"], False)
        messages = ordered_timeline_messages(timeline)
        result = {
            "timeline": timeline,
            "messages": messages,
            "phase": "after_watch_read",
            "hub_trace": _append_hub_trace(
                state,
                task="watch_read",
                status="ok",
                next_task="hub",
                reason_code="timeline_loaded" if messages else "no_messages",
                started=started,
            ),
        }
    except Exception as exc:  # noqa: BLE001 - read errors are surfaced as an action
        result = {
            "phase": "after_watch_read",
            "watched": {"status": "read_error", "error": str(exc)},
            "wait_action": {
                "agent": "watch",
                "contact_id": state["contact"].get("contact_id"),
                "display_name": _contact_label(state),
                "talker": state["talker"],
                "action": "read_error",
                "error": str(exc),
            },
            "hub_trace": _append_hub_trace(
                state,
                task="watch_read",
                status="error",
                next_task="hub",
                reason_code="timeline_read_error",
                started=started,
            ),
        }
    return result


async def memory_sync_node(
    state: AutomationHubState,
    runtime: Any,
) -> dict[str, Any]:
    context: HubRuntimeContext = runtime.context
    started = time.perf_counter()
    imported = 0
    error = ""
    try:
        imported = int(
            context.host.sync_timeline_to_memory(
                _contact(state),
                state.get("timeline") or {},
            )
            or 0
        )
    except Exception as exc:  # noqa: BLE001 - memory failure must not block a draft
        error = type(exc).__name__
    try:
        from app.memory import (
            extract_facts_via_model,
            refresh_summary,
            sync_incoming_facts,
            upsert_facts,
        )

        timeline = state.get("timeline") or {}
        incoming = [
            message
            for message in (timeline.get("messages") or state.get("messages") or [])
            if not message.get("is_from_me")
        ][-8:]
        contact_id = str(state["contact"].get("contact_id") or "")
        sync_incoming_facts(
            contact_id,
            incoming,
            chat_type=str(state["contact"].get("chat_type") or "private"),
        )
        extra = await extract_facts_via_model(incoming, contact_id, context.runtime)
        if extra:
            upsert_facts(contact_id, extra)
            refresh_summary(contact_id)
    except Exception:
        pass
    return {
        "memory_imported": imported,
        "memory_error": error,
        "phase": "after_memory",
        "hub_trace": _append_hub_trace(
            state,
            task="memory_sync",
            status="fallback" if error else "ok",
            next_task="hub",
            reason_code="memory_sync_error" if error else "memory_synced",
            started=started,
        ),
    }


def watch_evaluate_node(
    state: AutomationHubState,
    runtime: Any,
) -> dict[str, Any]:
    context: HubRuntimeContext = runtime.context
    started = time.perf_counter()
    messages = state.get("messages") or []
    watched = inspect_incoming(
        contact=_contact(state),
        messages=messages,
        talker=state["talker"],
        catch_up_unanswered=bool(state.get("catch_up_unanswered")),
        cursors=context.cursors,
        reply_waits=context.reply_waits,
        candidate_cache=context.candidate_cache,
        send_failures=context.send_failures,
        memory_imported=int(state.get("memory_imported") or 0),
    )
    result: dict[str, Any] = {
        "watched": watched,
        "phase": "after_watch_evaluate",
        "hub_trace": _append_hub_trace(
            state,
            task="watch_evaluate",
            status="ok",
            next_task="hub",
            reason_code=str(watched.get("status") or "evaluated"),
            started=started,
        ),
    }
    if watched.get("status") != "ready":
        result["wait_action"] = watched.get("action") or {}
        return result

    incoming = list(watched.get("incoming") or [])
    result.update(
        {
            "incoming": incoming,
            "newest_id": int(watched.get("newest_id") or 0),
            "previous_id": int(watched.get("previous_id") or 0),
            "trigger_reason": str(watched.get("trigger_reason") or ""),
        }
    )
    if not state.get("reply_enabled"):
        return result

    settings = _contact_settings(state)
    now = context.host.time.time()
    wait = context.reply_waits.get(state["talker"])
    if wait is None:
        wait = {
            "started_at": now,
            "incoming_id": int((incoming[0].get("id") or {}).get("local_id") or 0),
            "takeover_ready": bool(state.get("catch_up_unanswered"))
            or settings.takeover_delay_seconds == 0,
        }
        context.reply_waits[state["talker"]] = wait
    elif not wait.get("takeover_ready"):
        started_at = float(wait.get("started_at") or now)
        wait["takeover_ready"] = (
            now - started_at >= settings.takeover_delay_seconds
        )

    newest_id = int(watched.get("newest_id") or 0)
    if not wait.get("takeover_ready"):
        result["wait_action"] = {
            "agent": "watch",
            "contact_id": state["contact"].get("contact_id"),
            "display_name": _contact_label(state),
            "talker": state["talker"],
            "action": "waiting_for_user",
            "newest_local_id": newest_id,
            "started_at": wait["started_at"],
            "takeover_delay_seconds": settings.takeover_delay_seconds,
            "remaining_seconds": max(
                0,
                int(settings.takeover_delay_seconds - (now - float(wait["started_at"]))),
            ),
            "memory_imported": int(state.get("memory_imported") or 0),
        }
        return result

    retry_key = f"{state['talker']}:{newest_id}"
    retry_state = context.send_failures.get(retry_key) or {}
    retry_after = float(retry_state.get("retry_after") or 0)
    if retry_after > now:
        result["retry_key"] = retry_key
        result["wait_action"] = {
            "agent": "watch",
            "contact_id": state["contact"].get("contact_id"),
            "display_name": _contact_label(state),
            "talker": state["talker"],
            "action": "retry_backoff",
            "newest_local_id": newest_id,
            "retry_after": retry_after,
            "attempts": int(retry_state.get("attempts") or 0),
        }
        return result
    result["retry_key"] = retry_key
    return result


async def draft_node(
    state: AutomationHubState,
    runtime: Any,
) -> dict[str, Any]:
    context: HubRuntimeContext = runtime.context
    started = time.perf_counter()
    retry_key = state.get("retry_key") or ""
    cached = context.candidate_cache.get(retry_key) if retry_key else None
    try:
        result = cached or await context.host.generate_reply(
            _contact(state),
            conversation_text(state.get("messages") or []),
            context.runtime,
        )
        if not cached and retry_key:
            context.candidate_cache[retry_key] = result
        status = "cached" if cached else "ok"
        error = ""
    except Exception as exc:  # noqa: BLE001 - policy will block empty output
        result = {"risk": {"level": "L0", "label": "普通聊天", "matched": []}, "candidates": []}
        status = "error"
        error = type(exc).__name__
    return {
        "result": result,
        "generation_error": error,
        "phase": "after_draft",
        "hub_trace": _append_hub_trace(
            state,
            task="draft",
            status=status,
            next_task="hub",
            reason_code="draft_error" if error else "draft_ready",
            started=started,
        ),
    }


def policy_node(
    state: AutomationHubState,
    runtime: Any,
) -> dict[str, Any]:
    context: HubRuntimeContext = runtime.context
    started = time.perf_counter()
    result = state.get("result") or {}
    risk = result.get("risk") or {"level": "L0", "label": "普通聊天", "matched": []}
    candidates = result.get("candidates") or []
    candidate = str((candidates[0] if candidates else {}).get("text") or "")
    candidate_options = [
        str(item.get("text") or "").strip()
        for item in candidates[:3]
        if str(item.get("text") or "").strip()
    ]
    response_plan = (result.get("dialogue") or {}).get("response_plan") or {}
    requires_confirmation = bool(response_plan) and (
        response_plan.get("action") == "acknowledge_then_explore"
        or float(response_plan.get("confidence") or 0) < 0.75
    )
    model_fallback = any(
        item.get("role") == "writer" and item.get("status") == "fallback"
        for item in (result.get("trace") or [])
    )
    contact_settings = _contact_settings(state)
    policy = evaluate_send_policy(
        candidate=candidate,
        risk_level=str(risk.get("level") or "L0"),
        auto_send_levels=contact_settings.auto_send_levels,
        requires_confirmation=requires_confirmation,
        provider=context.runtime.provider,
        model_fallback=model_fallback,
        dry_run=contact_settings.dry_run,
        enabled=contact_settings.enabled,
        real_send_acknowledged=contact_settings.real_send_acknowledged,
    )
    next_task: HubTask = (
        "operator"
        if policy.decision == "auto_send"
        else "queue"
        if policy.decision == "needs_confirmation"
        else "finish"
    )
    return {
        "policy": {"decision": policy.decision, "reason": policy.reason},
        "candidate": candidate,
        "candidate_options": candidate_options,
        "risk": risk,
        "action": "blocked" if policy.decision == "blocked" else "",
        "next_task": next_task,
        "phase": "after_policy",
        "hub_trace": _append_hub_trace(
            state,
            task="policy",
            status=policy.decision,
            next_task=next_task,
            reason_code=policy.reason,
            started=started,
        ),
    }


def operator_node(
    state: AutomationHubState,
    runtime: Any,
) -> dict[str, Any]:
    context: HubRuntimeContext = runtime.context
    started = time.perf_counter()
    candidate = state.get("candidate") or ""
    newest_id = int(state.get("newest_id") or 0)
    confirmation_id = context.worker._confirmation_id(state["talker"], newest_id, candidate)
    send_verified = False
    send_error = ""
    try:
        result = execute_send(
            display_name=_contact_label(state),
            talker=state["talker"],
            text=candidate,
            newest_local_id=newest_id,
        )
        send_verified = bool(result.get("send_verified"))
        send_error = str(result.get("send_error") or "")
    except Exception as exc:  # noqa: BLE001 - send failures are retryable
        send_error = str(exc)
    action = "sent" if send_verified else "send_unverified"
    if send_verified:
        context.candidate_cache.pop(state.get("retry_key") or "", None)
        context.send_failures.pop(state.get("retry_key") or "", None)
    else:
        failure = context.send_failures.setdefault(
            state.get("retry_key") or "",
            {"attempts": 0, "last_error": ""},
        )
        failure["attempts"] = int(failure.get("attempts") or 0) + 1
        failure["last_error"] = send_error
        failure["retry_after"] = context.host.time.time() + min(
            30.0, 3.0 * (2 ** min(failure["attempts"] - 1, 3))
        )
    return {
        "confirmation_id": confirmation_id,
        "action": action,
        "sent": send_verified,
        "send_verified": send_verified,
        "send_error": send_error,
        "advance_cursor": send_verified,
        "next_task": "finish",
        "hub_trace": _append_hub_trace(
            state,
            task="operator",
            status="ok" if send_verified else "error",
            next_task="finish",
            reason_code="send_verified" if send_verified else "send_unverified",
            started=started,
        ),
    }


def queue_node(
    state: AutomationHubState,
    runtime: Any,
) -> dict[str, Any]:
    context: HubRuntimeContext = runtime.context
    started = time.perf_counter()
    newest_id = int(state.get("newest_id") or 0)
    candidate = state.get("candidate") or ""
    confirmation_id = context.worker._confirmation_id(state["talker"], newest_id, candidate)
    context.worker._enqueue_confirmation(
        context.pending,
        confirmation_id=confirmation_id,
        contact=_contact(state),
        talker=state["talker"],
        incoming=state.get("incoming") or [],
        candidate=candidate,
        candidate_options=state.get("candidate_options") or [],
        risk=state.get("risk") or {},
        newest_id=newest_id,
        conversation=conversation_text(state.get("messages") or []),
        reason=str((state.get("policy") or {}).get("reason") or "needs_confirmation"),
    )
    return {
        "confirmation_id": confirmation_id,
        "action": "needs_confirmation",
        "sent": False,
        "send_verified": False,
        "send_error": "",
        "advance_cursor": True,
        "next_task": "finish",
        "hub_trace": _append_hub_trace(
            state,
            task="queue",
            status="ok",
            next_task="finish",
            reason_code=str((state.get("policy") or {}).get("reason") or "needs_confirmation"),
            started=started,
        ),
    }


def finish_node(
    state: AutomationHubState,
    runtime: Any,
) -> dict[str, Any]:
    context: HubRuntimeContext = runtime.context
    started = time.perf_counter()
    final_trace = _append_hub_trace(
        state,
        task="finish",
        status="ok",
        next_task="end",
        reason_code="event_recorded" if state.get("action") or state.get("wait_action") else "cycle_finished",
        started=started,
    )
    action = state.get("action") or ""
    event = dict(state.get("event") or {})
    wait_action = state.get("wait_action") or {}
    if not action and wait_action:
        action = str(wait_action.get("action") or "")
        event = wait_action

    if action in {"needs_confirmation", "blocked", "ignored", "baseline", "user_replied"}:
        context.candidate_cache.pop(state.get("retry_key") or "", None)
        context.send_failures.pop(state.get("retry_key") or "", None)
        context.reply_waits.pop(state["talker"], None)
    elif action == "send_unverified":
        context.reply_waits.setdefault(state["talker"], {})["takeover_ready"] = True
    elif action in {"sent", "confirmed_sent"}:
        context.reply_waits.pop(state["talker"], None)

    newest_id = int(state.get("newest_id") or 0)
    if newest_id and action not in {"waiting_for_user", "retry_backoff", "read_error"}:
        context.cursors[state["talker"]] = (
            newest_id if state.get("advance_cursor", True) else int(state.get("previous_id") or 0)
        )

    if action and not event.get("created_at"):
        event = {
            "created_at": context.host._now(),
            "agent": "hub"
            if action
            in {"baseline", "user_replied", "waiting_for_user", "retry_backoff", "read_error"}
            else "operator"
            if action in {"sent", "send_unverified"}
            else "policy",
            "contact_id": state["contact"].get("contact_id"),
            "display_name": _contact_label(state),
            "talker": state["talker"],
            "action": action,
        }
    if event:
        latest_hub_reason = next(
            (
                item.get("reason_code", "")
                for item in reversed(state.get("hub_trace") or [])
                if item.get("task") == "hub"
            ),
            "",
        )
        event = {
            **event,
            "orchestration_mode": "langgraph-hub",
            "hub_reason": latest_hub_reason,
            "hub_trace": final_trace,
        }
        if state.get("trigger_reason"):
            event.setdefault("trigger_reason", state["trigger_reason"])
        event.setdefault("chat_type", state["contact"].get("chat_type") or "private")
        if state.get("incoming"):
            event.setdefault("incoming", [message.get("text", "") for message in state["incoming"]])
        if state.get("risk"):
            event.setdefault("risk", state["risk"])
        if state.get("candidate") is not None:
            event.setdefault("candidate", state.get("candidate") or "")
        if state.get("action") in {"sent", "send_unverified", "needs_confirmation", "blocked"}:
            event.update(
                {
                    "sent": bool(state.get("sent")),
                    "send_verified": bool(state.get("send_verified")),
                    "send_error": str(state.get("send_error") or ""),
                    "dry_run": _contact_settings(state).dry_run,
                    "settings_scope": "contact",
                    "confirmation_id": state.get("confirmation_id") or "",
                    "newest_local_id": newest_id,
                    "memory_imported": int(state.get("memory_imported") or 0),
                }
            )
            result = state.get("result") or {}
            event["generation"] = {
                "provider": result.get("provider") or runtime.context.runtime.provider,
                "model_fallback": any(
                    item.get("role") == "writer" and item.get("status") == "fallback"
                    for item in (result.get("trace") or [])
                ),
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
            }
        # Preserve the existing event-log contract: transient Watch outcomes
        # (baseline/ignored/user_replied/waiting/read_error) are returned to the
        # caller but are not persisted as automation send events.
        if action in {"sent", "send_unverified", "needs_confirmation", "blocked"}:
            context.host.append_jsonl(context.host.AUTOMATION_EVENTS_FILE, event)

    return {
        "event": event,
        "action": action,
        "finished": True,
        "hub_trace": final_trace,
    }


def _route_from_hub(state: AutomationHubState) -> HubTask:
    return state.get("next_task") or "finish"


def _route_from_policy(state: AutomationHubState) -> HubTask:
    return state.get("next_task") or "finish"


_compiled_hub_graph = None


def build_automation_hub_graph(force_rebuild: bool = False):
    global _compiled_hub_graph
    if _compiled_hub_graph is not None and not force_rebuild:
        return _compiled_hub_graph
    graph = StateGraph(AutomationHubState, context_schema=HubRuntimeContext)
    graph.add_node("hub", hub_node)
    graph.add_node("watch_read", watch_read_node)
    graph.add_node("memory_sync", memory_sync_node)
    graph.add_node("watch_evaluate", watch_evaluate_node)
    graph.add_node("draft", draft_node)
    graph.add_node("policy", policy_node)
    graph.add_node("operator", operator_node)
    graph.add_node("queue", queue_node)
    graph.add_node("finish", finish_node)
    graph.add_edge(START, "hub")
    graph.add_conditional_edges(
        "hub",
        _route_from_hub,
        {
            "watch_read": "watch_read",
            "memory_sync": "memory_sync",
            "watch_evaluate": "watch_evaluate",
            "draft": "draft",
            "policy": "policy",
            "operator": "operator",
            "queue": "queue",
            "finish": "finish",
        },
    )
    graph.add_edge("watch_read", "hub")
    graph.add_edge("memory_sync", "hub")
    graph.add_edge("watch_evaluate", "hub")
    graph.add_edge("draft", "hub")
    graph.add_conditional_edges(
        "policy",
        _route_from_policy,
        {"operator": "operator", "queue": "queue", "finish": "finish"},
    )
    graph.add_edge("operator", "finish")
    graph.add_edge("queue", "finish")
    graph.add_edge("finish", END)
    _compiled_hub_graph = graph.compile(name="wechat_automation_hub")
    return _compiled_hub_graph


async def run_automation_hub(
    *,
    contact: Contact,
    contact_settings: AutoReplySettings,
    runtime: RuntimeSettings,
    worker: Any,
    host: Any,
    settings: AutoReplySettings,
    cursors: dict[str, Any],
    pending: list[dict[str, Any]],
    candidate_cache: dict[str, Any],
    send_failures: dict[str, Any],
    reply_waits: dict[str, Any],
    allow_reply: bool | None,
    catch_up_unanswered: bool,
    has_contact_override: bool = False,
) -> dict[str, Any]:
    context = HubRuntimeContext(
        host=host,
        worker=worker,
        runtime=runtime,
        settings=settings,
        cursors=cursors,
        pending=pending,
        candidate_cache=candidate_cache,
        send_failures=send_failures,
        reply_waits=reply_waits,
    )
    initial: AutomationHubState = {
        "contact": contact.model_dump(),
        "contact_settings": contact_settings.model_dump(),
        # Preserve the existing manual-check contract: a global setting can
        # keep memory sync running while an explicit contact override controls
        # whether that contact is eligible for a generated draft. The worker's
        # background loop still gates entry on the global enabled flag.
        "reply_enabled": bool(
            ((not has_contact_override) or contact_settings.enabled)
            if allow_reply is None
            else allow_reply and contact_settings.enabled
        ),
        "catch_up_unanswered": catch_up_unanswered,
        "talker": contact.wechat_username,
        "phase": "start",
        "advance_cursor": True,
        "hub_trace": [],
    }
    return await build_automation_hub_graph().ainvoke(initial, context=context)
