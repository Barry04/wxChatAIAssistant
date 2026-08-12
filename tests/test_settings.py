from app.models import RuntimeSettings


def _patch_config_db(monkeypatch, tmp_path):
    import app.storage as storage

    monkeypatch.setattr(storage, "CONFIG_DB_FILE", tmp_path / "config.sqlite3")
    storage.initialize_config_storage(seed_demo_contacts=False)
    return storage


def test_runtime_settings_persist_api_key(tmp_path, monkeypatch):
    import app.services as services

    _patch_config_db(monkeypatch, tmp_path)
    original = RuntimeSettings(
        provider="openai-compatible",
        base_url="https://api.example.com",
        model="example-model",
        api_key="secret-key",
    )
    services.save_public_settings(original)

    loaded = services.get_runtime_settings()
    public = services.get_public_settings()

    assert loaded == original
    assert public["api_key"] == ""
    assert public["provider"] == "openai-compatible"


def test_update_settings_keeps_existing_api_key_when_form_is_blank(
    tmp_path, monkeypatch
):
    import app.main as main
    import app.services as services

    _patch_config_db(monkeypatch, tmp_path)
    services.save_public_settings(
        RuntimeSettings(
            provider="openai-compatible",
            base_url="https://api.example.com",
            model="example-model",
            api_key="existing-key",
        )
    )
    monkeypatch.setattr(main, "RUNTIME_API_KEY", "existing-key")

    result = main.update_settings(
        RuntimeSettings(
            provider="openai-compatible",
            base_url="https://api.example.com/v1",
            model="new-model",
            api_key="",
        )
    )

    assert result["api_key_configured"] is True
    assert services.get_runtime_settings().api_key == "existing-key"
    assert services.get_runtime_settings().model == "new-model"
