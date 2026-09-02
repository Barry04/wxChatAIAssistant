"""运行设置（含模型提供方与 API Key）路由。"""

from fastapi import APIRouter

from ..agent.llm import chat_completion
from ..models import RuntimeSettings
from ..services import (
    get_public_settings,
    get_runtime_settings,
    save_public_settings,
)
from . import state

router = APIRouter()


@router.get("/api/settings")
def settings() -> dict:
    return {
        **get_public_settings(),
        "api_key_configured": bool(state.RUNTIME_API_KEY),
    }


@router.put("/api/settings")
def update_settings(payload: RuntimeSettings) -> dict:
    current = get_runtime_settings()
    api_key = payload.api_key or current.api_key
    settings_to_save = payload.model_copy(update={"api_key": api_key})
    state.RUNTIME_API_KEY = api_key
    save_public_settings(settings_to_save)
    return {
        **get_public_settings(),
        "api_key_configured": bool(state.RUNTIME_API_KEY),
    }


@router.post("/api/settings/test")
async def test_settings() -> dict:
    stored = get_public_settings()
    settings = RuntimeSettings(**{**stored, "api_key": state.RUNTIME_API_KEY})
    if settings.provider == "demo":
        return {
            "ok": False,
            "provider": settings.provider,
            "api_key_configured": False,
            "error": "离线演示模式不会调用外部模型",
        }
    try:
        content = await chat_completion(
            settings,
            '只输出 JSON：{"ok":true}',
            temperature=0,
            force_json=True,
        )
        return {
            "ok": True,
            "provider": settings.provider,
            "model": settings.model,
            "api_key_configured": bool(state.RUNTIME_API_KEY),
            "response_received": bool(content.strip()),
        }
    except Exception as exc:  # noqa: BLE001 - return a safe connection diagnostic
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.model,
            "api_key_configured": bool(state.RUNTIME_API_KEY),
            "error": str(exc) or exc.__class__.__name__,
        }
