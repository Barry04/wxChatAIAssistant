"""草稿生成与反馈保存路由。"""

from fastapi import APIRouter

from ..models import FeedbackRequest, GenerateRequest, RuntimeSettings
from ..services import generate_reply, get_public_settings, save_feedback
from . import state
from .contacts import _validate_style_preset_id, find_contact

router = APIRouter()


@router.post("/api/generate")
async def generate(payload: GenerateRequest) -> dict:
    contact = find_contact(payload.contact_id)
    _validate_style_preset_id(payload.style_preset_id)
    stored = get_public_settings()
    settings = RuntimeSettings(**{**stored, "api_key": state.RUNTIME_API_KEY})
    return await generate_reply(
        contact,
        payload.conversation,
        settings,
        style_preset_id=payload.style_preset_id,
    )


@router.post("/api/feedback")
def feedback(payload: FeedbackRequest) -> dict:
    contact = find_contact(payload.contact_id)
    save_feedback(
        contact,
        payload.conversation,
        payload.selected_text,
        payload.final_text,
        payload.scene,
    )
    return {"saved": True}
