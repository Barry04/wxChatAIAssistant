from app.chat_analysis import analyze_chat_records
from app.wechat_cli_bridge import (
    get_full_timeline,
    recent_self_history,
    timeline_to_records,
)


def _message(local_id, timestamp, from_me, text, kind="text"):
    return {
        "id": {"local_id": local_id},
        "create_time": timestamp,
        "is_from_me": from_me,
        "text": text,
        "kind": kind,
    }


def test_timeline_to_records_groups_turns_and_keeps_metrics():
    messages = [
        _message(1, 100, False, "在吗"),
        _message(2, 110, False, "周末一起吃饭吗"),
        _message(3, 150, True, "可以"),
        _message(4, 155, True, "时间发我"),
        _message(5, 300, False, "好"),
        _message(6, 330, True, "收到", "emoji"),
    ]

    records = timeline_to_records(
        messages,
        "contact-a",
        "friend",
        "wxid-a",
        display_name="朋友 A",
    )

    assert len(records) == 2
    assert records[0]["incoming"] == ["在吗", "周末一起吃饭吗"]
    assert records[0]["my_reply"] == ["可以", "时间发我"]
    assert records[0]["scene"] == "invitation"
    assert records[0]["response_seconds"] == 40
    assert records[0]["incoming_times"] == [100, 110]
    assert records[0]["reply_kinds"] == ["text", "text"]
    assert records[1]["source_record_id"] == "wechat:wxid-a:6"


def test_chat_analysis_returns_aggregates_without_message_text():
    records = timeline_to_records(
        [
            _message(1, 100, False, "在吗"),
            _message(2, 130, True, "在呢？哈哈"),
            _message(3, 200, False, "发张图"),
            _message(4, 500, True, "", "image"),
        ],
        "contact-a",
        "friend",
        "wxid-a",
    )

    result = analyze_chat_records(records)

    assert result["record_count"] == 2
    assert result["median_response_seconds"] == 165
    assert result["under_1min_rate"] == 50
    assert result["question_rate"] == 50
    assert result["laughter_emoji_rate"] == 50
    assert result["message_types"]["image_rate"] == 25
    assert "incoming" not in result


def test_get_full_timeline_reads_pages_and_deduplicates(monkeypatch):
    import app.wechat_cli_bridge as module

    pages = {
        0: {
            "messages": [_message(1, 100, False, "a"), _message(2, 110, True, "b")],
            "query": {"has_more": True},
        },
        2: {
            "messages": [_message(2, 110, True, "b"), _message(3, 120, False, "c")],
            "query": {"has_more": False},
        },
    }
    monkeypatch.setattr(module, "get_timeline", lambda *_args, offset=0: pages[offset])

    result = get_full_timeline("wxid-a", max_messages=10, page_size=2)

    assert [item["id"]["local_id"] for item in result["messages"]] == [1, 2, 3]
    assert result["query"]["pages_read"] == 2
    assert result["query"]["messages_read"] == 3


def test_resolve_session_display_name_uses_stable_username(monkeypatch):
    import app.wechat_cli_bridge as module

    pages = {
        0: [
            {"username": "wxid-a", "display_name": "新备注"},
            {"username": "wxid-b", "display_name": "另一个人"},
        ]
    }
    monkeypatch.setattr(
        module,
        "list_sessions",
        lambda _limit, *, offset=0: pages.get(offset, []),
    )

    assert module.resolve_session_display_name("wxid-a", "旧备注") == "新备注"
    assert module.resolve_session_display_name("wxid-missing", "旧备注") == "旧备注"


def test_recent_self_history_slices_sessions_into_resumable_batches(monkeypatch):
    import app.wechat_cli_bridge as module

    sessions = [
        {"username": f"wxid-{index}", "display_name": f"联系人 {index}", "chat_type": "private"}
        for index in range(5)
    ]
    monkeypatch.setattr(
        module,
        "list_sessions",
        lambda _limit, *, offset=0: sessions[offset : offset + _limit],
    )
    monkeypatch.setattr(
        module,
        "get_full_timeline",
        lambda talker, _max_messages: {
            "messages": [_message(1, 100, False, talker), _message(2, 110, True, "ok")],
            "query": {"has_more": False},
        },
    )
    records, imported, batch = recent_self_history(
        session_limit=2,
        session_offset=2,
        messages_per_session=20,
        include_groups=False,
    )

    assert [item["username"] for item in imported] == ["wxid-2", "wxid-3"]
    assert len(records) == 2
    assert batch == {
        "session_offset": 2,
        "session_limit": 2,
        "session_end": 4,
        "total_sessions": 5,
        "has_next_batch": True,
        "failed_sessions": 0,
    }
