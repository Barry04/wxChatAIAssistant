from __future__ import annotations

from typing import Any

from app.models import Contact
from app.self_skill import get_self_skill_prompt
from app.services import (
    _demo_candidates,
    _sanitize_candidates,
    analyze_dialogue,
    classify_risk,
    classify_scene,
    contact_style_instructions,
    retrieve_examples,
)
from app.storage import PROFILE_FILE, load_skill, read_json


def tool_classify_scene(conversation: str) -> str:
    return classify_scene(conversation)


def tool_classify_risk(conversation: str) -> dict[str, Any]:
    return classify_risk(conversation)


def tool_analyze_dialogue(conversation: str) -> dict[str, Any]:
    return analyze_dialogue(conversation)


def tool_retrieve_examples(
    conversation: str,
    contact: Contact,
    scene: str,
    limit: int = 4,
) -> list[dict[str, Any]]:
    return retrieve_examples(conversation, contact, scene, limit=limit)


def tool_load_relationship_skill(relationship: str) -> dict[str, Any]:
    return load_skill(relationship)


def tool_load_persona(contact_id: str) -> str:
    return get_self_skill_prompt(contact_id)


def tool_load_profile() -> dict[str, Any]:
    return read_json(PROFILE_FILE, {})


def tool_contact_style_instructions(contact: Contact) -> dict[str, Any]:
    return contact_style_instructions(contact)


def tool_demo_candidates(
    contact: Contact,
    scene: str,
    examples: list[dict[str, Any]],
    dialogue: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    return _demo_candidates(contact, scene, examples, dialogue)


def tool_sanitize_candidates(
    candidates: list[dict[str, str]],
    dialogue: dict[str, Any],
) -> list[dict[str, str]]:
    return _sanitize_candidates(candidates, dialogue)
