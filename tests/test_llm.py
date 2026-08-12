import httpx

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
