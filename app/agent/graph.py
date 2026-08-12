from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from app.agent.roles import reviewer as reviewer_module
from app.agent.roles import style as style_module
from app.agent.roles import understand as understand_module
from app.agent.roles import writer as writer_module
from app.agent.state import AgentState
from app.models import Contact, RuntimeSettings

_compiled_graph = None


def _route_after_understand(state: AgentState) -> Literal["style", "__end__"]:
    if state.get("blocked") or (state.get("risk") or {}).get("level") == "L3":
        return END
    return "style"


def _route_after_reviewer(state: AgentState) -> Literal["writer", "__end__"]:
    review = state.get("review") or {}
    if review.get("decision") == "revise" and int(state.get("rewrite_count") or 0) <= 1:
        # rewrite_count already incremented in reviewer when decision=revise
        return "writer"
    return END


async def _understand_entry(state: AgentState) -> dict[str, Any]:
    return understand_module.understand_node(state)


async def _style_entry(state: AgentState) -> dict[str, Any]:
    return style_module.style_node(state)


async def _writer_entry(state: AgentState) -> dict[str, Any]:
    return await writer_module.writer_node(state)


async def _reviewer_entry(state: AgentState) -> dict[str, Any]:
    return reviewer_module.reviewer_node(state)


def build_generate_graph(force_rebuild: bool = False):
    global _compiled_graph
    if _compiled_graph is not None and not force_rebuild:
        return _compiled_graph

    graph = StateGraph(AgentState)
    graph.add_node("understand", _understand_entry)
    graph.add_node("style", _style_entry)
    graph.add_node("writer", _writer_entry)
    graph.add_node("reviewer", _reviewer_entry)

    graph.add_edge(START, "understand")
    graph.add_conditional_edges("understand", _route_after_understand)
    graph.add_edge("style", "writer")
    graph.add_edge("writer", "reviewer")
    graph.add_conditional_edges("reviewer", _route_after_reviewer)
    _compiled_graph = graph.compile()
    return _compiled_graph


async def run_generate_agent(
    contact: Contact,
    conversation: str,
    settings: RuntimeSettings,
    style_preset_id: str = "",
) -> dict[str, Any]:
    app = build_generate_graph()
    initial: AgentState = {
        "contact": contact.model_dump(),
        "conversation": conversation,
        "settings": settings.model_dump(),
        "style_preset_id": style_preset_id,
        "rewrite_count": 0,
        "warning": "",
        "candidates": [],
        "trace": [],
        "blocked": False,
    }
    final_state = await app.ainvoke(initial)

    persona = final_state.get("persona") or "尚未生成个人 Self Skill。"
    risk = final_state.get("risk") or {
        "level": "L0",
        "label": "普通聊天",
        "matched": [],
    }
    review = final_state.get("review") or {
        "decision": "block" if final_state.get("blocked") else "accept",
        "issues": [],
        "revised_hints": [],
    }
    candidates = final_state.get("candidates") or []
    if review.get("decision") == "block" or risk.get("level") == "L3":
        candidates = []

    return {
        "scene": final_state.get("scene") or "daily",
        "dialogue": final_state.get("dialogue") or {},
        "risk": risk,
        "skill": final_state.get("relationship_skill") or {},
        "examples": final_state.get("examples") or [],
        "candidates": candidates,
        "warning": final_state.get("warning") or "",
        "provider": settings.provider,
        "self_skill_ready": persona != "尚未生成个人 Self Skill。",
        "style_brief": final_state.get("style_brief") or {},
        "style_preset_id": final_state.get("style_preset_id") or "",
        "review": review,
        "trace": final_state.get("trace") or [],
        "agent_mode": "langgraph-multi-role",
    }
