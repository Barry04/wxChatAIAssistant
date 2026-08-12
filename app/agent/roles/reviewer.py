from __future__ import annotations

from typing import Any

from app.agent.tools import tool_classify_risk, tool_sanitize_candidates
from app.agent.tracing import make_trace_event, start_timer
from app.models import Contact

UNSAFE_PROMISE_MARKERS = ("我转你", "我保证", "一定去", "明天一定", "我马上转")
ZODIAC_SIGNS = (
    "白羊",
    "金牛",
    "双子",
    "巨蟹",
    "狮子",
    "处女",
    "天秤",
    "天蝎",
    "射手",
    "摩羯",
    "水瓶",
    "双鱼",
)
TOPIC_MISMATCH_MARKERS = {
    "astrology": ("忙完", "晚点回", "处理完", "等我一下"),
    "current_activity": ("星座", "金牛", "双子", "双鱼", "白羊", "天蝎", "摩羯"),
}


def _candidate_issues(
    text: str,
    *,
    dialogue: dict[str, Any],
    boundaries: list[str],
    risk_level: str,
) -> list[str]:
    issues: list[str] = []
    compact = text.strip()
    if not compact:
        issues.append("空候选")
        return issues
    if len(compact) > 80:
        issues.append("超长")
    if dialogue.get("last_message") and compact == dialogue["last_message"]:
        issues.append("复读对方最后一句")
    if tool_classify_risk(compact).get("level") == "L3":
        issues.append("命中高风险关键词")
    if risk_level in {"L1", "L2"} and any(
        marker in compact for marker in UNSAFE_PROMISE_MARKERS
    ):
        issues.append("敏感场景下作出未核实承诺")
    for boundary in boundaries:
        boundary = (boundary or "").strip()
        if boundary and boundary in compact:
            issues.append(f"触碰联系人边界:{boundary}")
    if dialogue.get("dialogue_act") == "affirmation":
        if compact in {"好", "好的", "知道了", "收到", "嗯", "嗯嗯"}:
            issues.append("对确认句机械复读")
    response_action = (dialogue.get("response_plan") or {}).get("action")
    if response_action == "acknowledge_then_explore":
        acknowledgement = ("听", "难", "辛苦", "不容易", "折腾", "确实", "这事", "后来")
        if not any(marker in compact for marker in acknowledgement):
            issues.append("没有先承接连续陈述")
    topic = str(dialogue.get("topic") or "")
    mismatch_markers = TOPIC_MISMATCH_MARKERS.get(topic, ())
    if any(marker in compact for marker in mismatch_markers):
        issues.append(f"候选与当前主题不相关:{topic}")
    if (
        topic == "astrology"
        and str(dialogue.get("last_message") or "").strip() in {"你呢", "那你呢", "你嘞"}
        and any(sign in compact for sign in ZODIAC_SIGNS)
    ):
        issues.append("编造未提供的本人星座")
    return issues


def reviewer_node(state: dict[str, Any]) -> dict[str, Any]:
    started = start_timer()
    contact = Contact.model_validate(state["contact"])
    dialogue = state.get("dialogue") or {}
    risk = state.get("risk") or tool_classify_risk(state.get("conversation", ""))
    risk_level = risk.get("level", "L0")
    candidates = tool_sanitize_candidates(state.get("candidates") or [], dialogue)
    rewrite_count = int(state.get("rewrite_count") or 0)
    warning = state.get("warning") or ""

    all_issues: list[str] = []
    cleaned: list[dict[str, str]] = []
    for item in candidates:
        issues = _candidate_issues(
            item.get("text", ""),
            dialogue=dialogue,
            boundaries=list(contact.boundaries or []),
            risk_level=risk_level,
        )
        if issues:
            all_issues.extend(f"{item.get('label', '候选')}:{issue}" for issue in issues)
            continue
        cleaned.append(item)

    decision = "accept"
    revised_hints: list[str] = []

    if risk_level == "L3":
        decision = "block"
        cleaned = []
        warning = (
            warning
            or "消息涉及高风险信息，系统不会代替你生成可直接发送的回复。"
        )
    elif not cleaned:
        if rewrite_count < 1:
            decision = "revise"
            revised_hints = [
                "删除复读、超长和承诺式表述",
                "只围绕对方最后一句做一个自然推进动作",
                "保持 3-15 个汉字的私人聊天口吻",
                *all_issues[:5],
            ]
        else:
            decision = "block"
            warning = f"{warning} 审核未通过，已阻止输出不安全候选。".strip()
    elif all_issues and rewrite_count < 1 and len(cleaned) < 3:
        decision = "revise"
        revised_hints = [
            "补足三条可用候选",
            "避免客服腔、复读确认和越权承诺",
            *all_issues[:5],
        ]
        # keep currently clean candidates for next pass context
    else:
        decision = "accept"
        if len(cleaned) < 3:
            # pad only with already-sanitized survivors; writer fallback handled upstream
            cleaned = cleaned[:3]

    if risk_level in {"L1", "L2"}:
        safety_warning = "该消息涉及敏感关系或待核实事实，请确认内容后再发送。"
        if safety_warning not in warning:
            warning = f"{warning} {safety_warning}".strip()

    if decision == "block":
        cleaned = []
    elif decision == "accept":
        cleaned = cleaned[:3]

    review = {
        "decision": decision,
        "issues": all_issues,
        "revised_hints": revised_hints,
    }
    next_rewrite = rewrite_count + 1 if decision == "revise" else rewrite_count

    return {
        "candidates": cleaned if decision != "revise" else state.get("candidates") or cleaned,
        "review": review,
        "rewrite_count": next_rewrite,
        "warning": warning,
        "blocked": decision == "block",
        "trace": [
            make_trace_event(
                "reviewer",
                decision,
                started,
                f"decision={decision}, issues={len(all_issues)}, kept={len(cleaned)}",
            )
        ],
    }
