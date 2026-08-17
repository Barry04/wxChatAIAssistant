import asyncio
import hashlib
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from .models import AutoReplySettings, Contact
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
from .wechat_cli_bridge import (
    get_full_timeline,
    get_timeline,
    timeline_participant_count,
    timeline_to_raw_messages,
    timeline_to_records,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    from .runtime.messages import ordered_messages

    messages = ordered_messages(timeline.get("messages", []))
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
        settings = AutoReplySettings(**load_auto_reply_config())
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
            )
            or contact_guard_ready,
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
        from app import automation as host
        from .runtime.orchestrator import run_cycle

        return await run_cycle(
            self,
            host,
            allow_reply,
            catch_up_unanswered,
            contact_id=contact_id,
        )

    async def confirm(self, confirmation_id: str, text: str) -> dict[str, Any]:
        from .operator.agent import execute_send

        # 轮询与人工确认共用状态和发送通道；短暂等待轮询结束，避免误报锁竞争。
        if not self._lock.acquire(timeout=10):
            return {"ok": False, "error": "cycle_already_running"}
        try:
            settings = AutoReplySettings(**load_auto_reply_config())
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
            try:
                operator_result = execute_send(
                    display_name=str(
                        contact_data.get("display_name") or item["display_name"]
                    ),
                    talker=str(item.get("talker") or ""),
                    text=candidate,
                    newest_local_id=int(item.get("newest_local_id") or 0),
                )
            except Exception as exc:
                operator_result = {
                    "send_verified": False,
                    "send_error": str(exc),
                    "selection": candidate,
                }
            send_verified = bool(operator_result.get("send_verified"))
            send_error = str(operator_result.get("send_error") or "")

            if send_verified:
                pending[:] = [
                    entry
                    for entry in pending
                    if entry.get("id") != confirmation_id
                ]
                event = {
                    **item,
                    "agent": "operator",
                    "chat_type": contact_data.get("chat_type") or "private",
                    "candidate": operator_result.get("selection") or candidate,
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
                "agent": "operator",
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
            settings = AutoReplySettings(**load_auto_reply_config())
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
                            "agent": "watch",
                            "action": "error",
                            "error": str(exc),
                        },
                    )
            self._wake.wait(timeout=settings.poll_interval_seconds)
            self._wake.clear()
