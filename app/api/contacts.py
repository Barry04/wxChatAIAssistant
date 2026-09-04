"""联系人、风格预设、技能与语料统计等基础数据路由。"""

from fastapi import APIRouter, HTTPException

from ..models import Contact, ContactStyleUpdate
from ..self_skill import get_style_presets
from ..services import corpus_stats
from ..storage import load_all_skills, load_contacts, save_contacts

router = APIRouter()


def get_contacts() -> list[dict]:
    """返回全部联系人，供其他路由模块复用。"""
    return load_contacts()


def find_contact(contact_id: str) -> Contact:
    for item in get_contacts():
        if item.get("contact_id") == contact_id:
            return Contact(**item)
    raise HTTPException(status_code=404, detail="联系人不存在")


def _validate_style_preset_id(style_preset_id: str) -> None:
    if not style_preset_id:
        return
    available_ids = {item.get("id") for item in get_style_presets()}
    if style_preset_id not in available_ids:
        raise HTTPException(
            status_code=400,
            detail="指定的回复风格不存在或尚未生成",
        )


@router.get("/api/contacts")
def list_contacts() -> list[dict]:
    return get_contacts()


@router.post("/api/contacts")
def upsert_contact(contact: Contact) -> Contact:
    _validate_style_preset_id(contact.style_preset_id)
    contacts = get_contacts()
    updated = False
    for index, item in enumerate(contacts):
        if item.get("contact_id") == contact.contact_id:
            contacts[index] = contact.model_dump()
            updated = True
            break
    if not updated:
        contacts.append(contact.model_dump())
    save_contacts(contacts)
    return contact


@router.patch("/api/contacts/{contact_id}/style")
def update_contact_style(contact_id: str, payload: ContactStyleUpdate) -> Contact:
    _validate_style_preset_id(payload.style_preset_id)
    contacts = get_contacts()
    for item in contacts:
        if item.get("contact_id") == contact_id:
            item["style_preset_id"] = payload.style_preset_id
            save_contacts(contacts)
            return Contact.model_validate(item)
    raise HTTPException(status_code=404, detail="联系人不存在")


@router.delete("/api/contacts/{contact_id}")
def delete_contact(contact_id: str) -> dict:
    contacts = get_contacts()
    remaining = [item for item in contacts if item.get("contact_id") != contact_id]
    if len(remaining) == len(contacts):
        raise HTTPException(status_code=404, detail="联系人不存在")
    save_contacts(remaining)
    return {"deleted": contact_id}


@router.get("/api/skills")
def skills() -> list[dict]:
    return load_all_skills()


@router.get("/api/stats")
def stats() -> dict:
    return corpus_stats()


@router.get("/api/style-presets")
def style_presets() -> list[dict]:
    return get_style_presets()
