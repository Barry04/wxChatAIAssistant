import asyncio
import json
import asyncio
import threading
import time

from app.automation import AutomationWorker
from app.models import Contact


def _message(local_id, from_me, text):
    return {
        "id": {"local_id": local_id},
        "is_from_me": from_me,
        "text": text,
        "kind": "text",
    }


def _update_auto_reply(**updates):
    import app.storage as storage

    settings = storage.load_auto_reply_config()
    settings.update(updates)
    storage.save_auto_reply_config(settings)


def _update_first_contact(**updates):
    import app.storage as storage

    contacts = storage.load_contacts()
    contacts[0].update(updates)
    storage.save_contacts(contacts)


def _configure(
    monkeypatch,
    tmp_path,
    *,
    allowed=True,
    cursor=0,
    level="L0",
    dry_run=True,
    acknowledged=False,
    provider="demo",
    takeover_delay_seconds=0,
):
    import app.automation as module
    import app.storage as storage

    contacts_file = tmp_path / "contacts.json"
    settings_file = tmp_path / "settings.json"
    state_file = tmp_path / "state.json"
    events_file = tmp_path / "events.jsonl"
    contacts_file.write_text(
        json.dumps(
            [
                {
                    "contact_id": "contact-a",
                    "display_name": "Contact A",
                    "relationship": "friend",
                    "wechat_username": "wxid-a",
                }
            ]
        ),
        encoding="utf-8",
    )
    settings_file.write_text(
        json.dumps(
            {
                "memory_sync_enabled": True,
                "enabled": False,
                "dry_run": dry_run,
                "real_send_acknowledged": acknowledged,
                "poll_interval_seconds": 3,
                "takeover_delay_seconds": takeover_delay_seconds,
                "allowed_contact_ids": ["contact-a"] if allowed else [],
                "auto_send_levels": ["L0"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(storage, "CONFIG_DB_FILE", tmp_path / "config.sqlite3")
    storage.initialize_config_storage(seed_demo_contacts=False)
    storage.save_contacts(
        [
            {
                "contact_id": "contact-a",
                "display_name": "Contact A",
                "relationship": "friend",
                "wechat_username": "wxid-a",
            }
        ]
    )
    storage.save_auto_reply_config(
        {
            "memory_sync_enabled": True,
            "enabled": False,
            "dry_run": dry_run,
            "real_send_acknowledged": acknowledged,
            "poll_interval_seconds": 3,
            "takeover_delay_seconds": takeover_delay_seconds,
            "allowed_contact_ids": ["contact-a"] if allowed else [],
            "auto_send_levels": ["L0"],
            "contact_settings": {},
        }
    )
    state_file.write_text(
        json.dumps({"cursors": {"wxid-a": cursor} if cursor else {}}),
        encoding="utf-8",
    )
    events_file.touch()
    monkeypatch.setattr(module, "AUTOMATION_STATE_FILE", state_file)
    monkeypatch.setattr(module, "AUTOMATION_EVENTS_FILE", events_file)
    monkeypatch.setattr(
        module,
        "get_public_settings",
        lambda: {
            "provider": provider,
            "base_url": "http://127.0.0.1:11434",
            "model": "demo",
        },
    )

    async def fake_generate(*_args, **_kwargs):
        candidates = [] if level == "L3" else [{"text": "candidate reply"}]
        return {
            "risk": {"level": level, "label": level, "matched": []},
            "candidates": candidates,
        }

    monkeypatch.setattr(module, "generate_reply", fake_generate)
    monkeypatch.setattr(module, "sync_timeline_to_memory", lambda *_args: 0)
    return module, state_file, events_file


def test_first_cycle_only_builds_baseline(monkeypatch, tmp_path):
    module, state_file, _ = _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {"messages": [_message(9, False, "incoming")]},
    )

    result = asyncio.run(AutomationWorker(lambda: "").run_once())

    assert result["actions"][0]["action"] == "baseline"
    assert json.loads(state_file.read_text())["cursors"]["wxid-a"] == 9


def test_manual_check_finds_historical_unanswered_messages(
    monkeypatch, tmp_path
):
    module, _, _ = _configure(monkeypatch, tmp_path, cursor=99)
    captured = {}

    async def fake_generate(_contact, conversation, _settings):
        captured["conversation"] = conversation
        return {
            "risk": {"level": "L0", "label": "L0", "matched": []},
            "candidates": [{"text": "candidate reply"}],
        }

    monkeypatch.setattr(module, "generate_reply", fake_generate)
    monkeypatch.setattr(
        module,
        "get_full_timeline",
        lambda *_args, **_kwargs: {
            "messages": [
                _message(1, False, "old message"),
                _message(2, True, "my old reply"),
                _message(3, False, "unanswered one"),
                _message(4, False, "unanswered two"),
            ]
        },
    )
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("manual check must use full timeline")
        ),
    )

    result = asyncio.run(
        AutomationWorker(lambda: "").run_once(catch_up_unanswered=True)
    )

    assert result["actions"][0]["action"] == "needs_confirmation"
    assert result["actions"][0]["incoming"] == [
        "unanswered one",
        "unanswered two",
    ]
    assert "unanswered two" in captured["conversation"]


def test_manual_check_only_reads_requested_contact(monkeypatch, tmp_path):
    module, _, _ = _configure(monkeypatch, tmp_path, cursor=99)
    monkeypatch.setattr(
        module,
        "load_contacts",
        lambda: [
            {"contact_id": "contact-a", "display_name": "A", "relationship": "friend", "wechat_username": "wxid-a"},
            {"contact_id": "contact-b", "display_name": "B", "relationship": "friend", "wechat_username": "wxid-b"},
        ],
    )
    monkeypatch.setattr(
        module,
        "load_auto_reply_config",
        lambda: {"enabled": False, "dry_run": True, "allowed_contact_ids": ["contact-a", "contact-b"], "contact_settings": {}},
    )
    checked = []
    monkeypatch.setattr(
        module,
        "get_full_timeline",
        lambda talker, *_args, **_kwargs: checked.append(talker) or {"messages": [_message(1, True, "old reply")]},
    )

    result = asyncio.run(
        AutomationWorker(lambda: "").run_once(
            catch_up_unanswered=True, contact_id="contact-b"
        )
    )

    assert result["processed"] == 1
    assert checked == ["wxid-b"]


def test_manual_check_bypasses_takeover_delay(monkeypatch, tmp_path):
    module, _, _ = _configure(
        monkeypatch, tmp_path, cursor=99, takeover_delay_seconds=300
    )
    monkeypatch.setattr(
        module,
        "get_full_timeline",
        lambda *_args, **_kwargs: {
            "messages": [
                _message(1, True, "my old reply"),
                _message(2, False, "yesterday unanswered"),
            ]
        },
    )

    result = asyncio.run(
        AutomationWorker(lambda: "").run_once(catch_up_unanswered=True)
    )

    assert result["actions"][0]["action"] == "needs_confirmation"


def test_timeline_read_failure_does_not_stop_other_contacts(monkeypatch, tmp_path):
    module, _, _ = _configure(monkeypatch, tmp_path, cursor=99)
    monkeypatch.setattr(
        module,
        "load_contacts",
        lambda: [
            {
                "contact_id": "contact-a",
                "display_name": "Broken contact",
                "relationship": "friend",
                "wechat_username": "broken-wxid",
            },
            {
                "contact_id": "contact-b",
                "display_name": "Working contact",
                "relationship": "friend",
                "wechat_username": "working-wxid",
            },
        ],
    )
    monkeypatch.setattr(
        module,
        "load_auto_reply_config",
        lambda: {
            "enabled": False,
            "dry_run": True,
            "real_send_acknowledged": False,
            "allowed_contact_ids": ["contact-a", "contact-b"],
            "contact_settings": {},
        },
    )

    def full_timeline(talker, *_args, **_kwargs):
        if talker == "broken-wxid":
            raise RuntimeError("cache index unavailable")
        return {
            "messages": [
                _message(1, True, "my old reply"),
                _message(2, False, "yesterday unanswered"),
            ]
        }

    monkeypatch.setattr(module, "get_full_timeline", full_timeline)

    result = asyncio.run(
        AutomationWorker(lambda: "").run_once(catch_up_unanswered=True)
    )

    assert [item["action"] for item in result["actions"]] == [
        "read_error",
        "needs_confirmation",
    ]


def test_waits_before_generating_and_then_takes_over(monkeypatch, tmp_path):
    module, state_file, _ = _configure(
        monkeypatch, tmp_path, cursor=5, takeover_delay_seconds=300
    )
    current_time = [1000.0]
    generated = []
    monkeypatch.setattr(module.time, "time", lambda: current_time[0])
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {"messages": [_message(6, False, "incoming")]},
    )
    monkeypatch.setattr(
        module,
        "generate_reply",
        lambda *_args, **_kwargs: generated.append(True),
    )

    first = asyncio.run(AutomationWorker(lambda: "").run_once())
    assert first["actions"][0]["action"] == "waiting_for_user"
    assert generated == []
    assert json.loads(state_file.read_text())["cursors"]["wxid-a"] == 5

    current_time[0] = 1301.0
    module_result = {
        "risk": {"level": "L0", "label": "L0", "matched": []},
        "candidates": [{"text": "candidate reply"}],
    }

    async def generate(*_args, **_kwargs):
        generated.append(True)
        return module_result

    monkeypatch.setattr(module, "generate_reply", generate)
    second = asyncio.run(AutomationWorker(lambda: "").run_once())
    assert second["actions"][0]["action"] == "needs_confirmation"
    assert generated == [True]


def test_user_reply_cancels_takeover_without_generation(monkeypatch, tmp_path):
    module, state_file, _ = _configure(
        monkeypatch, tmp_path, cursor=5, takeover_delay_seconds=300
    )
    current_time = [1000.0]
    generated = []
    monkeypatch.setattr(module.time, "time", lambda: current_time[0])
    timelines = iter(
        [
            {"messages": [_message(6, False, "incoming")]},
            {
                "messages": [
                    _message(6, False, "incoming"),
                    _message(7, True, "my reply"),
                ]
            },
        ]
    )
    monkeypatch.setattr(module, "get_timeline", lambda *_args: next(timelines))
    monkeypatch.setattr(
        module,
        "generate_reply",
        lambda *_args, **_kwargs: generated.append(True),
    )

    first = asyncio.run(AutomationWorker(lambda: "").run_once())
    second = asyncio.run(AutomationWorker(lambda: "").run_once())
    state = json.loads(state_file.read_text())
    assert first["actions"][0]["action"] == "waiting_for_user"
    assert second["actions"][0]["action"] == "user_replied"
    assert generated == []
    assert state["cursors"]["wxid-a"] == 7
    assert state["reply_waits"] == {}


def test_follow_up_message_does_not_reset_wait_timer(monkeypatch, tmp_path):
    module, state_file, _ = _configure(
        monkeypatch, tmp_path, cursor=5, takeover_delay_seconds=300
    )
    current_time = [1000.0]
    monkeypatch.setattr(module.time, "time", lambda: current_time[0])
    timelines = iter(
        [
            {"messages": [_message(6, False, "first")]},
            {
                "messages": [
                    _message(6, False, "first"),
                    _message(7, False, "follow-up"),
                ]
            },
        ]
    )
    monkeypatch.setattr(module, "get_timeline", lambda *_args: next(timelines))
    first = asyncio.run(AutomationWorker(lambda: "").run_once())
    second = asyncio.run(AutomationWorker(lambda: "").run_once())
    state = json.loads(state_file.read_text())
    assert first["actions"][0]["action"] == "waiting_for_user"
    assert second["actions"][0]["action"] == "waiting_for_user"
    assert state["reply_waits"]["wxid-a"]["started_at"] == 1000.0


def test_new_incoming_after_user_reply_starts_a_new_wait(monkeypatch, tmp_path):
    module, state_file, _ = _configure(
        monkeypatch, tmp_path, cursor=5, takeover_delay_seconds=300
    )
    current_time = [1000.0]
    monkeypatch.setattr(module.time, "time", lambda: current_time[0])
    timelines = iter(
        [
            {"messages": [_message(6, False, "first")]},
            {
                "messages": [
                    _message(6, False, "first"),
                    _message(7, True, "my reply"),
                ]
            },
            {
                "messages": [
                    _message(6, False, "first"),
                    _message(7, True, "my reply"),
                    _message(8, False, "new incoming"),
                ]
            },
        ]
    )
    monkeypatch.setattr(module, "get_timeline", lambda *_args: next(timelines))

    asyncio.run(AutomationWorker(lambda: "").run_once())
    asyncio.run(AutomationWorker(lambda: "").run_once())
    current_time[0] = 1400.0
    third = asyncio.run(AutomationWorker(lambda: "").run_once())
    state = json.loads(state_file.read_text())

    assert third["actions"][0]["action"] == "waiting_for_user"
    assert state["reply_waits"]["wxid-a"]["started_at"] == 1400.0


def test_non_whitelist_is_skipped_but_trailing_own_message_does_not_drop_incoming(
    monkeypatch, tmp_path
):
    module, _, _ = _configure(monkeypatch, tmp_path, allowed=False, cursor=5)
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {"messages": [_message(6, False, "incoming")]},
    )
    assert asyncio.run(AutomationWorker(lambda: "").run_once())["processed"] == 0

    module, _, _ = _configure(monkeypatch, tmp_path, cursor=5)
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {
            "messages": [
                _message(6, False, "incoming"),
                _message(7, True, "reply"),
            ]
        },
    )
    result = asyncio.run(AutomationWorker(lambda: "").run_once())
    assert result["actions"][0]["action"] == "user_replied"


def test_automation_orders_timeline_before_generation(monkeypatch, tmp_path):
    module, _, _ = _configure(monkeypatch, tmp_path, cursor=5)
    captured = {}

    async def fake_generate(_contact, conversation, _settings):
        captured["conversation"] = conversation
        return {
            "risk": {"level": "L0", "label": "L0", "matched": []},
            "candidates": [{"text": "candidate reply"}],
        }

    monkeypatch.setattr(module, "generate_reply", fake_generate)
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {
            "messages": [
                _message(7, False, "你呢"),
                _message(6, False, "金牛"),
                _message(4, True, "旧回复"),
            ]
        },
    )

    asyncio.run(AutomationWorker(lambda: "").run_once())

    assert captured["conversation"].splitlines()[-2:] == [
        "对方: 金牛",
        "对方: 你呢",
    ]


def test_demo_provider_never_auto_sends(monkeypatch, tmp_path):
    module, _, _ = _configure(
        monkeypatch,
        tmp_path,
        cursor=5,
        dry_run=False,
        acknowledged=True,
    )
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {"messages": [_message(6, False, "incoming")]},
    )
    monkeypatch.setattr(
        module,
        "send_wechat_message",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("demo provider must not auto-send")
        ),
    )

    result = asyncio.run(AutomationWorker(lambda: "").run_once())

    assert result["actions"][0]["action"] == "needs_confirmation"


def test_model_fallback_never_auto_sends(monkeypatch, tmp_path):
    module, state_file, _ = _configure(
        monkeypatch,
        tmp_path,
        cursor=5,
        dry_run=False,
        acknowledged=True,
        provider="openai-compatible",
    )
    _update_auto_reply(enabled=True)

    async def fallback_generate(*_args, **_kwargs):
        return {
            "risk": {"level": "L0", "label": "L0", "matched": []},
            "candidates": [{"text": "offline candidate"}],
            "trace": [{"role": "writer", "status": "fallback"}],
        }

    monkeypatch.setattr(module, "generate_reply", fallback_generate)
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {"messages": [_message(6, False, "incoming")]},
    )
    monkeypatch.setattr(
        module,
        "send_wechat_message",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("model fallback must not auto-send")
        ),
    )

    result = asyncio.run(AutomationWorker(lambda: "").run_once())

    assert result["actions"][0]["action"] == "needs_confirmation"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["pending_confirmations"][0]["reason"] == "model_fallback"


def test_dry_run_and_risk_actions(monkeypatch, tmp_path):
    for level, expected in (
        ("L0", "needs_confirmation"),
        ("L1", "needs_confirmation"),
        ("L2", "needs_confirmation"),
        ("L3", "blocked"),
    ):
        case_dir = tmp_path / level
        case_dir.mkdir()
        module, _, events_file = _configure(
            monkeypatch, case_dir, cursor=5, level=level
        )
        monkeypatch.setattr(
            module,
            "get_timeline",
            lambda *_args: {"messages": [_message(6, False, "incoming")]},
        )
        monkeypatch.setattr(
            module,
            "send_wechat_message",
            lambda *_args: (_ for _ in ()).throw(
                AssertionError("dry-run must not send")
            ),
        )

        result = asyncio.run(AutomationWorker(lambda: "").run_once())

        assert result["actions"][0]["action"] == expected
        event = json.loads(events_file.read_text().strip())
        assert event["sent"] is False


def test_sync_timeline_to_memory_refreshes_skill(monkeypatch):
    import app.automation as module

    refreshed = []
    monkeypatch.setattr(
        module,
        "timeline_to_records",
        lambda *_args, **_kwargs: [{"source_record_id": "wechat:a:2"}],
    )
    monkeypatch.setattr(module, "import_records", lambda records: len(records))
    monkeypatch.setattr(module, "distill_self_skill", lambda: refreshed.append(True))
    contact = Contact(
        contact_id="contact-a",
        display_name="Contact A",
        relationship="friend",
        wechat_username="wxid-a",
    )

    imported = module.sync_timeline_to_memory(
        contact,
        {"messages": [{"id": {"local_id": 2}, "is_from_me": True, "text": "reply"}]},
    )

    assert imported == 1
    assert refreshed == [True]


def test_memory_sync_can_run_without_auto_reply(monkeypatch, tmp_path):
    module, _, _ = _configure(monkeypatch, tmp_path, cursor=5)
    imported = []
    monkeypatch.setattr(
        module,
        "sync_timeline_to_memory",
        lambda *_args: imported.append(True) or 2,
    )
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {"messages": [_message(6, False, "incoming")]},
    )

    result = asyncio.run(
        AutomationWorker(lambda: "").run_once(allow_reply=False)
    )

    assert imported == [True]
    assert result["actions"] == []


def test_full_auto_sends_verified_l0_directly(monkeypatch, tmp_path):
    module, _, _ = _configure(
        monkeypatch,
        tmp_path,
        cursor=5,
        dry_run=False,
        acknowledged=True,
        provider="ollama",
    )
    _update_auto_reply(enabled=True)
    timeline_calls = iter(
        [
            {"messages": [_message(6, False, "incoming")]},
            {"messages": [_message(7, True, "candidate reply")]},
        ]
    )
    monkeypatch.setattr(module, "get_timeline", lambda *_args: next(timeline_calls))
    sent = []
    monkeypatch.setattr(
        module,
        "send_wechat_message",
        lambda *args: sent.append(args) or {"sent": True},
    )

    result = asyncio.run(AutomationWorker(lambda: "").run_once())

    assert result["actions"][0]["action"] == "sent"
    assert result["actions"][0]["send_verified"] is True
    assert sent == [("Contact A", "candidate reply")]


def test_contact_level_override_allows_verified_l1_auto_send(monkeypatch, tmp_path):
    module, _, _ = _configure(
        monkeypatch,
        tmp_path,
        cursor=5,
        level="L1",
        dry_run=False,
        acknowledged=True,
        provider="ollama",
    )
    _update_auto_reply(
        enabled=True,
        contact_settings={
            "contact-a": {
                "enabled": True,
                "dry_run": False,
                "real_send_acknowledged": True,
                "auto_send_levels": ["L1"],
            }
        },
    )
    timeline_calls = iter(
        [
            {"messages": [_message(6, False, "incoming")]},
            {"messages": [_message(7, True, "candidate reply")]},
        ]
    )
    monkeypatch.setattr(module, "get_timeline", lambda *_args: next(timeline_calls))
    sent = []
    monkeypatch.setattr(
        module,
        "send_wechat_message",
        lambda *args: sent.append(args) or {"sent": True},
    )

    result = asyncio.run(AutomationWorker(lambda: "").run_once())

    assert result["actions"][0]["action"] == "sent"
    assert result["actions"][0]["send_verified"] is True
    assert sent == [("Contact A", "candidate reply")]


def test_unverified_send_keeps_cursor_for_retry(monkeypatch, tmp_path):
    module, state_file, events_file = _configure(
        monkeypatch,
        tmp_path,
        cursor=5,
        dry_run=False,
        acknowledged=True,
        provider="ollama",
    )
    _update_auto_reply(enabled=True)
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {"messages": [_message(6, False, "incoming")]},
    )
    monkeypatch.setattr(
        module, "send_wechat_message", lambda *_args: {"sent": True}
    )

    result = asyncio.run(AutomationWorker(lambda: "").run_once())

    assert result["actions"][0]["action"] == "send_unverified"
    assert json.loads(state_file.read_text())["cursors"]["wxid-a"] == 5
    assert json.loads(events_file.read_text().strip())["sent"] is False


def test_failed_send_reuses_candidate_and_enters_backoff(monkeypatch, tmp_path):
    module, state_file, _ = _configure(
        monkeypatch,
        tmp_path,
        cursor=5,
        dry_run=False,
        acknowledged=True,
        provider="ollama",
    )
    _update_auto_reply(enabled=True)
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {"messages": [_message(6, False, "incoming")]},
    )
    generated = []

    async def counted_generate(*args, **kwargs):
        generated.append(True)
        return {
            "risk": {"level": "L0", "label": "L0", "matched": []},
            "candidates": [{"text": "candidate reply"}],
        }

    monkeypatch.setattr(module, "generate_reply", counted_generate)
    monkeypatch.setattr(
        module,
        "send_wechat_message",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("send failed")),
    )

    worker = AutomationWorker(lambda: "")
    first = asyncio.run(worker.run_once())
    second = asyncio.run(worker.run_once())

    assert first["actions"][0]["action"] == "send_unverified"
    assert second["actions"][0]["action"] == "retry_backoff"
    assert len(generated) == 1
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["candidate_cache"]["wxid-a:6"]["candidates"][0]["text"] == (
        "candidate reply"
    )
    assert state["send_failures"]["wxid-a:6"]["attempts"] == 1


def test_retry_detects_already_sent_candidate_before_reopening_wechat(
    monkeypatch, tmp_path
):
    module, state_file, _ = _configure(
        monkeypatch,
        tmp_path,
        cursor=5,
        dry_run=False,
        acknowledged=True,
        provider="ollama",
    )
    _update_auto_reply(enabled=True)
    state_file.write_text(
        json.dumps(
            {
                "cursors": {"wxid-a": 5},
                "candidate_cache": {
                    "wxid-a:6": {
                        "risk": {"level": "L0", "label": "L0", "matched": []},
                        "candidates": [{"text": "candidate reply"}],
                    }
                },
                "send_failures": {
                    "wxid-a:6": {
                        "attempts": 1,
                        "last_error": "verification timeout",
                        "retry_after": 0,
                    }
                },
                "reply_waits": {
                    "wxid-a": {"takeover_ready": True, "started_at": 0}
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {
            "messages": [
                _message(6, False, "incoming"),
                _message(7, True, "candidate reply"),
            ]
        },
    )
    monkeypatch.setattr(
        module,
        "send_wechat_message",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("an already-sent candidate must not be sent again")
        ),
    )

    result = asyncio.run(AutomationWorker(lambda: "").run_once())

    assert result["actions"][0]["action"] == "user_replied"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["cursors"]["wxid-a"] == 7
    assert "wxid-a:6" not in state.get("send_failures", {})
    assert "wxid-a:6" not in state.get("candidate_cache", {})


def test_verify_sent_message_retries_after_timeline_error(monkeypatch):
    import app.automation as module

    calls = []

    def timeline_with_transient_error(*_args):
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("temporary timeline error")
        return {"messages": [_message(7, True, "candidate reply")]}

    monkeypatch.setattr(module, "get_timeline", timeline_with_transient_error)
    monkeypatch.setattr(module.time, "sleep", lambda *_args: None)

    verified, error = AutomationWorker._verify_sent_message(
        "wxid-a",
        6,
        "candidate reply",
        attempts=2,
        interval_seconds=0,
    )

    assert verified is True
    assert error == ""
    assert len(calls) == 2


def test_send_exception_is_recorded_and_keeps_cursor(monkeypatch, tmp_path):
    module, state_file, events_file = _configure(
        monkeypatch,
        tmp_path,
        cursor=5,
        dry_run=False,
        acknowledged=True,
        provider="ollama",
    )
    _update_auto_reply(enabled=True)
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {"messages": [_message(6, False, "incoming")]},
    )

    def fail_send(*_args):
        raise RuntimeError("send failed")

    monkeypatch.setattr(module, "send_wechat_message", fail_send)
    result = asyncio.run(AutomationWorker(lambda: "").run_once())

    assert result["actions"][0]["action"] == "send_unverified"
    assert "send failed" in result["actions"][0]["send_error"]
    assert json.loads(state_file.read_text())["cursors"]["wxid-a"] == 5
    assert json.loads(events_file.read_text().strip())["send_error"] == "send failed"


def test_confirmation_is_queued_without_sending(monkeypatch, tmp_path):
    module, state_file, _ = _configure(monkeypatch, tmp_path, cursor=5)
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {"messages": [_message(6, False, "incoming")]},
    )
    sent = []
    monkeypatch.setattr(
        module, "send_wechat_message", lambda *args: sent.append(args)
    )

    result = asyncio.run(AutomationWorker(lambda: "").run_once())

    assert result["actions"][0]["action"] == "needs_confirmation"
    assert sent == []
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert len(state["pending_confirmations"]) == 1


def test_group_chat_ignores_unmentioned_messages(monkeypatch, tmp_path):
    module, state_file, events_file = _configure(monkeypatch, tmp_path, cursor=5)
    _update_first_contact(
        chat_type="group",
        participant_count=8,
        group_trigger_mode="mention_only",
    )
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {"messages": [_message(6, False, "普通群消息")]},
    )

    result = asyncio.run(AutomationWorker(lambda: "").run_once())

    assert result["actions"][0]["action"] == "ignored"
    assert json.loads(state_file.read_text())["cursors"]["wxid-a"] == 6
    assert not events_file.read_text(encoding="utf-8").strip()


def test_group_chat_mention_generates_confirmation(monkeypatch, tmp_path):
    module, _, events_file = _configure(monkeypatch, tmp_path, cursor=5)
    _update_first_contact(chat_type="group", group_trigger_mode="mention_only")
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {"messages": [_message(6, False, "@我 请看一下")]},
    )

    result = asyncio.run(AutomationWorker(lambda: "").run_once())

    assert result["actions"][0]["action"] == "needs_confirmation"
    event = json.loads(events_file.read_text(encoding="utf-8").strip())
    assert event["chat_type"] == "group"
    assert event["trigger_reason"] == "group_mention"


def test_group_chat_all_messages_mode_generates_confirmation(monkeypatch, tmp_path):
    module, _, _ = _configure(monkeypatch, tmp_path, cursor=5)
    _update_first_contact(chat_type="group", group_trigger_mode="all_messages")
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {"messages": [_message(6, False, "普通群消息")]},
    )

    result = asyncio.run(AutomationWorker(lambda: "").run_once())

    assert result["actions"][0]["action"] == "needs_confirmation"
    assert result["actions"][0]["trigger_reason"] == "group_all_messages"


def test_confirmation_sends_and_verifies(monkeypatch, tmp_path):
    module, state_file, _ = _configure(
        monkeypatch, tmp_path, cursor=5, acknowledged=True
    )
    timeline_calls = iter(
        [
            {"messages": [_message(6, False, "incoming")]},
            {"messages": [_message(7, True, "edited reply")]},
        ]
    )
    monkeypatch.setattr(module, "get_timeline", lambda *_args: next(timeline_calls))
    monkeypatch.setattr(
        module, "send_wechat_message", lambda *_args: {"sent": True}
    )

    asyncio.run(AutomationWorker(lambda: "").run_once())
    state = json.loads(state_file.read_text())
    confirmation_id = state["pending_confirmations"][0]["id"]
    _update_auto_reply(dry_run=False)

    result = asyncio.run(
        AutomationWorker(lambda: "").confirm(confirmation_id, "edited reply")
    )

    assert result["ok"] is True
    assert json.loads(state_file.read_text())["pending_confirmations"] == []


def test_confirmation_rejects_stale_talker_binding(monkeypatch, tmp_path):
    module, state_file, _ = _configure(
        monkeypatch, tmp_path, cursor=5, acknowledged=True
    )
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {"messages": [_message(6, False, "incoming")]},
    )
    asyncio.run(AutomationWorker(lambda: "").run_once())
    state = json.loads(state_file.read_text(encoding="utf-8"))
    confirmation_id = state["pending_confirmations"][0]["id"]
    _update_auto_reply(dry_run=False)
    _update_first_contact(wechat_username="wxid-changed")
    monkeypatch.setattr(
        module,
        "send_wechat_message",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("stale talker confirmation must not send")
        ),
    )

    result = asyncio.run(
        AutomationWorker(lambda: "").confirm(confirmation_id, "edited reply")
    )

    assert result["ok"] is False
    assert result["error"] == "contact_binding_changed"


def test_confirmation_waits_for_running_cycle(monkeypatch, tmp_path):
    module, state_file, _ = _configure(
        monkeypatch, tmp_path, cursor=5, acknowledged=True
    )
    timeline_calls = iter(
        [
            {"messages": [_message(6, False, "incoming")]},
            {"messages": [_message(7, True, "edited reply")]},
        ]
    )
    monkeypatch.setattr(module, "get_timeline", lambda *_args: next(timeline_calls))
    monkeypatch.setattr(
        module, "send_wechat_message", lambda *_args: {"sent": True}
    )

    worker = AutomationWorker(lambda: "")
    asyncio.run(worker.run_once())
    confirmation_id = json.loads(state_file.read_text())["pending_confirmations"][0][
        "id"
    ]
    _update_auto_reply(dry_run=False)

    worker._lock.acquire()
    release_timer = threading.Timer(0.05, worker._lock.release)
    release_timer.start()
    started_at = time.monotonic()
    result = asyncio.run(worker.confirm(confirmation_id, "edited reply"))
    elapsed = time.monotonic() - started_at

    assert elapsed >= 0.04
    assert result["ok"] is True
    assert json.loads(state_file.read_text())["pending_confirmations"] == []


def test_confirmation_returns_lock_error_after_timeout(monkeypatch, tmp_path):
    _module, _state_file, _ = _configure(monkeypatch, tmp_path)

    class BusyLock:
        def __init__(self):
            self.timeout = None

        def acquire(self, **kwargs):
            self.timeout = kwargs.get("timeout")
            return False

    worker = AutomationWorker(lambda: "")
    busy_lock = BusyLock()
    worker._lock = busy_lock

    result = asyncio.run(worker.confirm("missing", "reply"))

    assert result == {"ok": False, "error": "cycle_already_running"}
    assert busy_lock.timeout == 10


def test_confirmation_verification_failure_keeps_queue(monkeypatch, tmp_path):
    module, state_file, _ = _configure(
        monkeypatch, tmp_path, cursor=5, dry_run=False, acknowledged=True
    )
    timeline_calls = iter(
        [
            {"messages": [_message(6, False, "incoming")]},
            {"messages": [_message(7, True, "other reply")]},
        ]
    )
    monkeypatch.setattr(module, "get_timeline", lambda *_args: next(timeline_calls))
    monkeypatch.setattr(
        module, "send_wechat_message", lambda *_args: {"sent": True}
    )

    asyncio.run(AutomationWorker(lambda: "").run_once())
    state = json.loads(state_file.read_text())
    confirmation_id = state["pending_confirmations"][0]["id"]
    result = asyncio.run(
        AutomationWorker(lambda: "").confirm(confirmation_id, "unverified")
    )

    assert result["ok"] is False
    assert result["action"] == "send_unverified"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert len(state["pending_confirmations"]) == 1
    assert state["pending_confirmations"][0]["attempts"] == 1


def test_contact_settings_are_independent(monkeypatch, tmp_path):
    import app.automation as module
    import app.storage as storage

    contacts_file = tmp_path / "contacts.json"
    settings_file = tmp_path / "settings.json"
    state_file = tmp_path / "state.json"
    events_file = tmp_path / "events.jsonl"
    contacts_file.write_text(
        json.dumps(
            [
                {
                    "contact_id": "contact-a",
                    "display_name": "Contact A",
                    "relationship": "friend",
                    "wechat_username": "wxid-a",
                },
                {
                    "contact_id": "contact-b",
                    "display_name": "Contact B",
                    "relationship": "friend",
                    "wechat_username": "wxid-b",
                },
            ]
        ),
        encoding="utf-8",
    )
    settings_file.write_text(
        json.dumps(
            {
                "enabled": False,
                "dry_run": True,
                "allowed_contact_ids": [],
                "contact_settings": {
                    "contact-a": {
                        "enabled": True,
                        "dry_run": True,
                        "real_send_acknowledged": False,
                        "auto_send_levels": ["L0"],
                    },
                    "contact-b": {
                        "enabled": False,
                        "dry_run": True,
                        "real_send_acknowledged": False,
                        "auto_send_levels": ["L0"],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(storage, "CONFIG_DB_FILE", tmp_path / "config.sqlite3")
    storage.initialize_config_storage(seed_demo_contacts=False)
    storage.save_contacts(
        [
            {
                "contact_id": "contact-a",
                "display_name": "Contact A",
                "relationship": "friend",
                "wechat_username": "wxid-a",
            },
            {
                "contact_id": "contact-b",
                "display_name": "Contact B",
                "relationship": "friend",
                "wechat_username": "wxid-b",
            },
        ]
    )
    storage.save_auto_reply_config(
        {
            "enabled": False,
            "dry_run": True,
            "allowed_contact_ids": [],
            "contact_settings": {
                "contact-a": {
                    "enabled": True,
                    "dry_run": True,
                    "real_send_acknowledged": False,
                    "auto_send_levels": ["L0"],
                },
                "contact-b": {
                    "enabled": False,
                    "dry_run": True,
                    "real_send_acknowledged": False,
                    "auto_send_levels": ["L0"],
                },
            },
        }
    )
    state_file.write_text(
        json.dumps({"cursors": {"wxid-a": 5, "wxid-b": 5}}),
        encoding="utf-8",
    )
    events_file.touch()
    monkeypatch.setattr(module, "AUTOMATION_STATE_FILE", state_file)
    monkeypatch.setattr(module, "AUTOMATION_EVENTS_FILE", events_file)
    monkeypatch.setattr(
        module,
        "get_public_settings",
        lambda: {
            "provider": "demo",
            "base_url": "http://127.0.0.1:11434",
            "model": "demo",
        },
    )
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda talker, *_args: {"messages": [_message(6, False, f"incoming-{talker}")]},
    )
    async def fake_generate(*_args, **_kwargs):
        return {
            "risk": {"level": "L0", "label": "L0", "matched": []},
            "candidates": [{"text": "candidate reply"}],
        }

    monkeypatch.setattr(module, "generate_reply", fake_generate)
    monkeypatch.setattr(module, "sync_timeline_to_memory", lambda *_args: 0)

    result = asyncio.run(AutomationWorker(lambda: "").run_once())

    assert [item["contact_id"] for item in result["actions"]] == ["contact-a"]


def test_paused_worker_skips_cycle_and_reset_cursors(monkeypatch, tmp_path):
    module, state_file, _ = _configure(monkeypatch, tmp_path, cursor=5)
    monkeypatch.setattr(
        module,
        "get_timeline",
        lambda *_args: {"messages": [_message(6, False, "incoming")]},
    )
    worker = AutomationWorker(lambda: "")
    worker.set_paused(True)

    result = asyncio.run(worker.run_once())

    assert result["skipped"] == "paused"
    reset = worker.reset_cursors("contact-a")
    assert reset["reset"] is True
    assert json.loads(state_file.read_text())["cursors"] == {}
