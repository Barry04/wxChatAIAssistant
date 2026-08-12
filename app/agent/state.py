from __future__ import annotations

from typing import Annotated, Any, TypedDict


def _append_trace(
    existing: list[dict[str, Any]] | None,
    new: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return list(existing or []) + list(new or [])


class AgentState(TypedDict, total=False):
    contact: dict[str, Any]
    conversation: str
    settings: dict[str, Any]
    style_preset_id: str

    scene: str
    risk: dict[str, Any]
    dialogue: dict[str, Any]

    relationship_skill: dict[str, Any]
    persona: str
    profile: dict[str, Any]
    examples: list[dict[str, Any]]
    style_brief: dict[str, Any]

    candidates: list[dict[str, str]]
    review: dict[str, Any]
    rewrite_count: int
    warning: str
    blocked: bool

    trace: Annotated[list[dict[str, Any]], _append_trace]
