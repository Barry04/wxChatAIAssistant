"""对话导入、画像蒸馏与个人/女孩聊天风格 self-skill 路由。"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..models import ImportTextRequest
from ..self_skill import (
    distill_girls_chat_style,
    distill_self_skill,
    get_girls_chat_style,
    get_self_skill,
)
from ..services import (
    distill_profile,
    import_records,
    parse_csv_bytes,
    parse_plain_text,
)
from .contacts import find_contact

router = APIRouter()


@router.post("/api/import/text")
def import_text(payload: ImportTextRequest) -> dict:
    find_contact(payload.contact_id)
    records = parse_plain_text(
        payload.content,
        payload.contact_id,
        payload.relationship,
        payload.self_label,
    )
    if not records:
        raise HTTPException(
            status_code=400,
            detail="没有识别到有效对话，请使用“对方: 内容”和“我: 内容”的格式。",
        )
    imported = import_records(records)
    if imported:
        distill_self_skill()
    return {"imported": imported, "preview": records[:3]}


@router.post("/api/import/file")
async def import_file(
    file: Annotated[UploadFile, File()],
    contact_id: Annotated[str, Form()],
    relationship: Annotated[str, Form()],
    self_label: Annotated[str, Form()] = "我",
) -> dict:
    find_contact(contact_id)
    content = await file.read()
    suffix = Path(file.filename or "").suffix.lower()
    if suffix == ".csv":
        records = parse_csv_bytes(content, contact_id, relationship, self_label)
    elif suffix in {".txt", ".md"}:
        records = parse_plain_text(
            content.decode("utf-8-sig"),
            contact_id,
            relationship,
            self_label,
        )
    else:
        raise HTTPException(status_code=400, detail="目前只支持 TXT、MD 和 CSV 文件。")
    if not records:
        raise HTTPException(status_code=400, detail="文件中没有识别到有效对话。")
    imported = import_records(records)
    if imported:
        distill_self_skill()
    return {"imported": imported, "preview": records[:3]}


@router.post("/api/distill")
def distill() -> dict:
    return distill_profile()


@router.post("/api/self-skill/distill")
def distill_personal_skill() -> dict:
    return distill_self_skill()


@router.get("/api/self-skill/girls-chat-style")
def girls_chat_style() -> dict:
    return get_girls_chat_style()


@router.post("/api/self-skill/girls-chat-style/distill")
def distill_girls_chat() -> dict:
    return distill_girls_chat_style()


@router.get("/api/self-skill")
def self_skill() -> dict:
    return get_self_skill()
