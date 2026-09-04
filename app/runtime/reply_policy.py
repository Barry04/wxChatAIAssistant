"""自然对话回合策略。

真人聊天不会把对方连发的几条拆开逐条应答，也不会在聊到新话题之后，
回头把旧消息一条条补完。这里把这种习惯写成显式规则，供 Watcher 与
Orchestrator 在入队前调用。

规则只决定「现在该不该回 / 回哪一轮 / 何时出队」，不改变 L0-L3
发送门禁：策略永远不会绕过 PolicyGate 或 Operator 边界。
"""

from __future__ import annotations

import re
from typing import Any

# 相邻对方消息间隔超过该阈值时，视为话题边界（一期启发式，宁可保守）。
STALE_GAP_SECONDS = 6 * 3600

# 与服务层 AFFIRMATIVE_REPLIES 对齐的短确认集合；策略层额外覆盖
# 「好/行/可以」等口语确认，用于判断这轮是否只是对方在收尾。
AFFIRMATIVE_TEXTS = {
    "嗯",
    "嗯嗯",
    "嗯呐",
    "对",
    "对的",
    "是",
    "是的",
    "开了",
    "好",
    "好的",
    "好呀",
    "行",
    "可以",
    "ok",
    "okay",
}

_QUESTION_SUFFIX = re.compile(
    r"(吗|么|呢|嘛|咋|怎么|什么|谁|哪|几|多少|为何|为什么|是不是|能不能|可不可以)$"
)

_TOPIC_KEYWORDS = {
    "finance": ("股票", "股市", "创业板", "基金", "ETF", "买入", "卖出", "开户"),
    "meeting": ("见面", "吃饭", "周末", "几点", "有空", "出来"),
    "work": ("上班", "加班", "开会", "工作", "项目"),
    "current_activity": ("在干嘛", "干嘛呢", "忙什么", "做什么呢"),
    "astrology": ("星座", "金牛", "双子", "双鱼", "白羊", "天蝎", "摩羯"),
    "affection": ("想我", "想你"),
}


def message_local_id(message: dict[str, Any]) -> int:
    return int((message.get("id") or {}).get("local_id") or 0)


def message_create_time(message: dict[str, Any]) -> int:
    return int(message.get("create_time") or 0)


def message_text(message: dict[str, Any]) -> str:
    return str(message.get("text") or "")


def _normalized(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def is_affirmative(text: str) -> bool:
    return _normalized(text) in AFFIRMATIVE_TEXTS


def is_question(text: str) -> bool:
    normalized = _normalized(text)
    return text.endswith(("?", "？")) or bool(_QUESTION_SUFFIX.search(normalized))


def topic_label(text: str) -> str:
    for label, keywords in _TOPIC_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return label
    return "general"


def split_incoming_turn(
    incoming: list[dict[str, Any]],
    *,
    stale_gap_seconds: int = STALE_GAP_SECONDS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """把本人最后回复之后的对方消息切分为（当前轮, 过时片段）。

    边界启发式（第一期，宁可保守）：
    - 相邻消息时间间隔超过 ``stale_gap_seconds``；
    - 或前后消息命中不同且都明确的话题关键词组。
    新消息以短确认开头时视为对前文的回应，不开启新轮；
    最后一个边界之后的内容是「正在聊的这一轮」，更早的片段过时。
    """
    if len(incoming) <= 1:
        return incoming, []
    boundary = 0
    for index in range(1, len(incoming)):
        previous = incoming[index - 1]
        current = incoming[index]
        current_text = message_text(current)
        if is_affirmative(current_text):
            continue
        time_gap = (
            message_create_time(current) - message_create_time(previous)
        ) >= stale_gap_seconds
        previous_topic = topic_label(message_text(previous))
        current_topic = topic_label(current_text)
        clear_topic_shift = (
            previous_topic != current_topic
            and previous_topic != "general"
            and current_topic != "general"
        )
        if time_gap or clear_topic_shift:
            boundary = index
    if boundary == 0:
        return incoming, []
    return incoming[boundary:], incoming[:boundary]


def turn_is_ack_only(
    incoming: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> bool:
    """整轮只是对方短确认、且本人上一条不是待跟进的问题时，无需再开待确认。"""
    if not incoming:
        return False
    if not all(is_affirmative(message_text(message)) for message in incoming):
        return False
    last_own = next(
        (message for message in reversed(messages) if message.get("is_from_me")),
        None,
    )
    if last_own is None:
        return True
    return not is_question(message_text(last_own))


def pending_items_for_talker(
    pending: list[dict[str, Any]],
    talker: str,
) -> list[dict[str, Any]]:
    return [item for item in pending if item.get("talker") == talker]


def drop_pending_for_talker(
    pending: list[dict[str, Any]],
    talker: str,
) -> list[dict[str, Any]]:
    """原地移除该 talker 的待确认项，返回被移除的项以便记录可观察动作。"""
    kept: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for item in pending:
        if item.get("talker") == talker:
            removed.append(item)
        else:
            kept.append(item)
    pending[:] = kept
    return removed
