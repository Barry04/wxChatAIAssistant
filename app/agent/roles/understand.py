from __future__ import annotations

from typing import Any

from app.agent.tools import (
    tool_analyze_dialogue,
    tool_classify_risk,
    tool_classify_scene,
    tool_load_relationship_skill,
)
from app.agent.tracing import make_trace_event, start_timer
from app.models import Contact


def understand_node(state: dict[str, Any]) -> dict[str, Any]:
    started = start_timer()
    conversation = state["conversation"]
    scene = tool_classify_scene(conversation)
    dialogue = tool_analyze_dialogue(conversation)
    # A reply answers the whole unanswered turn. Earlier, already answered
    # history must not raise risk, but every consecutive incoming fragment can.
    risk_text = str(
        dialogue.get("incoming_turn_text")
        or dialogue.get("last_message")
        or conversation
    )
    risk = tool_classify_risk(risk_text)
    blocked = risk.get("level") == "L3"
    warning = (
        "消息涉及高风险信息，系统不会代替你生成可直接发送的回复。"
        if blocked
        else state.get("warning", "")
    )
    # L3 short-circuits before style; still attach relationship skill for API parity.
    relationship_skill = {}
    if blocked:
        contact = Contact.model_validate(state["contact"])
        relationship_skill = tool_load_relationship_skill(contact.relationship)
    summary = (
        f"scene={scene}, act={dialogue.get('dialogue_act')}, risk={risk.get('level')}"
    )
    result: dict[str, Any] = {
        "scene": scene,
        "risk": risk,
        "dialogue": dialogue,
        "blocked": blocked,
        "warning": warning,
        "candidates": [] if blocked else state.get("candidates", []),
        "trace": [
            make_trace_event(
                "understand",
                "blocked" if blocked else "ok",
                started,
                summary,
            )
        ],
    }
    if relationship_skill:
        result["relationship_skill"] = relationship_skill
        result["examples"] = []
        result["review"] = {
            "decision": "block",
            "issues": ["L3 risk gate"],
            "revised_hints": [],
        }
    return result
