import asyncio
import hashlib
import asyncio
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from .models import AutoReplySettings, Contact, RuntimeSettings
from .self_skill import distill_self_skill
from .services import (
    generate_reply,
    get_public_settings,
    import_raw_messages,
    import_records,
)
from .storage import (
    AUTOMATION_EVENTS_FILE,
    AUTOMATION_STATE_FILE,
    append_jsonl,
    load_auto_reply_config,
    load_contacts,
    read_json,
    write_json,
)
from .wechat_bridge import register_chat_identity, send_wechat_message
from .wechat_cli_bridge import (
    get_full_timeline,
    get_timeline,
    timeline_participant_count,
    timeline_to_raw_messages,
    timeline_to_records,
)

AUTO_SENDABLE_LEVELS = {"L0", "L1", "L2"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ordered_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = list(enumerate(messages))

    def sort_key(item: tuple[int, dict[str, Any]]) -> tuple[int, int, int]:
        index, message = item
        local_id = int((message.get("id") or {}).get("local_id") or 0)
        create_time = int(message.get("create_time") or 0)
        return (local_id if local_id > 0 else 2**63 - 1, create_time, index)

    return [message for _, message in sorted(indexed, key=sort_key)]


def _conversation_text(messages: list[dict[str, Any]]) -> str:
    rows = []
    for message in _ordered_messages(messages)[-12:]:
        speaker = "我" if message.get("is_from_me") else "对方"
        rows.append(f"{speaker}: {message.get('text') or '[' + str(message.get('kind')) + ']'}")
    return "\n".join(rows)


def _group_trigger_reason(
    contact: Contact,
    messages: list[dict[str, Any]],
) -> str:
    if contact.chat_type != "group":
        return "private_message"
    if contact.group_trigger_mode == "all_messages":
        return "group_all_messages"
    keywords = [
        keyword.strip().lower()
        for keyword in contact.group_mention_keywords
        if keyword.strip()
    ]
    for message in messages:
        if any(
            bool(message.get(field))
            for field in ("at_me", "mentioned_me", "is_mentioned")
        ):
            return "group_mention"
        text = str(message.get("text") or "")
        normalized = text.lower()
        if "@我" in text or "@all" in normalized or "所有人" in text:
            return "group_mention"
        if keywords and any(keyword in normalized for keyword in keywords):
            return "group_keyword"
    return ""


def _effective_settings(
    settings: AutoReplySettings,
    contact_id: str,
) -> AutoReplySettings:
    override = settings.contact_settings.get(contact_id)
    if not override:
        return settings
    values = settings.model_dump()
    values.pop("contact_settings", None)
    values.update(
        {
            key: value
            for key, value in override.model_dump().items()
            if value is not None
        }
    )
    values["contact_settings"] = settings.contact_settings
    return AutoReplySettings(**values)


def sync_timeline_to_memory(contact: Contact, timeline: dict[str, Any]) -> int:
    """Persist only completed turns; an unanswered incoming message is not training data."""
    messages = _ordered_messages(timeline.get("messages", []))
    import_raw_messages(
        timeline_to_raw_messages(
            messages,
            contact.contact_id,
            contact.relationship,
            contact.wechat_username,
            chat_type=contact.chat_type,
            display_name=contact.display_name,
            participant_count=contact.participant_count
            or timeline_participant_count(messages),
        )
    )
    records = timeline_to_records(
        messages,
        contact.contact_id,
        contact.relationship,
        contact.wechat_username,
        chat_type=contact.chat_type,
        display_name=contact.display_name,
        participant_count=contact.participant_count
        or timeline_participant_count(messages),
    )
    imported = import_records(records)
    if imported:
        distill_self_skill()
    return imported


class AutomationWorker:
    def __init__(self, api_key_provider: Callable[[], str]):
        self.api_key_provider = api_key_provider
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._manual_requested = threading.Event()
        self._lock = threading.Lock()
        self._running_cycle = False
        self._last_error = ""

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="wechat-auto-reply",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)

    def wake(self) -> None:
        self._wake.set()

    def status(self) -> dict[str, Any]:
        settings = AutoReplySettings(
            **load_auto_reply_config()
        )
        state = read_json(
            AUTOMATION_STATE_FILE,
            {
                "cursors": {},
                "pending_confirmations": [],
                "reply_waits": {},
                "paused": False,
            },
        )
        contact_guard_ready = any(
            bool(
                override.enabled
                and override.dry_run is False
                and override.real_send_acknowledged
            )
            for override in settings.contact_settings.values()
        )
        return {
            "worker_running": bool(self._thread and self._thread.is_alive()),
            "cycle_running": self._running_cycle,
            "last_error": self._last_error,
            "settings": settings.model_dump(),
            "cursor_count": len(state.get("cursors", {})),
            "paused": bool(state.get("paused", False)),
            "pending_confirmations": len(state.get("pending_confirmations", [])),
            "send_guard_ready": bool(
                settings.enabled
                and not settings.dry_run
                and settings.real_send_acknowledged
            ) or contact_guard_ready,
            "global_send_guard_ready": bool(
                settings.enabled
                and not settings.dry_run
                and settings.real_send_acknowledged
            ),
            "contact_send_guard_ready": contact_guard_ready,
            "contact_settings": {
                contact_id: value.model_dump()
                for contact_id, value in settings.contact_settings.items()
            },
            "last_run_at": state.get("last_run_at", ""),
        }

    @staticmethod
    def _confirmation_id(
        talker: str,
        newest_id: int,
        candidate: str,
    ) -> str:
        digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:12]
        return f"{talker}:{newest_id}:{digest}"

    @staticmethod
    def _verify_sent_message(
        talker: str,
        newest_id: int,
        candidate: str,
        *,
        attempts: int = 6,
        interval_seconds: float = 0.35,
    ) -> tuple[bool, str]:
        last_error = ""
        for attempt in range(attempts):
            try:
                verification = get_timeline(talker, 10)
                verified = any(
                    message.get("is_from_me")
                    and int(
                        (message.get("id") or {}).get("local_id") or 0
                    )
                    > newest_id
                    and str(message.get("text") or "").strip()
                    == candidate.strip()
                    for message in verification.get("messages", [])
                )
                if verified:
                    return True, ""
            except Exception as exc:
                last_error = str(exc)
            if attempt < attempts - 1:
                time.sleep(interval_seconds)
        return False, last_error

    @staticmethod
    def _enqueue_confirmation(
        pending: list[dict[str, Any]],
        *,
        confirmation_id: str,
        contact: Contact,
        talker: str,
        incoming: list[dict[str, Any]],
        candidate: str,
        candidate_options: list[str],
        risk: dict[str, Any],
        newest_id: int,
        conversation: str,
        reason: str,
    ) -> dict[str, Any]:
        existing = next(
            (item for item in pending if item.get("id") == confirmation_id),
            None,
        )
        if existing:
            return existing
        item = {
            "id": confirmation_id,
            "created_at": _now(),
            "contact_id": contact.contact_id,
            "display_name": contact.display_name,
            "talker": talker,
            "incoming": [message.get("text", "") for message in incoming],
            "candidate": candidate,
            "candidate_options": candidate_options[:3],
            "risk": risk,
            "newest_local_id": newest_id,
            "conversation": conversation,
            "reason": reason,
            "attempts": 0,
            "last_error": "",
        }
        pending.append(item)
        return item

    async def run_once(
        self,
        allow_reply: bool | None = None,
        *,
        catch_up_unanswered: bool = False,
        wait_for_cycle: bool = False,
        contact_id: str | None = None,
    ) -> dict[str, Any]:
        if wait_for_cycle:
            self._manual_requested.set()
            acquired = await asyncio.to_thread(
                self._lock.acquire,
                True,
                60,
            )
        else:
            if self._manual_requested.is_set():
                return {"processed": 0, "actions": [], "skipped": "manual_check_pending"}
            acquired = self._lock.acquire(blocking=False)
        if not acquired:
            if wait_for_cycle:
                self._manual_requested.clear()
            return {"processed": 0, "actions": [], "skipped": "cycle_already_running"}
        self._running_cycle = True
        try:
            return await self._run_once_locked(
                allow_reply,
                catch_up_unanswered,
                contact_id=contact_id,
            )
        finally:
            self._running_cycle = False
            self._lock.release()
            if wait_for_cycle:
                self._manual_requested.clear()

    async def _run_once_locked(
        self,
        allow_reply: bool | None = None,
        catch_up_unanswered: bool = False,
        *,
        contact_id: str | None = None,
    ) -> dict[str, Any]:
        settings = AutoReplySettings(
            **load_auto_reply_config()
        )
        contacts = [
            Contact(**item)
            for item in load_contacts()
            if (
                item.get("contact_id") in settings.allowed_contact_ids
                or item.get("contact_id") in settings.contact_settings
            )
            and (contact_id is None or item.get("contact_id") == contact_id)
            and item.get("wechat_username")
        ]
        state = read_json(
            AUTOMATION_STATE_FILE,
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
        stored = get_public_settings()
        runtime = RuntimeSettings(
            **{**stored, "api_key": self.api_key_provider()}
        )
        for contact in contacts:
            contact_settings = _effective_settings(settings, contact.contact_id)
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
                        get_full_timeline,
                        talker,
                        50000,
                    )
                else:
                    timeline = get_timeline(talker, 30)
            except Exception as exc:
                actions.append(
                    {
                        "contact_id": contact.contact_id,
                        "display_name": contact.display_name,
                        "talker": talker,
                        "action": "read_error",
                        "error": str(exc),
                    }
                )
                continue
            messages = _ordered_messages(timeline.get("messages", []))
            if not messages:
                continue
            memory_imported = (
                sync_timeline_to_memory(contact, timeline)
                if contact_settings.memory_sync_enabled
                else 0
            )
            newest_id = max(
                int((message.get("id") or {}).get("local_id") or 0)
                for message in messages
            )
            previous_id = int(cursors.get(talker) or 0)
            if catch_up_unanswered:
                last_own_index = max(
                    (
                        index
                        for index, message in enumerate(messages)
                        if message.get("is_from_me")
                    ),
                    default=-1,
                )
                incoming = [
                    message
                    for message in messages[last_own_index + 1 :]
                    if not message.get("is_from_me")
                ]
                if not incoming:
                    cursors[talker] = newest_id
                    reply_waits.pop(talker, None)
                    actions.append(
                        {
                            "contact_id": contact.contact_id,
                            "display_name": contact.display_name,
                            "talker": talker,
                            "action": "already_replied",
                            "newest_local_id": newest_id,
                            "memory_imported": memory_imported,
                        }
                    )
                    continue
            elif previous_id == 0:
                cursors[talker] = newest_id
                actions.append(
                    {
                        "contact_id": contact.contact_id,
                        "talker": talker,
                        "action": "baseline",
                        "newest_local_id": newest_id,
                        "memory_imported": memory_imported,
                    }
                )
                continue

            if not catch_up_unanswered:
                new_messages = [
                    message
                    for message in messages
                    if int((message.get("id") or {}).get("local_id") or 0)
                    > previous_id
                ]
                if not new_messages:
                    cursors[talker] = newest_id
                    continue
                incoming = [
                    message
                    for message in new_messages
                    if not message.get("is_from_me")
                ]
                if not incoming:
                    reply_waits.pop(talker, None)
                    cursors[talker] = newest_id
                    continue

                # A reply sent from the WeChat client must take priority over automation.
                own_new_messages = [
                    message
                    for message in new_messages
                    if message.get("is_from_me")
                ]
                if own_new_messages:
                    latest_own_id = max(
                        int((message.get("id") or {}).get("local_id") or 0)
                        for message in own_new_messages
                    )
                    incoming = [
                        message
                        for message in new_messages
                        if not message.get("is_from_me")
                        and int(
                            (message.get("id") or {}).get("local_id") or 0
                        )
                        > latest_own_id
                    ]
                    if not incoming:
                        reply_waits.pop(talker, None)
                        cursors[talker] = newest_id
                        stale_retry_keys = [
                            key
                            for key in set(candidate_cache) | set(send_failures)
                            if key.startswith(f"{talker}:")
                        ]
                        for key in stale_retry_keys:
                            candidate_cache.pop(key, None)
                            send_failures.pop(key, None)
                        actions.append(
                            {
                                "contact_id": contact.contact_id,
                                "display_name": contact.display_name,
                                "talker": talker,
                                "action": "user_replied",
                                "newest_local_id": newest_id,
                                "memory_imported": memory_imported,
                            }
                        )
                        continue
                    # A new incoming turn starts after the user's latest reply.
                    reply_waits.pop(talker, None)

            trigger_reason = _group_trigger_reason(contact, incoming)
            if not trigger_reason:
                cursors[talker] = newest_id
                actions.append(
                    {
                        "contact_id": contact.contact_id,
                        "display_name": contact.display_name,
                        "talker": talker,
                        "chat_type": contact.chat_type,
                        "action": "ignored",
                        "trigger_reason": "group_not_mentioned",
                        "newest_local_id": newest_id,
                        "memory_imported": memory_imported,
                    }
                )
                continue

            if not reply_enabled:
                continue

            wait = reply_waits.get(talker)
            now = time.time()
            if wait is None:
                wait = {
                    "started_at": now,
                    "incoming_id": int(
                        (incoming[0].get("id") or {}).get("local_id") or 0
                    ),
                    # The user explicitly requested a historical catch-up, so the
                    # normal delay intended to leave room for a manual reply has
                    # already elapsed by definition.
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
            if retry_after > time.time():
                actions.append(
                    {
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
                result = await generate_reply(
                    contact,
                    _conversation_text(messages),
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
            action = "blocked"
            sent = False
            send_verified = False
            send_error = ""
            advance_cursor = True
            if (
                candidate
                and risk_level in AUTO_SENDABLE_LEVELS
                and risk_level in contact_settings.auto_send_levels
                and not requires_confirmation
            ):
                confirmation_id = self._confirmation_id(
                    talker,
                    newest_id,
                    candidate,
                )
                if (
                    runtime.provider == "demo"
                    or model_fallback
                    or contact_settings.dry_run
                    or not contact_settings.enabled
                    or not contact_settings.real_send_acknowledged
                ):
                    action = "needs_confirmation"
                    reason = (
                        "demo_provider"
                        if runtime.provider == "demo"
                        else "model_fallback"
                        if model_fallback
                        else "dry_run"
                        if contact_settings.dry_run
                        else "real_send_not_acknowledged"
                    )
                    self._enqueue_confirmation(
                        pending,
                        confirmation_id=confirmation_id,
                        contact=contact,
                        talker=talker,
                        incoming=incoming,
                        candidate=candidate,
                        candidate_options=candidate_options,
                        risk=result["risk"],
                        newest_id=newest_id,
                        conversation=_conversation_text(messages),
                        reason=reason,
                    )
                else:
                    try:
                        register_chat_identity(contact.display_name, talker)
                        send_result = send_wechat_message(
                            contact.display_name,
                            candidate,
                        )
                        if send_result.get("sent"):
                            try:
                                verification = get_timeline(talker, 10)
                                send_verified = any(
                                    message.get("is_from_me")
                                    and int(
                                        (message.get("id") or {}).get("local_id") or 0
                                    )
                                    > newest_id
                                    and str(message.get("text") or "").strip()
                                    == candidate.strip()
                                    for message in verification.get("messages", [])
                                )
                            except Exception as exc:
                                send_error = f"发送后读取微信时间线失败：{exc}"
                                send_verified = False
                            if not send_verified:
                                send_verified, send_error = self._verify_sent_message(
                                    talker,
                                    newest_id,
                                    candidate,
                                )
                        else:
                            send_error = "微信发送接口未确认发送成功"
                    except Exception as exc:
                        send_error = str(exc)
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
                        failure["retry_after"] = time.time() + min(
                            30.0,
                            3.0 * (2 ** min(failure["attempts"] - 1, 3)),
                        )
            elif candidate:
                action = "needs_confirmation"
                confirmation_id = self._confirmation_id(
                    talker,
                    newest_id,
                    candidate,
                )
                self._enqueue_confirmation(
                    pending,
                    confirmation_id=confirmation_id,
                    contact=contact,
                    talker=talker,
                    incoming=incoming,
                    candidate=candidate,
                    candidate_options=candidate_options,
                    risk=result["risk"],
                    newest_id=newest_id,
                    conversation=_conversation_text(messages),
                    reason=(
                        "model_fallback"
                        if model_fallback
                        else "low_confidence_or_multi_message"
                        if requires_confirmation
                        else "risk_confirmation"
                    ),
                )

            if action in {"needs_confirmation", "blocked", "ignored"}:
                candidate_cache.pop(retry_key, None)
                send_failures.pop(retry_key, None)
                reply_waits.pop(talker, None)
            elif action == "send_unverified":
                # Retry an already-taken-over turn without starting another wait.
                reply_waits[talker] = {
                    **reply_waits.get(talker, {}),
                    "takeover_ready": True,
                }
            else:
                reply_waits.pop(talker, None)
            cursors[talker] = newest_id if advance_cursor else previous_id
            event = {
                "created_at": _now(),
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
            append_jsonl(AUTOMATION_EVENTS_FILE, event)
            actions.append(event)

        state["last_run_at"] = _now()
        write_json(AUTOMATION_STATE_FILE, state)
        self._last_error = ""
        return {"processed": len(contacts), "actions": actions}

    async def confirm(self, confirmation_id: str, text: str) -> dict[str, Any]:
        # 轮询与人工确认共用状态和发送通道；短暂等待轮询结束，避免误报锁竞争。
        if not self._lock.acquire(timeout=10):
            return {"ok": False, "error": "cycle_already_running"}
        try:
            settings = AutoReplySettings(
                **load_auto_reply_config()
            )
            state = read_json(
                AUTOMATION_STATE_FILE,
                {
                    "cursors": {},
                    "pending_confirmations": [],
                    "reply_waits": {},
                    "paused": False,
                },
            )
            pending = state.setdefault("pending_confirmations", [])
            item = next(
                (entry for entry in pending if entry.get("id") == confirmation_id),
                None,
            )
            if not item:
                return {"ok": False, "error": "confirmation_not_found"}
            contact_settings = _effective_settings(settings, item["contact_id"])
            if contact_settings.dry_run:
                return {"ok": False, "error": "dry_run_enabled"}
            if not contact_settings.real_send_acknowledged:
                return {"ok": False, "error": "real_send_not_acknowledged"}

            contacts = load_contacts()
            contact_data = next(
                (
                    entry
                    for entry in contacts
                    if entry.get("contact_id") == item.get("contact_id")
                ),
                None,
            )
            if not contact_data:
                item["last_error"] = "联系人不存在"
                return {"ok": False, "error": item["last_error"]}
            current_talker = str(contact_data.get("wechat_username") or "").strip()
            pending_talker = str(item.get("talker") or "").strip()
            if not current_talker or current_talker != pending_talker:
                item["last_error"] = "联系人微信会话绑定已变更，请重新生成待确认项"
                write_json(AUTOMATION_STATE_FILE, state)
                return {"ok": False, "error": "contact_binding_changed"}

            candidate = text.strip()
            item["attempts"] = int(item.get("attempts") or 0) + 1
            send_verified = False
            send_error = ""
            try:
                register_chat_identity(
                    str(item.get("display_name") or ""),
                    str(item.get("talker") or ""),
                )
                send_result = send_wechat_message(
                    str(contact_data.get("display_name") or item["display_name"]),
                    candidate,
                )
                if send_result.get("sent"):
                    send_verified, send_error = self._verify_sent_message(
                        str(item["talker"]),
                        int(item.get("newest_local_id") or 0),
                        candidate,
                    )
                else:
                    send_error = "微信发送接口未确认发送成功"
            except Exception as exc:
                send_error = str(exc)

            if send_verified:
                pending[:] = [
                    entry
                    for entry in pending
                    if entry.get("id") != confirmation_id
                ]
                event = {
                    **item,
                    "chat_type": contact_data.get("chat_type") or "private",
                    "candidate": candidate,
                    "action": "confirmed_sent",
                    "sent": True,
                    "send_verified": True,
                    "send_error": "",
                    "confirmed_at": _now(),
                }
                append_jsonl(AUTOMATION_EVENTS_FILE, event)
                write_json(AUTOMATION_STATE_FILE, state)
                return {"ok": True, "action": "confirmed_sent", "event": event}

            item["last_error"] = send_error or "发送后未在微信时间线中验证到消息"
            event = {
                **item,
                "candidate": candidate,
                "action": "send_unverified",
                "sent": False,
                "send_verified": False,
                "send_error": item["last_error"],
            }
            append_jsonl(AUTOMATION_EVENTS_FILE, event)
            write_json(AUTOMATION_STATE_FILE, state)
            return {"ok": False, "action": "send_unverified", "event": event}
        finally:
            self._lock.release()

    def discard_confirmation(self, confirmation_id: str) -> dict[str, Any]:
        state = read_json(
            AUTOMATION_STATE_FILE,
            {
                "cursors": {},
                "pending_confirmations": [],
                "reply_waits": {},
                "paused": False,
            },
        )
        pending = state.setdefault("pending_confirmations", [])
        before = len(pending)
        state["pending_confirmations"] = [
            item for item in pending if item.get("id") != confirmation_id
        ]
        if len(state["pending_confirmations"]) == before:
            return {"deleted": False}
        write_json(AUTOMATION_STATE_FILE, state)
        return {"deleted": True, "confirmation_id": confirmation_id}

    def set_paused(self, paused: bool) -> dict[str, Any]:
        with self._lock:
            state = read_json(
                AUTOMATION_STATE_FILE,
                {
                    "cursors": {},
                    "pending_confirmations": [],
                    "reply_waits": {},
                    "paused": False,
                },
            )
            state["paused"] = paused
            write_json(AUTOMATION_STATE_FILE, state)
        self.wake()
        return {"paused": paused}

    def reset_cursors(self, contact_id: str | None = None) -> dict[str, Any]:
        state = read_json(
            AUTOMATION_STATE_FILE,
            {"cursors": {}, "pending_confirmations": [], "paused": False},
        )
        if contact_id:
            contacts = load_contacts()
            contact = next(
                (item for item in contacts if item.get("contact_id") == contact_id),
                None,
            )
            if not contact or not contact.get("wechat_username"):
                return {"reset": False, "error": "联系人或微信会话不存在"}
            state.setdefault("cursors", {}).pop(contact["wechat_username"], None)
            state.setdefault("reply_waits", {}).pop(contact["wechat_username"], None)
            reset = [contact_id]
        else:
            state["cursors"] = {}
            state["reply_waits"] = {}
            reset = "all"
        write_json(AUTOMATION_STATE_FILE, state)
        return {"reset": True, "contacts": reset}

    def _loop(self) -> None:
        while not self._stop.is_set():
            settings = AutoReplySettings(
                **load_auto_reply_config()
            )
            state = read_json(
                AUTOMATION_STATE_FILE,
                {"cursors": {}, "pending_confirmations": [], "paused": False},
            )
            if (
                not self._manual_requested.is_set()
                and not state.get("paused")
                and (
                settings.memory_sync_enabled
                or settings.enabled
                or bool(settings.contact_settings)
                )
            ):
                try:
                    asyncio.run(self.run_once())
                except Exception as exc:
                    self._last_error = str(exc)
                    append_jsonl(
                        AUTOMATION_EVENTS_FILE,
                        {
                            "created_at": _now(),
                            "action": "error",
                            "error": str(exc),
                        },
                    )
            self._wake.wait(timeout=settings.poll_interval_seconds)
            self._wake.clear()
