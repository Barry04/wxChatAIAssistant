import asyncio
import json

import app.agent.llm as llm
import httpx
import pytest
from app.agent.llm import _openai_compatible_payload, _response_error
from app.models import RuntimeSettings


def test_deepseek_payload_disables_thinking_and_requests_json():
    payload = _openai_compatible_payload(
        RuntimeSettings(
            provider="openai-compatible",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
        ),
        "请输出 JSON",
        temperature=0.65,
        force_json=True,
    )

    assert payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"] == {"type": "json_object"}


def test_generic_openai_compatible_payload_stays_generic():
    payload = _openai_compatible_payload(
        RuntimeSettings(
            provider="openai-compatible",
            base_url="https://example.com/v1",
            model="example-model",
        ),
        "hello",
        temperature=0.4,
        force_json=True,
    )

    assert "thinking" not in payload
    assert "response_format" not in payload


def test_response_error_keeps_status_and_safe_api_message():
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    response = httpx.Response(
        401,
        request=request,
        json={
            "error": {
                "message": "Authentication Fails",
                "type": "authentication_error",
            }
        },
    )

    error = _response_error(response)

    assert str(error) == "模型服务返回 HTTP 401: Authentication Fails"


def test_chat_completion_writes_redacted_model_call_log(monkeypatch, tmp_path):
    log_file = tmp_path / "model-calls.jsonl"
    prompt = "private conversation text"
    api_key = "secret-api-key"

    class FakeResponse:
        is_error = False
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "private reply"}}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(llm, "MODEL_CALLS_FILE", log_file, raising=False)
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    result = asyncio.run(
        llm.chat_completion(
            RuntimeSettings(
                provider="openai-compatible",
                base_url="https://api.example.com/v1",
                model="example-model",
                api_key=api_key,
            ),
            prompt,
        )
    )

    event = json.loads(log_file.read_text(encoding="utf-8"))
    assert result == "private reply"
    assert event["provider"] == "openai-compatible"
    assert event["model"] == "example-model"
    assert event["endpoint"] == "api.example.com"
    assert event["status"] == "success"
    assert event["http_status"] == 200
    assert isinstance(event["duration_ms"], int)
    serialized = json.dumps(event, ensure_ascii=False)
    assert prompt not in serialized
    assert api_key not in serialized
    assert "private reply" not in serialized


def test_failed_model_call_log_redacts_prompt_and_api_key(monkeypatch, tmp_path):
    log_file = tmp_path / "model-calls.jsonl"
    prompt = "private prompt"
    api_key = "secret-key"

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            raise RuntimeError(f"failed with {prompt} and {api_key}")

    monkeypatch.setattr(llm, "MODEL_CALLS_FILE", log_file)
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    with pytest.raises(RuntimeError, match="failed with"):
        asyncio.run(
            llm.chat_completion(
                RuntimeSettings(
                    provider="openai-compatible",
                    base_url="https://api.example.com/v1",
                    model="example-model",
                    api_key=api_key,
                ),
                prompt,
            )
        )

    serialized = log_file.read_text(encoding="utf-8")
    assert '"status": "error"' in serialized
    assert prompt not in serialized
    assert api_key not in serialized


def test_http_error_log_keeps_status_but_redacts_provider_message(
    monkeypatch, tmp_path
):
    log_file = tmp_path / "model-calls.jsonl"
    provider_message = "provider echoed private conversation"

    class FakeResponse:
        is_error = True
        status_code = 400

        def json(self):
            return {"error": {"message": provider_message}}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(llm, "MODEL_CALLS_FILE", log_file)
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    with pytest.raises(RuntimeError, match="HTTP 400"):
        asyncio.run(
            llm.chat_completion(
                RuntimeSettings(
                    provider="openai-compatible",
                    base_url="https://api.example.com/v1",
                    model="example-model",
                ),
                "private prompt",
            )
        )

    event = json.loads(log_file.read_text(encoding="utf-8"))
    assert event["error"] == "http_error:400"
    assert provider_message not in json.dumps(event, ensure_ascii=False)
