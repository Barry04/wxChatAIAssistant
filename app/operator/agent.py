import time
from pathlib import Path
from typing import Any

from app.wechat_bridge import (
    register_chat_identity,
    send_wechat_files,
    send_wechat_mention,
    send_wechat_message,
    send_wechat_quote,
)
from app.wechat_cli_bridge import get_timeline

MEDIA_KINDS = {"image", "file", "video"}


def _is_media_message(message: dict[str, Any]) -> bool:
    kind = str(message.get("kind") or "")
    if kind in MEDIA_KINDS:
        return True
    text = str(message.get("text") or "")
    return any(token in text for token in ("[图片]", "[文件]", "[image]", "[file]"))


def verify_sent_message(
    talker: str,
    newest_id: int,
    candidate: str,
    *,
    attempts: int = 6,
    interval_seconds: float = 0.35,
) -> tuple[bool, str]:
    last_error = ""
    expected = candidate.strip()
    for attempt in range(attempts):
        try:
            verification = get_timeline(talker, 10)
            verified = any(
                message.get("is_from_me")
                and int((message.get("id") or {}).get("local_id") or 0) > newest_id
                and str(message.get("text") or "").strip() == expected
                for message in verification.get("messages", [])
            )
            if verified:
                return True, ""
        except Exception as exc:
            last_error = str(exc)
        if attempt < attempts - 1:
            time.sleep(interval_seconds)
    return False, last_error


def verify_sent_attachments(
    talker: str,
    newest_id: int,
    files: list[str],
    *,
    attempts: int = 6,
    interval_seconds: float = 0.35,
) -> tuple[bool, str]:
    last_error = ""
    expected = len(files)
    for attempt in range(attempts):
        try:
            verification = get_timeline(talker, 10)
            matched = sum(
                1
                for message in verification.get("messages", [])
                if message.get("is_from_me")
                and int((message.get("id") or {}).get("local_id") or 0) > newest_id
                and _is_media_message(message)
            )
            if matched >= expected:
                return True, ""
        except Exception as exc:
            last_error = str(exc)
        if attempt < attempts - 1:
            time.sleep(interval_seconds)
    return False, last_error


def execute_send(
    *,
    display_name: str,
    talker: str,
    text: str,
    newest_local_id: int,
    attachments: list[str] | None = None,
    quote_preview: str = "",
    quote_local_id: int = 0,
    at_names: list[str] | None = None,
) -> dict[str, Any]:
    """只发送调用方给出的已批准原文和附件，不读取草稿、不改写文本。"""
    trace: list[dict[str, Any]] = []
    approved = str(text or "").strip()
    files = [str(Path(path)) for path in (attachments or []) if str(path).strip()]
    quote_text = str(quote_preview or "").strip()
    wants_quote = bool(int(quote_local_id or 0) or quote_text)
    mention_names = [str(name).strip() for name in (at_names or []) if str(name).strip()]
    if any("所有人" in name or name.lower() == "all" for name in mention_names):
        trace.append(
            {
                "step": "authorize_session",
                "ok": False,
                "error": "at_all_not_supported",
            }
        )
        return {
            "ok": False,
            "sent": False,
            "send_verified": False,
            "send_error": "at_all_not_supported",
            "selection": approved,
            "trace": trace,
        }
    if wants_quote and not quote_text:
        trace.append(
            {
                "step": "authorize_session",
                "ok": False,
                "error": "quote_target_missing",
            }
        )
        return {
            "ok": False,
            "sent": False,
            "send_verified": False,
            "send_error": "quote_target_missing",
            "selection": approved,
            "trace": trace,
        }
    missing = [path for path in files if not Path(path).is_file()]
    if missing:
        trace.append(
            {
                "step": "authorize_session",
                "ok": False,
                "error": "unapproved_attachment",
            }
        )
        return {
            "ok": False,
            "sent": False,
            "send_verified": False,
            "send_error": "unapproved_attachment",
            "selection": approved,
            "trace": trace,
        }
    if not approved and not files:
        trace.append(
            {
                "step": "authorize_session",
                "ok": False,
                "error": "empty_text",
            }
        )
        return {
            "ok": False,
            "sent": False,
            "send_verified": False,
            "send_error": "empty_text",
            "selection": "",
            "trace": trace,
        }

    register_chat_identity(display_name, talker)
    trace.append({"step": "authorize_session", "ok": True})

    send_error = ""
    send_verified = False
    newest_id = int(newest_local_id or 0)
    try:
        if files:
            send_result = send_wechat_files(display_name, files)
            interface_sent = bool(send_result.get("sent"))
            trace.append(
                {
                    "step": "send",
                    "ok": interface_sent,
                    "error": "" if interface_sent else "微信发送接口未确认发送成功",
                }
            )
            if not interface_sent:
                return {
                    "ok": False,
                    "sent": False,
                    "send_verified": False,
                    "send_error": "微信发送接口未确认发送成功",
                    "selection": approved,
                    "trace": trace,
                }
            send_verified, send_error = verify_sent_attachments(
                talker, newest_id, files
            )
            trace.append(
                {
                    "step": "verify",
                    "ok": send_verified,
                    "error": send_error,
                }
            )
            if not send_verified:
                return {
                    "ok": False,
                    "sent": False,
                    "send_verified": False,
                    "send_error": send_error,
                    "selection": approved,
                    "trace": trace,
                }
        if approved:
            if mention_names:
                send_result = send_wechat_mention(
                    display_name,
                    mention_names,
                    approved,
                    quote_preview=quote_text if wants_quote else "",
                )
            elif wants_quote:
                send_result = send_wechat_quote(display_name, quote_text, approved)
            else:
                send_result = send_wechat_message(display_name, approved)
            interface_sent = bool(send_result.get("sent"))
            trace.append(
                {
                    "step": "send",
                    "ok": interface_sent,
                    "error": "" if interface_sent else "微信发送接口未确认发送成功",
                }
            )
            if interface_sent:
                send_verified, send_error = verify_sent_message(
                    talker, newest_id, approved
                )
                trace.append(
                    {
                        "step": "verify",
                        "ok": send_verified,
                        "error": send_error,
                    }
                )
            else:
                send_error = "微信发送接口未确认发送成功"
                send_verified = False
        elif files:
            send_verified = True
    except Exception as exc:
        send_error = str(exc)
        send_verified = False
        trace.append({"step": "send", "ok": False, "error": send_error})

    return {
        "ok": send_verified,
        "sent": send_verified,
        "send_verified": send_verified,
        "send_error": send_error,
        "selection": approved,
        "trace": trace,
    }
