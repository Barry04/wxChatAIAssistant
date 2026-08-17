import time
from typing import Any

from app.wechat_bridge import register_chat_identity, send_wechat_message
from app.wechat_cli_bridge import get_timeline


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


def execute_send(
    *,
    display_name: str,
    talker: str,
    text: str,
    newest_local_id: int,
) -> dict[str, Any]:
    """只发送调用方给出的已批准原文，不读取草稿、不改写文本。"""
    trace: list[dict[str, Any]] = []
    approved = str(text or "").strip()
    if not approved:
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
    try:
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
                talker,
                int(newest_local_id or 0),
                approved,
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
    except Exception as exc:
        send_error = str(exc)
        trace.append({"step": "send", "ok": False, "error": send_error})

    return {
        "ok": send_verified,
        "sent": send_verified,
        "send_verified": send_verified,
        "send_error": send_error,
        "selection": approved,
        "trace": trace,
    }
