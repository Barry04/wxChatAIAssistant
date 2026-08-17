from pathlib import Path

from app.operator.agent import execute_send, verify_sent_message


def _message(local_id, from_me, text):
    return {
        "id": {"local_id": local_id},
        "is_from_me": from_me,
        "text": text,
        "kind": "text",
    }


def test_execute_send_verifies_outgoing_message(monkeypatch):
    monkeypatch.setattr(
        "app.operator.agent.register_chat_identity",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_message",
        lambda *_args: {"sent": True},
    )
    monkeypatch.setattr(
        "app.operator.agent.get_timeline",
        lambda *_args: {"messages": [_message(7, True, "已批准回复")]},
    )

    result = execute_send(
        display_name="联系人甲",
        talker="wxid-a",
        text="已批准回复",
        newest_local_id=6,
    )

    assert result["ok"] is True
    assert result["sent"] is True
    assert result["send_verified"] is True
    assert result["selection"] == "已批准回复"
    assert [item["step"] for item in result["trace"]] == [
        "authorize_session",
        "send",
        "verify",
    ]


def test_execute_send_records_interface_failure(monkeypatch):
    monkeypatch.setattr(
        "app.operator.agent.register_chat_identity",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_message",
        lambda *_args: {"sent": False},
    )
    monkeypatch.setattr(
        "app.operator.agent.get_timeline",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("未确认发送时不得回读时间线")
        ),
    )

    result = execute_send(
        display_name="联系人甲",
        talker="wxid-a",
        text="已批准回复",
        newest_local_id=6,
    )

    assert result["ok"] is False
    assert result["send_verified"] is False
    assert result["send_error"] == "微信发送接口未确认发送成功"


def test_execute_send_unverified_when_timeline_missing(monkeypatch):
    monkeypatch.setattr(
        "app.operator.agent.register_chat_identity",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_message",
        lambda *_args: {"sent": True},
    )
    monkeypatch.setattr(
        "app.operator.agent.get_timeline",
        lambda *_args: {"messages": [_message(6, False, "incoming")]},
    )
    monkeypatch.setattr("app.operator.agent.time.sleep", lambda *_args: None)

    result = execute_send(
        display_name="联系人甲",
        talker="wxid-a",
        text="已批准回复",
        newest_local_id=6,
    )

    assert result["ok"] is False
    assert result["send_verified"] is False
    assert result["selection"] == "已批准回复"


def test_execute_send_rejects_empty_text(monkeypatch):
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_message",
        lambda *_args: (_ for _ in ()).throw(AssertionError("空文本不得发送")),
    )

    result = execute_send(
        display_name="联系人甲",
        talker="wxid-a",
        text="   ",
        newest_local_id=6,
    )

    assert result["ok"] is False
    assert result["send_error"] == "empty_text"
    assert result["selection"] == ""


def test_verify_sent_message_retries_after_timeline_error(monkeypatch):
    calls = []

    def timeline_with_transient_error(*_args):
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("temporary timeline error")
        return {"messages": [_message(7, True, "candidate reply")]}

    monkeypatch.setattr(
        "app.operator.agent.get_timeline",
        timeline_with_transient_error,
    )
    monkeypatch.setattr("app.operator.agent.time.sleep", lambda *_args: None)

    verified, error = verify_sent_message(
        "wxid-a",
        6,
        "candidate reply",
        attempts=2,
        interval_seconds=0,
    )

    assert verified is True
    assert error == ""
    assert len(calls) == 2


def test_agent_package_has_no_wechat_send_dependency():
    root = Path("app/agent")
    forbidden = ("send_wechat_message", "wechat_bridge")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path} 不应依赖 {token}"
