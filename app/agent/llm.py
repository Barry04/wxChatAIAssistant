from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.models import RuntimeSettings


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
    # Windows user-level proxy settings can be stale even when WinHTTP is direct.
    # Model endpoints should use the explicitly configured base URL directly.
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
            return response.json()["message"]["content"]

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
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("模型服务响应缺少 choices[0].message.content") from exc
