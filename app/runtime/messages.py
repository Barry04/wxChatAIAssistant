from typing import Any

from app.message_text import display_message_text


def ordered_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = list(enumerate(messages))

    def sort_key(item: tuple[int, dict[str, Any]]) -> tuple[int, int, int]:
        index, message = item
        local_id = int((message.get("id") or {}).get("local_id") or 0)
        create_time = int(message.get("create_time") or 0)
        return (local_id if local_id > 0 else 2**63 - 1, create_time, index)

    return [message for _, message in sorted(indexed, key=sort_key)]


def conversation_text(messages: list[dict[str, Any]]) -> str:
    rows = []
    for message in ordered_messages(messages)[-12:]:
        speaker = "我" if message.get("is_from_me") else "对方"
        rows.append(f"{speaker}: {display_message_text(message)}")
    return "\n".join(rows)
