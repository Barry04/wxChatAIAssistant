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


def test_execute_send_rejects_missing_attachments(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_message",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("未批准附件不得发送")),
    )

    result = execute_send(
        display_name="联系人甲",
        talker="wxid-a",
        text="",
        newest_local_id=6,
        attachments=[str(tmp_path / "missing.png")],
    )

    assert result["ok"] is False
    assert result["sent"] is False
    assert result["send_error"] == "unapproved_attachment"


def test_execute_send_sends_approved_image_and_file(monkeypatch, tmp_path):
    image = tmp_path / "photo.png"
    document = tmp_path / "notes.txt"
    image.write_bytes(b"png")
    document.write_text("hello", encoding="utf-8")
    sent_files: list[str] = []
    monkeypatch.setattr(
        "app.operator.agent.register_chat_identity",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_files",
        lambda _name, paths: sent_files.extend(paths) or {"sent": True},
    )
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_message",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("纯附件不得走文本发送")
        ),
    )
    monkeypatch.setattr(
        "app.operator.agent.get_timeline",
        lambda *_args: {
            "messages": [
                {"id": {"local_id": 7}, "is_from_me": True, "text": "", "kind": "image"},
                {
                    "id": {"local_id": 8},
                    "is_from_me": True,
                    "text": "notes.txt",
                    "kind": "file",
                },
            ]
        },
    )

    result = execute_send(
        display_name="联系人甲",
        talker="wxid-a",
        text="",
        newest_local_id=6,
        attachments=[str(image), str(document)],
    )

    assert result["ok"] is True
    assert result["send_verified"] is True
    assert sent_files == [str(image), str(document)]


def test_execute_send_aborts_media_when_session_verify_fails(monkeypatch, tmp_path):
    image = tmp_path / "photo.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(
        "app.operator.agent.register_chat_identity",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_files",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("OCR 标题验证失败")
        ),
    )

    result = execute_send(
        display_name="联系人甲",
        talker="wxid-a",
        text="附一张图",
        newest_local_id=6,
        attachments=[str(image)],
    )

    assert result["ok"] is False
    assert result["sent"] is False
    assert "OCR 标题验证失败" in result["send_error"]


def test_execute_send_quotes_target_instead_of_plain_send(monkeypatch):
    quoted = []
    monkeypatch.setattr(
        "app.operator.agent.register_chat_identity",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_quote",
        lambda name, preview, text: quoted.append((name, preview, text))
        or {"sent": True},
    )
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_message",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("引用失败时不得改走普通发送")
        ),
    )
    monkeypatch.setattr(
        "app.operator.agent.get_timeline",
        lambda *_args: {"messages": [_message(8, True, "收到")]},
    )

    result = execute_send(
        display_name="联系人甲",
        talker="wxid-a",
        text="收到",
        newest_local_id=6,
        quote_preview="周末一起吃饭吗",
        quote_local_id=6,
    )

    assert result["ok"] is True
    assert quoted == [("联系人甲", "周末一起吃饭吗", "收到")]


def test_execute_send_does_not_fallback_when_quote_target_missing(monkeypatch):
    monkeypatch.setattr(
        "app.operator.agent.register_chat_identity",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_quote",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("找不到可引用气泡")
        ),
    )
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_message",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("找不到引用目标时不得普通发送")
        ),
    )

    result = execute_send(
        display_name="联系人甲",
        talker="wxid-a",
        text="收到",
        newest_local_id=6,
        quote_preview="周末一起吃饭吗",
        quote_local_id=6,
    )

    assert result["ok"] is False
    assert result["sent"] is False
    assert "找不到可引用气泡" in result["send_error"]


def test_execute_send_mentions_group_member_instead_of_plain_at_text(monkeypatch):
    mentioned = []
    monkeypatch.setattr(
        "app.operator.agent.register_chat_identity",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_mention",
        lambda name, at_names, text, **_kwargs: mentioned.append((name, at_names, text))
        or {"sent": True},
    )
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_message",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("@ 失败时不得改走纯文本")
        ),
    )
    monkeypatch.setattr(
        "app.operator.agent.get_timeline",
        lambda *_args: {"messages": [_message(8, True, "收到")]},
    )

    result = execute_send(
        display_name="测试群",
        talker="group-a",
        text="收到",
        newest_local_id=6,
        at_names=["张三"],
    )

    assert result["ok"] is True
    assert mentioned == [("测试群", ["张三"], "收到")]


def test_execute_send_rejects_at_all(monkeypatch):
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_mention",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("不得发送@所有人")
        ),
    )
    monkeypatch.setattr(
        "app.operator.agent.send_wechat_message",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("不得发送@所有人")
        ),
    )

    result = execute_send(
        display_name="测试群",
        talker="group-a",
        text="收到",
        newest_local_id=6,
        at_names=["所有人"],
    )

    assert result["ok"] is False
    assert result["send_error"] == "at_all_not_supported"


def test_agent_package_has_no_wechat_send_dependency():
    root = Path("app/agent")
    forbidden = ("send_wechat_message", "wechat_bridge")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path} 不应依赖 {token}"
