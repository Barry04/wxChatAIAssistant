from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from app.models import RuntimeSettings
from app.storage import MODEL_CALLS_FILE, append_jsonl


def _record_model_call(
    settings: RuntimeSettings,
    *,
    started_at: float,
    status: str,
    http_status: int | None = None,
    error: str = "",
) -> None:
    """Persist request metadata without prompts, responses, credentials, or paths."""
    hostname = (urlparse(settings.base_url).hostname or "local").lower()
    append_jsonl(
        MODEL_CALLS_FILE,
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provider": settings.provider,
            "model": settings.model,
            "endpoint": hostname,
            "status": status,
            "http_status": http_status,
            "duration_ms": max(0, round((time.perf_counter() - started_at) * 1000)),
            "error": error[:500],
        },
    )


def _safe_error_summary(exc: Exception, http_status: int | None = None) -> str:
    if http_status is not None:
        return f"http_error:{http_status}"
    if isinstance(exc, httpx.TimeoutException):
        return "request_timeout"
    if isinstance(exc, httpx.RequestError):
        return f"request_error:{type(exc).__name__}"
    message = str(exc)
    if message.startswith("模型服务返回 HTTP "):
        return message[:500]
    if message == "模型服务响应缺少 choices[0].message.content":
        return message
    return type(exc).__name__


def _response_error(response: httpx.Response) -> RuntimeError:
    detail = ""
    try:
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            detail = str(error.get("message") or error.get("code") or "").strip()
        elif error:
            detail = str(error).strip()
        if not detail and isinstance(payload, dict):
            detail = str(payload.get("message") or payload.get("code") or "").strip()
    except (ValueError, TypeError):
        detail = response.text.strip()[:300]
    suffix = f": {detail}" if detail else ""
    return RuntimeError(f"模型服务返回 HTTP {response.status_code}{suffix}")


def extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("模型没有返回 JSON")
    return json.loads(cleaned[start : end + 1])


def _openai_compatible_payload(
    settings: RuntimeSettings,
    prompt: str,
    *,
    temperature: float,
    force_json: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": settings.model,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    hostname = (urlparse(settings.base_url).hostname or "").lower()
    if hostname == "api.deepseek.com":
        payload["thinking"] = {"type": "disabled"}
        if force_json:
            payload["response_format"] = {"type": "json_object"}
    return payload


async def chat_completion(
    settings: RuntimeSettings,
    prompt: str,
    *,
    temperature: float = 0.65,
    force_json: bool = True,
) -> str:
    """Call Ollama or OpenAI-compatible chat APIs. Demo provider is not allowed here."""
    if settings.provider == "demo":
        raise RuntimeError("demo provider does not call external models")

    timeout = httpx.Timeout(45.0)
    started_at = time.perf_counter()
    # Windows user-level proxy settings can be stale even when WinHTTP is direct.
    # Model endpoints should use the explicitly configured base URL directly.
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            if settings.provider == "ollama":
                payload: dict[str, Any] = {
                    "model": settings.model,
                    "stream": False,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if force_json:
                    payload["format"] = "json"
                response = await client.post(
                    settings.base_url.rstrip("/") + "/api/chat",
                    json=payload,
                )
                if response.is_error:
                    raise _response_error(response)
                content = response.json()["message"]["content"]
            else:
                headers = {"Content-Type": "application/json"}
                if settings.api_key:
                    headers["Authorization"] = f"Bearer {settings.api_key}"
                response = await client.post(
                    settings.base_url.rstrip("/") + "/chat/completions",
                    headers=headers,
                    json=_openai_compatible_payload(
                        settings,
                        prompt,
                        temperature=temperature,
                        force_json=force_json,
                    ),
                )
                if response.is_error:
                    raise _response_error(response)
                payload = response.json()
                try:
                    content = payload["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as exc:
                    raise RuntimeError(
                        "模型服务响应缺少 choices[0].message.content"
                    ) from exc
        _record_model_call(
            settings,
            started_at=started_at,
            status="success",
            http_status=response.status_code,
        )
        return content
    except Exception as exc:
        _record_model_call(
            settings,
            started_at=started_at,
            status="error",
            http_status=getattr(locals().get("response"), "status_code", None),
            error=_safe_error_summary(
                exc,
                getattr(locals().get("response"), "status_code", None),
            ),
        )
        raise
