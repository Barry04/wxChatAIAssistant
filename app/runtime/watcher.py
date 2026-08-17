from typing import Any

from app.models import Contact
from app.runtime.messages import ordered_messages


def group_trigger_reason(
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


def load_timeline(host: Any, talker: str, catch_up_unanswered: bool) -> dict[str, Any]:
    if catch_up_unanswered:
        return host.get_full_timeline(talker, 50000)
    return host.get_timeline(talker, 30)


def inspect_incoming(
    *,
    contact: Contact,
    messages: list[dict[str, Any]],
    talker: str,
    catch_up_unanswered: bool,
    cursors: dict[str, Any],
    reply_waits: dict[str, Any],
    candidate_cache: dict[str, Any],
    send_failures: dict[str, Any],
    memory_imported: int,
) -> dict[str, Any]:
    """根据游标、群触发和本人已回复状态决定是否进入草稿。不生成、不发送。"""
    if not messages:
        return {"status": "empty"}

    newest_id = max(
        int((message.get("id") or {}).get("local_id") or 0) for message in messages
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
            return {
                "status": "skip",
                "action": {
                    "agent": "watch",
                    "contact_id": contact.contact_id,
                    "display_name": contact.display_name,
                    "talker": talker,
                    "action": "already_replied",
                    "newest_local_id": newest_id,
                    "memory_imported": memory_imported,
                },
            }
    elif previous_id == 0:
        cursors[talker] = newest_id
        return {
            "status": "skip",
            "action": {
                "agent": "watch",
                "contact_id": contact.contact_id,
                "talker": talker,
                "action": "baseline",
                "newest_local_id": newest_id,
                "memory_imported": memory_imported,
            },
        }
    else:
        new_messages = [
            message
            for message in messages
            if int((message.get("id") or {}).get("local_id") or 0) > previous_id
        ]
        if not new_messages:
            cursors[talker] = newest_id
            return {"status": "empty"}
        incoming = [
            message for message in new_messages if not message.get("is_from_me")
        ]
        if not incoming:
            reply_waits.pop(talker, None)
            cursors[talker] = newest_id
            return {"status": "empty"}

        own_new_messages = [
            message for message in new_messages if message.get("is_from_me")
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
                and int((message.get("id") or {}).get("local_id") or 0) > latest_own_id
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
                return {
                    "status": "skip",
                    "action": {
                        "agent": "watch",
                        "contact_id": contact.contact_id,
                        "display_name": contact.display_name,
                        "talker": talker,
                        "action": "user_replied",
                        "newest_local_id": newest_id,
                        "memory_imported": memory_imported,
                    },
                }
            reply_waits.pop(talker, None)

    trigger_reason = group_trigger_reason(contact, incoming)
    if not trigger_reason:
        cursors[talker] = newest_id
        return {
            "status": "skip",
            "action": {
                "agent": "watch",
                "contact_id": contact.contact_id,
                "display_name": contact.display_name,
                "talker": talker,
                "chat_type": contact.chat_type,
                "action": "ignored",
                "trigger_reason": "group_not_mentioned",
                "newest_local_id": newest_id,
                "memory_imported": memory_imported,
            },
        }

    return {
        "status": "ready",
        "messages": messages,
        "incoming": incoming,
        "newest_id": newest_id,
        "previous_id": previous_id,
        "trigger_reason": trigger_reason,
    }


def ordered_timeline_messages(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    return ordered_messages(timeline.get("messages", []))
