from typing import Any

KIND_LABELS = {
    "image": "图片",
    "file": "文件",
    "emoji": "表情",
    "sticker": "表情",
    "voice": "语音",
    "video": "视频",
    "call": "通话",
}


def display_message_text(message: dict[str, Any]) -> str:
    text = str(message.get("text") or "").strip()
    if text:
        return text
    kind = str(message.get("kind") or "消息")
    return f"[{KIND_LABELS.get(kind, kind)}]"
