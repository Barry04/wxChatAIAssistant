import asyncio
import json

from app.models import Contact, RuntimeSettings
from app.services import (
    analyze_dialogue,
    classify_risk,
    classify_scene,
    generate_reply,
    parse_plain_text,
    retrieve_examples,
)
from app.services import _sanitize_candidates
from app.self_skill import (
    _girls_chat_candidates,
    distill_girls_chat_style,
    distill_self_skill,
    get_self_skill,
    get_self_skill_prompt,
    get_style_presets,
    get_style_prompt,
)
from app.storage import MESSAGES_FILE
from app.services import import_records


def test_scene_and_risk_classification():
    assert classify_scene("今天真的好累，什么都不想做") == "comfort"
    assert classify_scene("周末一起吃饭吗") == "invitation"
    assert classify_risk("把验证码发给我")["level"] == "L3"
    assert classify_risk("我去医院看看")["level"] == "L0"
    assert classify_risk("明天几点见面")["level"] == "L1"
    assert classify_risk("明天")["level"] == "L0"
    assert classify_risk("算了")["level"] == "L0"
    assert classify_risk("要不要去医院")["level"] == "L3"
    assert classify_risk("五年前被弄到警察局的时候，那个女的动手了")["level"] == "L2"


def test_plain_text_import():
    records = parse_plain_text(
        "对方: 今天好累\n我: 怎么啦\n我: 先休息一下\n对方: 好的",
        "contact-a",
        "partner",
    )
    assert len(records) == 1
    assert records[0]["incoming"] == ["今天好累"]
    assert records[0]["my_reply"] == ["怎么啦", "先休息一下"]


def test_demo_generation():
    contact = Contact(
        contact_id="contact-a",
        display_name="小A",
        relationship="partner",
        preferred_address="宝",
    )
    result = asyncio.run(
        generate_reply(
            contact,
            "今天真的特别累",
            RuntimeSettings(provider="demo"),
        )
    )
    assert result["scene"] == "comfort"
    assert len(result["candidates"]) == 3


def test_dialogue_analysis_tracks_short_confirmation_and_topic():
    result = analyze_dialogue(
        "我: 你创业板已经开通了？\n对方: 开了"
    )
    assert result["dialogue_act"] == "affirmation"
    assert result["topic"] == "finance"
    assert result["previous_message"] == "你创业板已经开通了？"


def test_demo_generation_uses_last_turn_context():
    contact = Contact(
        contact_id="contact-a",
        display_name="小A",
        relationship="friend",
    )
    result = asyncio.run(
        generate_reply(
            contact,
            "我: 你创业板已经开通了？\n对方: 开了",
            RuntimeSettings(provider="demo"),
        )
    )
    assert result["dialogue"]["dialogue_act"] == "affirmation"
    assert result["candidates"][0]["text"] == "那准备买啥？"


def test_multi_message_turn_is_the_reply_unit():
    contact = Contact(
        contact_id="contact-a",
        display_name="小A",
        relationship="friend",
    )
    result = asyncio.run(
        generate_reply(
            contact,
            "对方: 五年前被弄到警察局的时候，那个女的动手了\n"
            "对方: 今年两次的这俩女的倒是没有",
            RuntimeSettings(provider="demo"),
        )
    )

    texts = [item["text"] for item in result["candidates"]]
    assert result["dialogue"]["incoming_turn"] == [
        "五年前被弄到警察局的时候，那个女的动手了",
        "今年两次的这俩女的倒是没有",
    ]
    assert result["dialogue"]["response_plan"]["action"] == "acknowledge_then_explore"
    assert result["dialogue"]["response_plan"]["confidence"] < 0.75
    assert all("幸运" not in text for text in texts)
    assert any("后来" in text or "接着说" in text for text in texts)


def test_demo_generation_answers_current_activity_without_busy_template():
    contact = Contact(
        contact_id="contact-a",
        display_name="小A",
        relationship="partner",
    )
    result = asyncio.run(
        generate_reply(
            contact,
            "我: 快啦，忙完就来找你\n对方: 在干嘛呢",
            RuntimeSettings(provider="demo"),
        )
    )
    texts = [item["text"] for item in result["candidates"]]
    assert result["dialogue"]["topic"] == "current_activity"
    assert texts[0] == "刚看到，咋啦？"
    assert all("忙完" not in text for text in texts)


def test_demo_generation_keeps_astrology_follow_up_on_topic():
    contact = Contact(
        contact_id="contact-a",
        display_name="小A",
        relationship="partner",
    )
    result = asyncio.run(
        generate_reply(
            contact,
            "我: 你先说说看？\n对方: 金牛\n对方: 你呢",
            RuntimeSettings(provider="demo"),
        )
    )
    assert result["dialogue"]["topic"] == "astrology"
    assert result["candidates"][0]["text"] == "你猜猜看？"


def test_real_contact_does_not_retrieve_demo_examples(tmp_path, monkeypatch):
    import app.services as services_module

    messages = tmp_path / "messages.jsonl"
    messages.write_text(
        '{"contact_id":"demo-partner","relationship":"partner","scene":"daily",'
        '"incoming":["你忙完了吗"],"my_reply":["快啦，忙完就来找你"],"source":"demo"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(services_module, "MESSAGES_FILE", messages)
    contact = Contact(
        contact_id="wechat:real",
        display_name="真实联系人",
        relationship="partner",
        is_demo=False,
    )
    assert retrieve_examples("对方: 在干嘛呢", contact, "daily") == []


def test_model_candidates_are_deduplicated_and_bounded():
    result = _sanitize_candidates(
        [
            {"label": "a", "text": " 好啊 "},
            {"label": "b", "text": "好啊"},
            {"label": "c", "text": "x" * 81},
            {"label": "d", "text": "行，晚点说"},
        ],
        {"last_message": "开了"},
    )
    assert [item["text"] for item in result] == ["好啊", "行，晚点说"]


def test_self_skill_requires_real_samples(tmp_path, monkeypatch):
    import app.self_skill as self_skill_module

    messages = tmp_path / "messages.jsonl"
    messages.write_text(
        '{"relationship":"friend","my_reply":["行啊，整起"],"source":"demo"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(self_skill_module, "MESSAGES_FILE", messages)
    result = distill_self_skill()
    assert result["generated"] is False
    assert result["sample_count"] == 0


def test_self_skill_distills_contact_profiles_separately(tmp_path, monkeypatch):
    import app.self_skill as self_skill_module

    messages = tmp_path / "messages.jsonl"
    messages.write_text(
        "\n".join(
            [
                '{"contact_id":"contact-a","display_name":"甲","relationship":"friend","scene":"joking","my_reply":["行啊","哈哈哈"],"source":"wechat"}',
                '{"contact_id":"contact-b","display_name":"乙","relationship":"friend","scene":"daily","my_reply":["知道了，我晚点确认"],"source":"wechat"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(self_skill_module, "MESSAGES_FILE", messages)
    monkeypatch.setattr(self_skill_module, "SELF_MEMORY_FILE", tmp_path / "self.md")
    monkeypatch.setattr(self_skill_module, "PERSONA_FILE", tmp_path / "persona.md")
    monkeypatch.setattr(self_skill_module, "SELF_SKILL_META_FILE", tmp_path / "meta.json")
    contact_dir = tmp_path / "contacts"
    monkeypatch.setattr(self_skill_module, "CONTACT_SKILL_DIR", contact_dir)

    result = distill_self_skill()

    profiles = result["meta"]["contact_profiles"]
    assert set(profiles) == {"contact-a", "contact-b"}
    assert "style_profiles" in result["meta"]
    assert all(
        not profile.get("name", "").startswith("鐢?")
        for profile in result["meta"]["style_profiles"].values()
    )
    assert profiles["contact-a"]["sample_count"] == 2
    assert profiles["contact-b"]["average_reply_length"] > profiles["contact-a"]["average_reply_length"]
    assert len(list(contact_dir.glob("*.md"))) == 2

    prompt = get_self_skill_prompt("contact-a")
    assert '"contact_id": "contact-a"' in prompt
    assert '"contact_id": "contact-b"' not in prompt

    presets = get_style_presets()
    preset_ids = {item["id"] for item in presets}
    assert "style:concise" in preset_ids
    assert all(not item["id"].startswith("contact:") for item in presets)
    assert all(item["name"] not in {"鐢?", "涔?"} for item in presets)
    reusable = get_style_prompt(style_preset_id="style:concise")
    assert '"style_preset_id": "style:concise"' in reusable
    assert '"contact_id": "contact-b"' not in reusable
    assert '"incoming"' not in reusable


def test_girls_chat_candidates_only_use_private_mutual_goodnight(tmp_path, monkeypatch):
    import app.self_skill as self_skill_module

    raw = tmp_path / "wechat-raw-messages.jsonl"
    rows = [
        {
            "contact_id": "wechat:a",
            "wechat_talker": "a",
            "display_name": "甲",
            "chat_type": "private",
            "is_from_me": False,
            "create_time": 100,
            "text": "晚安",
        },
        {
            "contact_id": "wechat:a",
            "wechat_talker": "a",
            "display_name": "甲",
            "chat_type": "private",
            "is_from_me": True,
            "create_time": 120,
            "text": "晚安",
        },
        {
            "contact_id": "wechat:group",
            "wechat_talker": "group",
            "display_name": "群聊",
            "chat_type": "group",
            "is_from_me": False,
            "create_time": 100,
            "text": "晚安",
        },
        {
            "contact_id": "wechat:group",
            "wechat_talker": "group",
            "display_name": "群聊",
            "chat_type": "group",
            "is_from_me": True,
            "create_time": 120,
            "text": "晚安",
        },
    ]
    raw.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )
    monkeypatch.setattr(self_skill_module, "WECHAT_RAW_MESSAGES_FILE", raw)

    candidates = _girls_chat_candidates()

    assert len(candidates) == 1
    assert candidates[0]["talker"] == "a"
    assert candidates[0]["mutual_goodnight_count"] == 1


def test_girls_chat_style_distills_candidate_replies_without_identity(
    tmp_path, monkeypatch
):
    import app.self_skill as self_skill_module

    raw = tmp_path / "wechat-raw-messages.jsonl"
    raw.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {
                    "contact_id": "wechat:a",
                    "wechat_talker": "a",
                    "display_name": "甲",
                    "chat_type": "private",
                    "is_from_me": False,
                    "create_time": 100,
                    "text": "晚安",
                },
                {
                    "contact_id": "wechat:a",
                    "wechat_talker": "a",
                    "display_name": "甲",
                    "chat_type": "private",
                    "is_from_me": True,
                    "create_time": 120,
                    "text": "晚安",
                },
            ]
        ),
        encoding="utf-8",
    )
    messages = tmp_path / "messages.jsonl"
    messages.write_text(
        json.dumps(
            {
                "contact_id": "wechat:a",
                "wechat_talker": "a",
                "display_name": "甲",
                "chat_type": "private",
                "source": "wechat",
                "incoming": ["今天辛苦啦"],
                "my_reply": ["早点休息呀"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    skill_file = tmp_path / "girls-chat-style.md"
    monkeypatch.setattr(self_skill_module, "WECHAT_RAW_MESSAGES_FILE", raw)
    monkeypatch.setattr(self_skill_module, "MESSAGES_FILE", messages)
    monkeypatch.setattr(self_skill_module, "SELF_SKILL_META_FILE", tmp_path / "meta.json")
    monkeypatch.setattr(self_skill_module, "GIRLS_CHAT_STYLE_FILE", skill_file)

    result = distill_girls_chat_style()

    assert result["generated"] is True
    assert result["candidate_count"] == 1
    assert result["sample_count"] == 1
    assert skill_file.exists()
    assert "甲" not in skill_file.read_text(encoding="utf-8")


def test_girls_chat_style_uses_aggregate_sample_count_for_preset_and_prompt(
    tmp_path, monkeypatch
):
    import app.self_skill as self_skill_module

    meta = {
        "sample_count": 100,
        "girls_chat_style": {
            "candidate_count": 10,
            "sample_count": 14057,
            "confidence_note": "仅基于启发式候选",
            "style_profiles": {
                "balanced": {
                    "sample_count": 4203,
                    "confidence": "medium",
                    "average_reply_length": 6.5,
                    "median_reply_length": 4,
                    "question_rate": 10,
                    "laughter_emoji_rate": 2,
                    "median_response_seconds": 20,
                    "active_hours": [],
                    "common_particles": [],
                    "common_endings": [],
                    "style_rules": [],
                }
            },
        },
    }
    monkeypatch.setattr(
        self_skill_module,
        "get_self_skill",
        lambda: {"ready": True, "meta": meta, "persona": ""},
    )

    preset = next(
        item for item in get_style_presets() if item["id"] == "style:girls-chat"
    )
    assert preset["sample_count"] == 14057
    assert preset["profile_sample_count"] == 4203

    prompt = json.loads(get_style_prompt(style_preset_id="style:girls-chat"))
    profile = prompt["meta"]["style_profile"]
    assert profile["sample_count"] == 14057
    assert profile["profile_sample_count"] == 4203
    assert "identity_boundary" in profile


def test_distill_self_skill_refreshes_existing_girls_style_document(
    tmp_path, monkeypatch
):
    import app.self_skill as self_skill_module

    messages = tmp_path / "messages.jsonl"
    messages.write_text(
        json.dumps(
            {
                "contact_id": "wechat:a",
                "chat_type": "private",
                "source": "wechat",
                "incoming": ["你好"],
                "my_reply": ["晚点聊"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    meta_file = tmp_path / "meta.json"
    meta_file.write_text(
        json.dumps(
            {
                "created_at": "2026-01-01T00:00:00+00:00",
                "girls_chat_style": {
                    "sample_count": 99,
                    "candidate_count": 1,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw = tmp_path / "wechat-raw-messages.jsonl"
    raw.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {
                    "contact_id": "wechat:a",
                    "wechat_talker": "a",
                    "chat_type": "private",
                    "is_from_me": False,
                    "create_time": 100,
                    "text": "晚安",
                },
                {
                    "contact_id": "wechat:a",
                    "wechat_talker": "a",
                    "chat_type": "private",
                    "is_from_me": True,
                    "create_time": 120,
                    "text": "晚安",
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    girls_file = tmp_path / "girls-chat-style.md"
    monkeypatch.setattr(self_skill_module, "MESSAGES_FILE", messages)
    monkeypatch.setattr(self_skill_module, "SELF_SKILL_META_FILE", meta_file)
    monkeypatch.setattr(self_skill_module, "WECHAT_RAW_MESSAGES_FILE", raw)
    monkeypatch.setattr(self_skill_module, "GIRLS_CHAT_STYLE_FILE", girls_file)
    monkeypatch.setattr(self_skill_module, "SELF_MEMORY_FILE", tmp_path / "memory.md")
    monkeypatch.setattr(self_skill_module, "PERSONA_FILE", tmp_path / "persona.md")
    monkeypatch.setattr(self_skill_module, "CONTACT_SKILL_DIR", tmp_path / "contacts")
    monkeypatch.setattr("app.services.distill_profile", lambda: None)

    result = self_skill_module.distill_self_skill()

    assert result["generated"] is True
    assert "- 聚合回复样本: 1" in girls_file.read_text(encoding="utf-8")
    refreshed = json.loads(meta_file.read_text(encoding="utf-8"))
    assert refreshed["girls_chat_style"]["sample_count"] == 1


def test_import_records_deduplicates_source_ids(tmp_path, monkeypatch):
    import app.services as services_module

    messages = tmp_path / "messages.jsonl"
    messages.touch()
    monkeypatch.setattr(services_module, "MESSAGES_FILE", messages)
    record = {
        "source_record_id": "wechat:a:1",
        "incoming": ["你好"],
        "my_reply": ["你好"],
    }

    assert import_records([record, record]) == 1
    assert import_records([record]) == 0


def test_feedback_refreshes_self_skill(tmp_path, monkeypatch):
    import app.services as services_module

    feedback = tmp_path / "feedback.jsonl"
    messages = tmp_path / "messages.jsonl"
    feedback.touch()
    messages.touch()
    monkeypatch.setattr(services_module, "FEEDBACK_FILE", feedback)
    monkeypatch.setattr(services_module, "MESSAGES_FILE", messages)

    refreshed = []
    monkeypatch.setattr(
        "app.self_skill.distill_self_skill",
        lambda: refreshed.append(True),
    )

    contact = Contact(
        contact_id="contact-a",
        display_name="小A",
        relationship="friend",
    )
    services_module.save_feedback(
        contact,
        "对方: 晚点聊",
        "晚点说",
        "好，晚点聊",
        "daily",
    )

    assert refreshed == [True]
    assert len(messages.read_text(encoding="utf-8").splitlines()) == 1


def test_read_json_falls_back_on_corrupt_or_empty(tmp_path):
    from app.storage import read_json

    missing = tmp_path / "missing.json"
    assert read_json(missing, {"fallback": 1}) == {"fallback": 1}

    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")
    assert read_json(empty, {"fallback": 2}) == {"fallback": 2}

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_bytes(b"\x00\x00\x00")
    assert read_json(corrupt, {"fallback": 3}) == {"fallback": 3}

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json", encoding="utf-8")
    assert read_json(invalid, {"fallback": 4}) == {"fallback": 4}
