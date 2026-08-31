from __future__ import annotations

from typing import Any

from app.agent.tools import (
    tool_contact_style_instructions,
    tool_load_persona,
    tool_load_profile,
    tool_load_relationship_skill,
    tool_retrieve_examples,
)
from app.agent.tracing import make_trace_event, start_timer
from app.memory import get_summary, relevant_facts
from app.models import Contact
from app.self_skill import get_style_prompt


def style_node(state: dict[str, Any]) -> dict[str, Any]:
    started = start_timer()
    contact = Contact.model_validate(state["contact"])
    scene = state.get("scene") or "daily"
    dialogue = state.get("dialogue") or {}
    conversation = state["conversation"]

    skill = tool_load_relationship_skill(contact.relationship)
    requested_preset = str(state.get("style_preset_id") or "").strip()
    stored_preset = str(contact.style_preset_id or "").strip()
    style_preset_id = (
        requested_preset
        if requested_preset.startswith("style:")
        else stored_preset
        if stored_preset.startswith("style:")
        else ""
    )
    persona = get_style_prompt(contact.contact_id, style_preset_id)
    profile = tool_load_profile()
    # 选择类型风格时只使用聚合表达统计；避免把某个联系人的称呼、事实或历史带入新对话。
    examples = (
        []
        if style_preset_id.startswith("style:")
        else tool_retrieve_examples(conversation, contact, scene)
    )

    principles = skill.get("principles") or []
    style_prefs = tool_contact_style_instructions(contact)
    try:
        facts = relevant_facts(contact.contact_id, conversation)
        memory_summary = get_summary(contact.contact_id)
    except Exception:
        facts, memory_summary = [], ""
    style_brief = {
        "relationship": contact.relationship,
        "preferred_address": contact.preferred_address,
        "message_length": contact.message_length,
        "emoji_level": contact.emoji_level,
        "humor_level": contact.humor_level,
        "message_length_rule": style_prefs["message_length_rule"],
        "emoji_rule": style_prefs["emoji_rule"],
        "humor_rule": style_prefs["humor_rule"],
        "style_preset_id": style_preset_id or "global",
        "style_source": (
            "aggregate_style"
            if style_preset_id.startswith("style:")
            else "contact_or_relationship_history"
        ),
        "boundaries": list(contact.boundaries or []),
        "scene": scene,
        "dialogue_act": dialogue.get("dialogue_act"),
        "topic": dialogue.get("topic"),
        "last_message": dialogue.get("last_message"),
        "previous_message": dialogue.get("previous_message"),
        "incoming_turn": dialogue.get("incoming_turn", []),
        "response_plan": dialogue.get("response_plan", {}),
        "principles": principles[:6],
        "example_replies": [
            " ".join(item.get("my_reply", [])).strip()
            for item in examples[:3]
            if item.get("my_reply")
        ],
        "facts": facts,
        "memory_summary": memory_summary,
        "rules": [
            "优先回应对方当前连续发送的整段消息；最后一句只是其中一个片段",
            "先满足 response_plan.action，再考虑幽默、评价或话题推进",
            "一条候选只做一个交流动作",
            "不编造位置、行程、健康、金钱决定或重大关系承诺",
            "不编造用户本人的星座、年龄、职业、所在地或其他未提供事实",
            "只使用当前联系人已记录事实；低置信度事实视为可能，不得迁移到其他人",
            "对方追问未提供的本人事实时，用自然反问或请对方猜，不得直接声明",
            "affirmation 不要机械复读确认，应结合上一句推进",
            "对方已回答的问题不要再答一遍",
            "用户最终反馈文本优先级高于模型习惯",
            style_prefs["message_length_rule"],
            style_prefs["emoji_rule"],
            style_prefs["humor_rule"],
        ],
    }

    return {
        "relationship_skill": skill,
        "persona": persona,
        "profile": profile,
        "style_preset_id": style_preset_id,
        "examples": examples,
        "style_brief": style_brief,
        "trace": [
            make_trace_event(
                "style",
                "ok",
                started,
                f"examples={len(examples)}, persona_ready={persona != '尚未生成个人 Self Skill。'}",
            )
        ],
    }
