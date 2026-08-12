from __future__ import annotations

import json
from typing import Any

from app.agent.llm import chat_completion, extract_json
from app.agent.tools import tool_demo_candidates, tool_sanitize_candidates
from app.agent.tracing import make_trace_event, start_timer
from app.models import Contact, RuntimeSettings


def _build_writer_prompt(state: dict[str, Any]) -> str:
    return f"""
你是一个只生成私人聊天草稿的中文写手角色。不要替用户编造事实、承诺、位置、行程或金钱决定。
你的任务是接住对方当前尚未回复的连续消息，生成下一条可以直接发送的微信消息；最后一句只是这段消息的一部分。不要总结整段对话。
优先级：当前未回复消息段 > 紧邻上下文 > 同一联系人历史 > 同关系历史 > 通用关系规则。
不得编造用户本人的星座、年龄、职业、所在地或其他未提供事实。对方追问未知的本人事实时，使用自然反问或请对方猜。
如果对方只是“嗯/开了/可以/好”等确认，不要重复确认；结合上一句提出一个自然的下一步追问。
如果对方已经回答了问题，不要再回答已经结束的问题，也不要突然切换成客服式关心。
必须先满足 response_plan.action；当动作为 acknowledge_then_explore 时，先承接对方的完整陈述再追问，不能只针对末句评价、调侃或转换话题。
如果当前或紧邻上下文涉及警察介入、动手、受伤、威胁或其他人身冲突，先承接惊吓或不适并关心对方是否安全；绝不能用“幸运、还好、活该、你也挺能”的口吻淡化、调侃或归因。
每条候选只保留一个交流动作，通常 3-15 个汉字；除非确有必要，不要连续提出两个问题。

写作约束 style_brief：
{json.dumps(state.get("style_brief") or {}, ensure_ascii=False)}

基础人格画像：
{json.dumps(state.get("profile") or {}, ensure_ascii=False)}

个人 Self Skill：
{state.get("persona") or "尚未生成个人 Self Skill。"}

关系 Skill：
{json.dumps(state.get("relationship_skill") or {}, ensure_ascii=False)}

联系人档案：
{json.dumps(state.get("contact") or {}, ensure_ascii=False)}

当前场景：{state.get("scene")}
当前对话动作与主题：
{json.dumps(state.get("dialogue") or {}, ensure_ascii=False)}
风险等级：{(state.get("risk") or {}).get("level")} {(state.get("risk") or {}).get("label")}

相似历史回复：
{json.dumps(state.get("examples") or [], ensure_ascii=False)}

当前聊天：
{state.get("conversation")}

审核修改提示（若有）：
{json.dumps((state.get("review") or {}).get("revised_hints") or [], ensure_ascii=False)}

生成三个自然、简短且风格有差异的候选回复，标签固定为“最像我”“更温和”“更简短”。
只输出 JSON：
{{"candidates":[{{"label":"最像我","text":"..." }},{{"label":"更温和","text":"..."}},{{"label":"更简短","text":"..."}}]}}
""".strip()


async def writer_node(state: dict[str, Any]) -> dict[str, Any]:
    started = start_timer()
    contact = Contact.model_validate(state["contact"])
    settings = RuntimeSettings.model_validate(state["settings"])
    scene = state.get("scene") or "daily"
    dialogue = state.get("dialogue") or {}
    examples = state.get("examples") or []
    warning = state.get("warning") or ""
    status = "ok"

    if settings.provider == "demo":
        candidates = tool_demo_candidates(contact, scene, examples, dialogue)
    else:
        prompt = _build_writer_prompt(state)
        try:
            content = await chat_completion(settings, prompt)
            payload = extract_json(content)
            candidates = tool_sanitize_candidates(
                payload.get("candidates", []),
                dialogue,
            )
            if len(candidates) < 3:
                raise ValueError("模型返回的候选不足")
        except Exception as exc:  # noqa: BLE001 - fallback is intentional
            candidates = tool_demo_candidates(contact, scene, examples, dialogue)
            warning = f"{warning} 模型连接失败，已回退到离线生成：{exc}".strip()
            status = "fallback"

    candidates = tool_sanitize_candidates(candidates, dialogue)
    if not candidates:
        candidates = tool_sanitize_candidates(
            tool_demo_candidates(contact, scene, [], dialogue),
            dialogue,
        )
        status = "fallback"

    return {
        "candidates": candidates,
        "warning": warning,
        "trace": [
            make_trace_event(
                "writer",
                status,
                started,
                f"candidates={len(candidates)}, provider={settings.provider}",
            )
        ],
    }
