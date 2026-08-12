import json

from fastapi.testclient import TestClient

import app.main as main_module


def _patch_config_db(monkeypatch, tmp_path, contacts=None):
    import app.storage as storage

    monkeypatch.setattr(storage, "CONFIG_DB_FILE", tmp_path / "config.sqlite3")
    storage.initialize_config_storage(seed_demo_contacts=False)
    storage.save_contacts(contacts or [])


def _disable_worker(monkeypatch):
    monkeypatch.setattr(main_module.AUTOMATION_WORKER, "start", lambda: None)
    monkeypatch.setattr(main_module.AUTOMATION_WORKER, "stop", lambda: None)


def test_style_presets_route_and_contact_validation(monkeypatch, tmp_path):
    _patch_config_db(monkeypatch, tmp_path)
    monkeypatch.setattr(
        main_module,
        "get_style_presets",
        lambda: [
            {
                "id": "style:concise",
                "name": "来源风格",
                "sample_count": 12,
                "confidence": "high",
                "style_rules": [],
            }
        ],
    )
    _disable_worker(monkeypatch)

    with TestClient(main_module.app) as client:
        presets = client.get("/api/style-presets")
        assert presets.status_code == 200
        assert presets.json()[0]["id"] == "style:concise"

        created = client.post(
            "/api/contacts",
            json={
                "contact_id": "contact-new",
                "display_name": "新用户",
                "relationship": "friend",
                "style_preset_id": "style:concise",
            },
        )
        assert created.status_code == 200
        assert created.json()["style_preset_id"] == "style:concise"

        updated = client.post(
            "/api/contacts",
            json={
                **created.json(),
                "style_preset_id": "",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["style_preset_id"] == ""
        import app.storage as storage
        stored = storage.load_contacts()
        assert stored[0]["style_preset_id"] == ""

        style_updated = client.patch(
            "/api/contacts/contact-new/style",
            json={"style_preset_id": "style:concise"},
        )
        assert style_updated.status_code == 200
        assert style_updated.json()["display_name"] == "新用户"
        assert style_updated.json()["style_preset_id"] == "style:concise"
        stored = storage.load_contacts()
        assert stored[0]["display_name"] == "新用户"
        assert stored[0]["style_preset_id"] == "style:concise"

        missing = client.patch(
            "/api/contacts/contact-missing/style",
            json={"style_preset_id": "style:concise"},
        )
        assert missing.status_code == 404

        invalid = client.post(
            "/api/contacts",
            json={
                "contact_id": "contact-invalid",
                "display_name": "无效风格",
                "relationship": "friend",
                "style_preset_id": "style:missing",
            },
        )
        assert invalid.status_code == 400
        assert len(storage.load_contacts()) == 1


def test_contact_route_accepts_group_chat_settings(monkeypatch, tmp_path):
    _patch_config_db(monkeypatch, tmp_path)
    monkeypatch.setattr(main_module, "get_style_presets", lambda: [])
    _disable_worker(monkeypatch)

    with TestClient(main_module.app) as client:
        response = client.post(
            "/api/contacts",
            json={
                "contact_id": "group-a",
                "display_name": "项目群",
                "relationship": "friend",
                "wechat_username": "19174600856@chatroom",
                "chat_type": "group",
                "participant_count": 8,
                "group_trigger_mode": "mention_only",
                "group_mention_keywords": ["项目", "提醒"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chat_type"] == "group"
    assert payload["participant_count"] == 8
    assert payload["group_mention_keywords"] == ["项目", "提醒"]


def test_generate_route_accepts_temporary_style_override(monkeypatch, tmp_path):
    _patch_config_db(
        monkeypatch,
        tmp_path,
        [
            {
                "contact_id": "contact-new",
                "display_name": "contact-new",
                "relationship": "friend",
                "style_preset_id": "style:balanced",
            }
        ],
    )
    contacts_file = tmp_path / "contacts.json"
    contacts_file.write_text(
        json.dumps(
            [
                {
                    "contact_id": "contact-new",
                    "display_name": "新用户",
                    "relationship": "friend",
                    "style_preset_id": "style:balanced",
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        main_module,
        "get_style_presets",
        lambda: [{"id": "style:concise", "name": "简洁短句"}],
    )
    calls = []

    async def fake_generate(contact, conversation, settings, style_preset_id=""):
        calls.append((contact.style_preset_id, conversation, style_preset_id))
        return {"style_preset_id": style_preset_id}

    monkeypatch.setattr(main_module, "generate_reply", fake_generate)
    _disable_worker(monkeypatch)

    with TestClient(main_module.app) as client:
        response = client.post(
            "/api/generate",
            json={
                "contact_id": "contact-new",
                "conversation": "对方：你好",
                "style_preset_id": "style:concise",
            },
        )
        assert response.status_code == 200
        assert calls == [("style:balanced", "对方：你好", "style:concise")]

        invalid = client.post(
            "/api/generate",
            json={
                "contact_id": "contact-new",
                "conversation": "对方：你好",
                "style_preset_id": "style:missing",
            },
        )
        assert invalid.status_code == 400


def test_girls_chat_style_routes(monkeypatch):
    _disable_worker(monkeypatch)
    monkeypatch.setattr(
        main_module,
        "get_girls_chat_style",
        lambda: {"ready": True, "meta": {"candidate_count": 2, "sample_count": 20}},
    )
    monkeypatch.setattr(
        main_module,
        "distill_girls_chat_style",
        lambda: {"generated": True, "candidate_count": 2, "sample_count": 20},
    )

    with TestClient(main_module.app) as client:
        fetched = client.get("/api/self-skill/girls-chat-style")
        distilled = client.post("/api/self-skill/girls-chat-style/distill")

    assert fetched.status_code == 200
    assert fetched.json()["meta"]["candidate_count"] == 2
    assert distilled.status_code == 200
    assert distilled.json()["generated"] is True


def test_wechat_coverage_route_reports_read_and_distilled_counts(
    monkeypatch, tmp_path
):
    coverage_file = tmp_path / "wechat-read-coverage.json"
    raw_file = tmp_path / "wechat-raw-messages.jsonl"
    messages_file = tmp_path / "messages.jsonl"
    meta_file = tmp_path / "meta.json"
    coverage_file.write_text(
        json.dumps(
            {
                "total_sessions": 10,
                "readable_sessions": 8,
                "failed_sessions": [
                    {"username": "wxid_missing", "display_name": "缺失会话"}
                ],
            }
        ),
        encoding="utf-8",
    )
    raw_file.write_text('{"id": 1}\n{"id": 2}\n', encoding="utf-8")
    messages_file.write_text('{"id": 1}\n', encoding="utf-8")
    meta_file.write_text(json.dumps({"sample_count": 42}), encoding="utf-8")
    monkeypatch.setattr(main_module, "WECHAT_COVERAGE_FILE", coverage_file)
    monkeypatch.setattr(main_module, "WECHAT_RAW_MESSAGES_FILE", raw_file)
    monkeypatch.setattr(main_module, "MESSAGES_FILE", messages_file)
    monkeypatch.setattr(main_module, "SELF_SKILL_META_FILE", meta_file)
    _disable_worker(monkeypatch)

    with TestClient(main_module.app) as client:
        response = client.get("/api/wechat/coverage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_coverage_percent"] == 80.0
    assert payload["failed_count"] == 1
    assert payload["raw_message_count"] == 2
    assert payload["completed_turn_count"] == 1
    assert payload["distilled_reply_count"] == 42


def test_wechat_coverage_route_reads_utf8_report_without_bom(
    monkeypatch, tmp_path
):
    coverage_file = tmp_path / "wechat-read-coverage.json"
    coverage_file.write_bytes(
        b"\xef\xbb\xbf"
        + json.dumps(
            {
                "total_sessions": 488,
                "readable_sessions": 478,
                "failed_sessions": [],
            },
            ensure_ascii=False,
        ).encode("utf-8")
    )
    monkeypatch.setattr(main_module, "WECHAT_COVERAGE_FILE", coverage_file)
    monkeypatch.setattr(main_module, "WECHAT_RAW_MESSAGES_FILE", tmp_path / "raw.jsonl")
    monkeypatch.setattr(main_module, "MESSAGES_FILE", tmp_path / "messages.jsonl")
    monkeypatch.setattr(main_module, "SELF_SKILL_META_FILE", tmp_path / "meta.json")
    _disable_worker(monkeypatch)

    with TestClient(main_module.app) as client:
        response = client.get("/api/wechat/coverage")

    assert response.status_code == 200
    assert response.json()["total_sessions"] == 488
def test_wechat_import_merges_paginated_coverage(monkeypatch, tmp_path):
    coverage_file = tmp_path / "wechat-read-coverage.json"
    monkeypatch.setattr(main_module, "WECHAT_COVERAGE_FILE", coverage_file)
    monkeypatch.setattr(
        main_module,
        "recent_self_history",
        lambda **_kwargs: (
            [],
            [
                {
                    "username": "wxid_ok",
                    "display_name": "可读",
                    "chat_type": "private",
                    "records": 0,
                    "raw_messages": 2,
                    "raw_imported": 2,
                },
                {
                    "username": "wxid_bad",
                    "display_name": "缺失",
                    "chat_type": "private",
                    "records": 0,
                    "raw_messages": 0,
                    "raw_imported": 0,
                    "error": "table Msg_x not found",
                },
            ],
            {
                "session_offset": 0,
                "session_limit": 2,
                "session_end": 2,
                "total_sessions": 3,
                "has_next_batch": True,
                "failed_sessions": 1,
            },
        ),
    )
    monkeypatch.setattr(main_module, "import_records", lambda _records: 0)
    monkeypatch.setattr(main_module, "distill_self_skill", lambda: {})
    _disable_worker(monkeypatch)

    with TestClient(main_module.app) as client:
        response = client.post(
            "/api/wechat/import-recent",
            json={
                "session_limit": 2,
                "session_offset": 0,
                "messages_per_session": 20,
                "include_groups": True,
            },
        )

    assert response.status_code == 200
    coverage = response.json()["coverage"]
    assert coverage["total_sessions"] == 3
    assert coverage["readable_sessions"] == 1
    assert coverage["failed_sessions"][0]["username"] == "wxid_bad"


def test_wechat_import_preserves_legacy_readable_count_from_raw_messages(
    monkeypatch, tmp_path
):
    coverage_file = tmp_path / "wechat-read-coverage.json"
    raw_file = tmp_path / "wechat-raw-messages.jsonl"
    coverage_file.write_text(
        json.dumps(
            {
                "total_sessions": 3,
                "readable_sessions": 2,
                "failed_sessions": [],
            }
        ),
        encoding="utf-8",
    )
    raw_file.write_text(
        '{"wechat_talker":"wxid_old_a"}\n'
        '{"wechat_talker":"wxid_old_b"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(main_module, "WECHAT_COVERAGE_FILE", coverage_file)
    monkeypatch.setattr(main_module, "WECHAT_RAW_MESSAGES_FILE", raw_file)

    report = main_module._update_wechat_coverage(
        {"total_sessions": 3},
        [{"username": "wxid_new", "display_name": "new", "chat_type": "private"}],
    )

    assert report["readable_sessions"] == 3
    assert set(report["readable_session_ids"]) == {
        "wxid_old_a",
        "wxid_old_b",
        "wxid_new",
    }
