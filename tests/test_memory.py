from app.memory import (
    extract_facts_from_incoming,
    list_facts,
    relevant_facts,
    sync_incoming_facts,
    upsert_facts,
)
from app.agent.roles.style import style_node
from app.models import Contact


def test_upsert_merges_duplicate_facts_and_replaces_on_correction(monkeypatch, tmp_path):
    import app.storage as storage

    monkeypatch.setattr(storage, "CONFIG_DB_FILE", tmp_path / "config.sqlite3")
    storage.initialize_config_storage(seed_demo_contacts=False)

    first = upsert_facts(
        "contact-a",
        [
            {
                "fact_type": "preference",
                "content": "不吃香菜",
                "key": "香菜",
                "source_message_id": "m1",
            }
        ],
    )
    second = upsert_facts(
        "contact-a",
        [
            {
                "fact_type": "preference",
                "content": "不吃香菜",
                "key": "香菜",
                "source_message_id": "m2",
            }
        ],
    )
    changed = upsert_facts(
        "contact-a",
        [
            {
                "fact_type": "preference",
                "content": "现在可以吃香菜",
                "key": "香菜",
                "source_message_id": "m3",
            }
        ],
    )

    stored = list_facts("contact-a")
    assert len(first) == 1
    assert second[0]["key_hash"] == first[0]["key_hash"]
    assert len(stored) == 1
    assert stored[0]["content"] == "现在可以吃香菜"
    assert changed[0]["content"] == "现在可以吃香菜"


def test_facts_are_isolated_by_contact(monkeypatch, tmp_path):
    import app.storage as storage

    monkeypatch.setattr(storage, "CONFIG_DB_FILE", tmp_path / "config.sqlite3")
    storage.initialize_config_storage(seed_demo_contacts=False)
    upsert_facts("contact-a", [{"fact_type": "identity", "content": "养了只猫叫咪咪"}])
    upsert_facts("contact-b", [{"fact_type": "plan", "content": "下周一到上海出差"}])

    assert [item["content"] for item in list_facts("contact-a")] == ["养了只猫叫咪咪"]
    assert [item["content"] for item in list_facts("contact-b")] == ["下周一到上海出差"]


def test_recent_facts_rank_above_older_ones(monkeypatch, tmp_path):
    import app.storage as storage

    monkeypatch.setattr(storage, "CONFIG_DB_FILE", tmp_path / "config.sqlite3")
    storage.initialize_config_storage(seed_demo_contacts=False)
    upsert_facts("contact-a", [{"fact_type": "habit", "content": "经常加班"}])
    upsert_facts("contact-a", [{"fact_type": "plan", "content": "周五早点走"}])

    contents = [item["content"] for item in list_facts("contact-a")]
    assert contents[0] == "周五早点走"


def test_extract_and_sync_do_not_raise_on_failure(monkeypatch, tmp_path):
    import app.storage as storage

    monkeypatch.setattr(storage, "CONFIG_DB_FILE", tmp_path / "config.sqlite3")
    storage.initialize_config_storage(seed_demo_contacts=False)
    facts = extract_facts_from_incoming(
        [{"is_from_me": False, "text": "我不吃香菜", "kind": "text"}],
        "contact-a",
    )
    assert any("香菜" in item["content"] for item in facts)
    count = sync_incoming_facts(
        "contact-a",
        [{"is_from_me": False, "text": "养了只猫叫咪咪", "kind": "text"}],
    )
    assert count >= 1
    monkeypatch.setattr(
        "app.memory.extract_facts_from_incoming",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("model down")),
    )
    assert sync_incoming_facts("contact-a", [{"is_from_me": False, "text": "x"}]) == 0


def test_model_extract_parses_json_and_failure_does_not_block_heuristic(monkeypatch, tmp_path):
    import asyncio

    import app.storage as storage
    from app.memory import extract_facts_via_model
    from app.models import RuntimeSettings

    monkeypatch.setattr(storage, "CONFIG_DB_FILE", tmp_path / "config.sqlite3")
    storage.initialize_config_storage(seed_demo_contacts=False)
    settings = RuntimeSettings(provider="openai-compatible", model="test")
    incoming = [{"is_from_me": False, "text": "我不吃香菜", "kind": "text"}]

    async def fake_chat(*_args, **_kwargs):
        return '{"facts":[{"fact_type":"preference","content":"不吃香菜","key":"香菜","confidence":0.8}]}'

    monkeypatch.setattr("app.agent.llm.chat_completion", fake_chat)
    parsed = asyncio.run(extract_facts_via_model(incoming, "contact-a", settings))
    assert parsed[0]["content"] == "不吃香菜"
    assert parsed[0]["fact_type"] == "preference"

    async def boom(*_args, **_kwargs):
        raise RuntimeError("model down")

    monkeypatch.setattr("app.agent.llm.chat_completion", boom)
    try:
        asyncio.run(extract_facts_via_model(incoming, "contact-a", settings))
        raise AssertionError("model extract should surface the failure to the caller")
    except RuntimeError:
        pass
    assert sync_incoming_facts("contact-a", incoming) >= 1


def test_style_survives_memory_lookup_failure(monkeypatch):
    monkeypatch.setattr("app.agent.roles.style.relevant_facts", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("db down")))
    monkeypatch.setattr("app.agent.roles.style.get_summary", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("db down")))
    contact = Contact(contact_id="contact-a", display_name="甲", relationship="friend")
    result = style_node(
        {
            "contact": contact.model_dump(),
            "conversation": "今晚吃火锅吗",
            "scene": "daily",
            "dialogue": {"topic": "吃饭", "last_message": "今晚吃火锅吗"},
        }
    )
    assert result["style_brief"]["facts"] == []
    assert result["style_brief"]["memory_summary"] == ""


def test_style_brief_injects_current_contact_facts_only(monkeypatch, tmp_path):
    import app.storage as storage

    monkeypatch.setattr(storage, "CONFIG_DB_FILE", tmp_path / "config.sqlite3")
    storage.initialize_config_storage(seed_demo_contacts=False)
    upsert_facts("contact-a", [{"fact_type": "preference", "content": "不吃香菜"}])
    upsert_facts("contact-b", [{"fact_type": "plan", "content": "下周一到上海出差"}])
    contact = Contact(
        contact_id="contact-a",
        display_name="甲",
        relationship="friend",
    )
    result = style_node(
        {
            "contact": contact.model_dump(),
            "conversation": "今晚吃火锅吗",
            "scene": "daily",
            "dialogue": {"topic": "吃饭", "last_message": "今晚吃火锅吗"},
        }
    )

    contents = [item["content"] for item in result["style_brief"].get("facts") or []]
    assert "不吃香菜" in contents
    assert "下周一到上海出差" not in contents
    assert "可能" not in "".join(contents)
    assert "不吃香菜" in (result["style_brief"].get("memory_summary") or "")
    assert "上海" not in (result["style_brief"].get("memory_summary") or "")
