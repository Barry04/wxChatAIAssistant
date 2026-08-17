import csv
import io
import re
from collections import Counter
from typing import Any

from .models import Contact, RuntimeSettings
from .storage import (
    FEEDBACK_FILE,
    MESSAGES_FILE,
    WECHAT_RAW_MESSAGES_FILE,
    PROFILE_FILE,
    append_jsonl,
    load_safety_config,
    load_runtime_config,
    read_json,
    read_jsonl,
    save_runtime_config,
    write_json,
)


SCENE_KEYWORDS = {
    "comfort": ["累", "难过", "委屈", "烦", "崩溃", "不开心", "想哭", "压力", "警察局", "动手", "被打", "报警"],
    "conflict": ["算了", "随便", "你总是", "生气", "吵架", "不想理", "分手", "离婚"],
    "invitation": ["一起", "吃饭", "见面", "周末", "有空", "什么时候", "出来"],
    "joking": ["哈哈", "笑死", "离谱", "666", "绝了", "牛啊"],
    "concern": ["担心", "身体", "休息", "吃饭了吗", "回家", "注意安全"],
}

AFFIRMATIVE_REPLIES = {
    "嗯",
    "嗯嗯",
    "嗯呐",
    "对",
    "对的",
    "是",
    "是的",
    "开了",
    "可以",
    "行",
    "行了",
    "好了",
    "好",
    "知道了",
    "收到",
}

def classify_scene(text: str) -> str:
    compact = text.lower()
    scores = {
        scene: sum(1 for keyword in keywords if keyword.lower() in compact)
        for scene, keywords in SCENE_KEYWORDS.items()
    }
    best_scene, best_score = max(scores.items(), key=lambda item: item[1])
    return best_scene if best_score else "daily"


def classify_risk(text: str) -> dict[str, Any]:
    configured_levels = load_safety_config().get("levels") or {}
    for level in ("L3", "L2", "L1"):
        config = configured_levels.get(level) or {}
        keyword_matches = [
            str(keyword)
            for keyword in config.get("keywords", [])
            if str(keyword) and str(keyword) in text
        ]
        matched = _semantic_risk_matches(text, level, keyword_matches)
        if matched:
            return {
                "level": level,
                "label": str(config.get("label") or level),
                "matched": matched,
            }
    l0 = configured_levels.get("L0") or {}
    return {
        "level": "L0",
        "label": str(l0.get("label") or "普通聊天"),
        "matched": [],
    }


def _semantic_risk_matches(
    text: str,
    level: str,
    keyword_matches: list[str],
) -> list[str]:
    """Require a risky intent pattern instead of escalating on one broad word."""
    if not keyword_matches:
        return []
    compact = re.sub(r"\s+", "", text)

    if level == "L1":
        scheduling_words = ("\u660e\u5929", "\u540e\u5929", "\u4eca\u665a", "\u5468\u672b")
        planning_words = (
            "\u51e0\u70b9",
            "\u4ec0\u4e48\u65f6\u5019",
            "\u4f55\u65f6",
            "\u89c1\u9762",
            "\u5f00\u4f1a",
            "\u884c\u7a0b",
            "\u52a0\u73ed",
        )
        has_schedule_pair = any(
            left in compact and right in compact
            for left in scheduling_words
            for right in planning_words
        )
        has_time_question = any(
            marker in compact
            for marker in ("\u51e0\u70b9", "\u4ec0\u4e48\u65f6\u5019", "\u4f55\u65f6")
        )
        has_commitment = any(
            marker in compact
            for marker in (
                "\u7b54\u5e94",
                "\u4e00\u5b9a",
                "\u884c\u7a0b",
                "\u52a0\u73ed",
            )
        )
        return (
            keyword_matches
            if has_schedule_pair or has_time_question or has_commitment
            else []
        )

    if level == "L2":
        strong_relationship = any(
            marker in compact
            for marker in (
                "\u5206\u624b",
                "\u79bb\u5a5a",
                "\u7edd\u4ea4",
                "\u5435\u67b6",
                "\u4e0d\u60f3\u7406\u4f60",
                "\u4f60\u6eda",
                "\u6eda\u5f00",
            )
        )
        interpersonal_harm = any(
            marker in compact
            for marker in (
                "警察局", "报警", "动手", "打架", "被打", "打人", "威胁"
            )
        )
        return keyword_matches if strong_relationship or interpersonal_harm else []

    if level == "L3":
        direct_high_risk = any(
            marker in compact
            for marker in (
                "\u8f6c\u8d26",
                "\u501f\u94b1",
                "\u9a8c\u8bc1\u7801",
                "\u5bc6\u7801",
                "\u94f6\u884c\u5361",
                "\u5f8b\u5e08",
                "\u5408\u540c",
            )
        )
        medical_request = any(
            marker in compact
            for marker in (
                "\u8be5\u4e0d\u8be5\u5403\u836f",
                "\u5403\u4ec0\u4e48\u836f",
                "\u600e\u4e48\u7528\u836f",
                "\u8981\u4e0d\u8981\u53bb\u533b\u9662",
                "\u533b\u751f\u600e\u4e48\u8bf4",
            )
        )
        return keyword_matches if direct_high_risk or medical_request else []

    return []


def _conversation_lines(conversation: str) -> list[str]:
    return [line.strip() for line in conversation.splitlines() if line.strip()]


def _message_text(line: str) -> str:
    match = re.match(r"^[^:：]{1,30}[:：]\s*(.+)$", line)
    return match.group(1).strip() if match else line.strip()


def _is_self_message(line: str) -> bool:
    return bool(re.match(r"^\s*(?:我|me|自己)[:：]", line, re.IGNORECASE))


def _current_incoming_turn(lines: list[str]) -> list[str]:
    """Extract all consecutive messages received after the user's last turn."""
    turn: list[str] = []
    for line in reversed(lines):
        if _is_self_message(line):
            break
        turn.append(_message_text(line))
    return list(reversed(turn))


def _response_plan(incoming_turn: list[str], last_message: str) -> dict[str, Any]:
    """Make the reply task explicit before any wording is generated."""
    normalized = re.sub(r"\s+", "", last_message).lower()
    if not last_message:
        return {"action": "no_reply", "confidence": 0.0, "reason": "没有可回应的消息"}
    if last_message.endswith(("?", "？")) or re.search(
        r"(吗|么|呢|嘛|咋|怎么|什么|谁|哪|几|多少|为何|为什么|是不是|能不能|可不可以)$",
        normalized,
    ):
        return {"action": "answer_or_clarify", "confidence": 0.86, "reason": "对方提出了明确问题"}
    if normalized in AFFIRMATIVE_REPLIES:
        return {"action": "continue_context", "confidence": 0.82, "reason": "对方作了简短确认"}
    if len(incoming_turn) >= 2 or len("".join(incoming_turn)) > 36:
        return {
            "action": "acknowledge_then_explore",
            "confidence": 0.58,
            "reason": "对方连续陈述，需要先承接完整消息段再追问",
        }
    return {"action": "respond_or_continue", "confidence": 0.76, "reason": "普通单句陈述"}


def analyze_dialogue(conversation: str) -> dict[str, Any]:
    """Extract the minimum turn-level context needed for a natural next reply."""
    lines = _conversation_lines(conversation)
    texts = [_message_text(line) for line in lines]
    last = texts[-1] if texts else ""
    previous = texts[-2] if len(texts) > 1 else ""
    incoming_turn = _current_incoming_turn(lines)
    turn_text = "\n".join(incoming_turn) or last
    response_plan = _response_plan(incoming_turn, last)
    normalized = re.sub(r"\s+", "", last).lower()

    if not last:
        act = "empty"
    elif normalized in AFFIRMATIVE_REPLIES:
        act = "affirmation"
    elif last.endswith(("?", "？")) or re.search(
        r"(吗|么|呢|嘛|咋|怎么|什么|谁|哪|几|多少|为何|为什么|是不是|能不能|可不可以)$",
        normalized,
    ):
        act = "question"
    elif any(token in last for token in ("哈哈", "笑死", "666", "离谱", "绝了")):
        act = "joking"
    elif len(last) <= 4:
        act = "short_update"
    else:
        act = "statement"

    topic = "general"
    topic_keywords = {
        "finance": ("股票", "股市", "创业板", "基金", "ETF", "买入", "卖出", "开户"),
        "meeting": ("见面", "吃饭", "周末", "几点", "有空", "出来"),
        "work": ("上班", "加班", "开会", "工作", "项目"),
        "current_activity": ("在干嘛", "干嘛呢", "忙什么", "做什么呢"),
        "astrology": ("星座", "金牛", "双子", "双鱼", "白羊", "天蝎", "摩羯"),
        "affection": ("想我", "想你"),
    }
    # Topic and response action are decided by the complete unanswered turn,
    # with a small preceding window only for references such as “这个/那件事”.
    context = " ".join((texts[-6:-len(incoming_turn)] if incoming_turn else texts[-4:]) + incoming_turn)
    for candidate, keywords in topic_keywords.items():
        if any(keyword in context for keyword in keywords):
            topic = candidate
            break

    return {
        "last_message": last,
        "previous_message": previous,
        "incoming_turn": incoming_turn,
        "incoming_turn_text": turn_text,
        "response_plan": response_plan,
        "dialogue_act": act,
        "topic": topic,
        "has_prior_context": len(texts) > 1,
    }


def parse_plain_text(
    content: str,
    contact_id: str,
    relationship: str,
    self_label: str = "我",
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    incoming: list[str] = []
    replies: list[str] = []
    aliases = {self_label.strip().lower(), "我", "me", "自己"}

    def flush() -> None:
        if incoming and replies:
            joined = "\n".join(incoming)
            records.append(
                {
                    "contact_id": contact_id,
                    "relationship": relationship,
                    "scene": classify_scene(joined),
                    "incoming": incoming.copy(),
                    "my_reply": replies.copy(),
                    "source": "import",
                }
            )

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^([^:：]{1,30})[:：]\s*(.+)$", line)
        if not match:
            continue
        speaker, text = match.group(1).strip().lower(), match.group(2).strip()
        if speaker in aliases:
            if incoming:
                replies.append(text)
        else:
            if replies:
                flush()
                incoming, replies = [], []
            incoming.append(text)
    flush()
    return records


def parse_csv_bytes(
    content: bytes,
    contact_id: str,
    relationship: str,
    self_label: str = "我",
) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    lines = []
    for row in reader:
        speaker = row.get("speaker") or row.get("发送者") or row.get("sender") or ""
        message = row.get("text") or row.get("内容") or row.get("message") or ""
        if speaker and message:
            lines.append(f"{speaker}: {message}")
    return parse_plain_text("\n".join(lines), contact_id, relationship, self_label)


def import_records(records: list[dict[str, Any]]) -> int:
    existing_ids = {
        row.get("source_record_id")
        for row in read_jsonl(MESSAGES_FILE)
        if row.get("source_record_id")
    }
    imported = 0
    for record in records:
        source_record_id = record.get("source_record_id")
        if source_record_id and source_record_id in existing_ids:
            continue
        append_jsonl(MESSAGES_FILE, record)
        imported += 1
        if source_record_id:
            existing_ids.add(source_record_id)
    return imported


def import_raw_messages(messages: list[dict[str, Any]]) -> int:
    existing_ids = {
        row.get("source_message_id")
        for row in read_jsonl(WECHAT_RAW_MESSAGES_FILE)
        if row.get("source_message_id")
    }
    imported = 0
    for message in messages:
        source_id = message.get("source_message_id")
        if source_id and source_id in existing_ids:
            continue
        append_jsonl(WECHAT_RAW_MESSAGES_FILE, message)
        imported += 1
        if source_id:
            existing_ids.add(source_id)
    return imported


def _bigrams(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", text.lower())
    if len(compact) < 2:
        return {compact} if compact else set()
    return {compact[index : index + 2] for index in range(len(compact) - 1)}


def retrieve_examples(
    conversation: str,
    contact: Contact,
    scene: str,
    limit: int = 4,
) -> list[dict[str, Any]]:
    query = _bigrams(conversation)
    scored: list[tuple[float, dict[str, Any]]] = []
    for record in read_jsonl(MESSAGES_FILE):
        if record.get("source") == "demo" and not contact.is_demo:
            continue
        same_contact = record.get("contact_id") == contact.contact_id
        same_relationship = record.get("relationship") == contact.relationship
        if not same_contact and not same_relationship:
            continue
        if record.get("chat_type") == "group" and not same_contact:
            continue
        incoming = " ".join(record.get("incoming", []))
        features = _bigrams(incoming)
        overlap = len(query & features) / max(1, len(query | features))
        if not same_contact and overlap <= 0:
            continue
        score = overlap
        score += 0.75 if same_contact else 0.08
        score += 0.18 if record.get("scene") == scene else 0
        if record.get("source") == "feedback":
            score += 0.2
        if record.get("chat_type") == "private":
            score += 0.05
        scored.append((score, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {**record, "score": round(score, 3)}
        for score, record in scored[:limit]
        if score > 0.1
    ]


def distill_profile() -> dict[str, Any]:
    # 与 Self Skill 共用样本过滤：排除 demo，且大群（>10 人）不进入画像。
    from .self_skill import _real_records

    records = _real_records()
    replies = [
        message.strip()
        for record in records
        for message in record.get("my_reply", [])
        if message.strip()
    ]
    if not replies:
        profile = {
            "sample_count": 0,
            "summary": "尚未使用你的聊天记录进行风格提炼。",
            "expression_dna": [],
            "relationship_profiles": {},
        }
        write_json(PROFILE_FILE, profile)
        return profile

    average_length = round(sum(len(item) for item in replies) / len(replies), 1)
    punctuation = Counter(char for item in replies for char in item if char in "，。！？～~…")
    endings = Counter(item[-2:] for item in replies if len(item) >= 2)
    emoji_count = sum(
        1
        for item in replies
        if re.search(r"[\U0001F300-\U0001FAFF]|哈哈|嘿嘿|hhh|233", item)
    )

    dna = [
        f"平均每条回复约 {average_length} 个字符",
        f"表情或笑声出现在约 {round(emoji_count / len(replies) * 100)}% 的样本中",
    ]
    if punctuation:
        dna.append("常用标点：" + "、".join(item[0] for item in punctuation.most_common(4)))
    if endings:
        dna.append("常见结尾：" + "、".join(item[0] for item in endings.most_common(5)))

    relation_profiles: dict[str, Any] = {}
    for relationship in ("partner", "friend", "family"):
        relation_replies = [
            reply
            for record in records
            if record.get("relationship") == relationship
            for reply in record.get("my_reply", [])
        ]
        if relation_replies:
            relation_profiles[relationship] = {
                "sample_count": len(relation_replies),
                "average_length": round(
                    sum(len(item) for item in relation_replies) / len(relation_replies),
                    1,
                ),
                "common_endings": [
                    item[0]
                    for item in Counter(
                        reply[-2:] for reply in relation_replies if len(reply) >= 2
                    ).most_common(5)
                ],
            }

    profile = {
        "sample_count": len(replies),
        "summary": f"已从 {len(replies)} 条本人回复中生成轻量表达画像。",
        "expression_dna": dna,
        "relationship_profiles": relation_profiles,
    }
    write_json(PROFILE_FILE, profile)
    return profile


LENGTH_NOTES = {
    "very_short": "尽量 4-8 个汉字，一句说完",
    "short": "保持 8-15 个汉字的微信口吻",
    "medium": "可以稍长到 20 字，但仍是一条消息",
}
EMOJI_NOTES = {
    "none": "不要使用表情符号",
    "low": "通常不用表情，必要时最多一个",
    "medium": "可以自然带一个语气延展或轻表情",
    "high": "适当使用表情或「哈哈」类语气",
}
HUMOR_NOTES = {
    "low": "克制，少开玩笑",
    "medium": "自然轻松，不要硬搞笑",
    "high": "可以更活泼、带点玩笑",
}
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0000FE00-\U0000FE0F"
    "\U0001F1E6-\U0001F1FF"
    "]+"
)
_LAUGH_RE = re.compile(r"(哈){2,}|hhh+|lol", re.I)


def contact_style_instructions(contact: Contact) -> dict[str, Any]:
    return {
        "preferred_address": contact.preferred_address,
        "message_length": contact.message_length,
        "message_length_rule": LENGTH_NOTES[contact.message_length],
        "emoji_level": contact.emoji_level,
        "emoji_rule": EMOJI_NOTES[contact.emoji_level],
        "humor_level": contact.humor_level,
        "humor_rule": HUMOR_NOTES[contact.humor_level],
        "boundaries": list(contact.boundaries or []),
    }


def _shorten_reply(text: str, max_chars: int = 8) -> str:
    compact = text.strip()
    if len(compact) <= max_chars:
        return compact
    if compact.endswith(("?", "？")):
        tail = re.split(r"[，,。]", compact)[-1].strip()
        if 2 <= len(tail) <= max_chars + 4:
            return tail
    for sep in ("，", ",", "。"):
        if sep in compact:
            head = compact.split(sep, 1)[0].strip()
            if 2 <= len(head) <= max_chars + 4:
                return head
    return compact[:max_chars]


def _apply_contact_preferences(
    texts: list[str],
    contact: Contact,
    scene: str = "daily",
) -> list[str]:
    styled: list[str] = []
    playful_scenes = {"daily", "joking", "invitation"}
    for index, text in enumerate(texts):
        item = re.sub(r"\s+", " ", text.strip())
        if contact.emoji_level == "none":
            item = _EMOJI_RE.sub("", item).strip()
        if contact.humor_level == "low":
            item = _LAUGH_RE.sub("", item)
            item = re.sub(r"\s+", " ", item).strip(" ，,")
        if contact.message_length == "very_short":
            item = _shorten_reply(item)
        if (
            contact.emoji_level == "high"
            and index == 0
            and item
            and not _EMOJI_RE.search(item)
        ):
            item = f"{item}{'😄' if contact.humor_level != 'low' else '～'}"
        elif (
            contact.emoji_level == "medium"
            and index == 0
            and item
            and not _EMOJI_RE.search(item)
            and not item.endswith("～")
        ):
            item = f"{item}～"
        if (
            contact.humor_level == "high"
            and contact.relationship != "family"
            and scene in playful_scenes
            and index == 0
            and item
            and "哈" not in item
            and not item.endswith(("?", "？"))
        ):
            item = f"{item}哈哈"
        styled.append(item or text.strip())
    return styled


def _demo_candidates(
    contact: Contact,
    scene: str,
    examples: list[dict[str, Any]],
    dialogue: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    address = contact.preferred_address.strip()
    prefix = f"{address}，" if address else ""
    templates = {
        "partner": {
            "comfort": [
                f"怎么啦，{address or '你'}，先别一个人扛着，跟我说说",
                f"{prefix}今天辛苦了，先歇一会儿，我陪你",
                "抱抱，慢慢说，我在听",
            ],
            "conflict": [
                "我知道你现在不舒服，我不想敷衍你，你把想说的说完",
                "先别急着下结论，我们把这件事慢慢说清楚",
                "我在听，这件事我会认真回应",
            ],
            "invitation": [
                f"可以呀{address and '，' + address or ''}，咱们把时间定一下",
                "好呀，你想什么时候去？",
                "可以，时间定了跟我说",
            ],
            "daily": [
                f"知道啦{address and '，' + address or ''}，我忙完就找你",
                "好，我这边处理完跟你说",
                "收到，晚点回你",
            ],
        },
        "friend": {
            "comfort": [
                "咋了，发生啥了？说来听听",
                "先缓缓，别一个人憋着",
                "来，说说咋回事",
            ],
            "conflict": [
                "先别上火，咱把这事说清楚",
                "行，我先听你说完",
                "别急，慢慢说",
            ],
            "invitation": ["行啊，整起", "可以，啥时候？", "走，时间发我"],
            "joking": ["不愧是你哈哈哈", "你是真的离谱", "行，这很有你的风格"],
            "daily": ["行，晚点说", "收到，等我一下", "懂了懂了"],
        },
        "family": {
            "comfort": [
                "怎么了？你慢慢说，我在听",
                "先别着急，我们一起想办法",
                "你先休息一下，有事跟我说",
            ],
            "concern": [
                "知道了，我会注意，你别担心",
                "我这边没事，安排好会告诉你",
                "好，我记着了",
            ],
            "conflict": [
                "先别生气，咱们慢慢说",
                "我知道你是担心我，我认真跟你说",
                "这件事我们晚点好好商量",
            ],
            "invitation": [
                "可以，你把时间告诉我，我安排一下",
                "好，确定后跟我说一声",
                "行，我先看看时间",
            ],
            "daily": [
                "知道了，我安排好会跟你说",
                "好，我记住了",
                "行，晚点我再确认一下",
            ],
        },
    }
    relation_templates = templates[contact.relationship]
    selected = relation_templates.get(scene, relation_templates["daily"]).copy()
    dialogue = dialogue or {}
    response_action = (dialogue.get("response_plan") or {}).get("action")
    if response_action == "acknowledge_then_explore":
        selected = [
            "听着确实挺折腾的，后来呢？",
            "难怪你这么说，接着说说？",
            "这事不容易，你后来怎么弄的？",
        ]
    previous_message = dialogue.get("previous_message", "")
    if response_action != "acknowledge_then_explore" and (
        dialogue.get("dialogue_act") == "affirmation"
        and dialogue.get("has_prior_context")
    ):
        if dialogue.get("topic") == "finance":
            selected = [
                "那准备买啥？",
                "那可以，准备看哪个？",
                "准备上哪个？",
            ]
        elif dialogue.get("topic") == "meeting":
            selected = [
                "那时间定了吗？",
                "那啥时候？",
                "那到时候说一声。",
            ]
        elif previous_message.endswith(("?", "？")):
            selected = [
                "那就行，后面咋安排？",
                "那可以，接下来呢？",
                "行，知道了。",
            ]
    elif dialogue.get("dialogue_act") == "question":
        topic = dialogue.get("topic")
        last_message = str(dialogue.get("last_message") or "")
        if topic == "current_activity":
            selected = [
                "刚看到，咋啦？",
                "怎么啦，找我呀？",
                "在呢，咋啦？",
            ]
        elif topic == "astrology":
            selected = [
                "你猜猜看？",
                "你觉得我像什么星座？",
                "先猜一个哈哈",
            ]
        elif topic == "affection":
            selected = [
                "你猜呢？",
                "那肯定想了呀",
                "想了想了",
            ]
        elif last_message in {"你呢", "那你呢", "你嘞"}:
            selected = [
                "你猜猜？",
                "你觉得呢？",
                "先猜一个",
            ]
        else:
            selected = [
                "你先说说看？",
                "这个我还真不确定，你咋想的？",
                "咋了，具体说说？",
            ]
    example_text = ""
    if examples and dialogue.get("dialogue_act") not in {"affirmation", "question"}:
        candidate_example = " ".join(examples[0].get("my_reply", [])).strip()
        if (
            examples[0].get("contact_id") == contact.contact_id
            and candidate_example
            and re.search(r"[\u4e00-\u9fffA-Za-z0-9]", candidate_example)
            and candidate_example not in selected
        ):
            example_text = candidate_example
    if example_text:
        selected[0] = example_text
    selected = _apply_contact_preferences(selected, contact, scene)
    labels = ["最像我", "更温和", "更简短"]
    return [{"label": label, "text": text} for label, text in zip(labels, selected)]




def _sanitize_candidates(
    candidates: list[dict[str, str]],
    dialogue: dict[str, Any],
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in candidates:
        text = re.sub(r"\s+", " ", str(item.get("text", "")).strip())
        if not text or text in seen:
            continue
        if len(text) > 80:
            continue
        if dialogue.get("last_message") and text == dialogue["last_message"]:
            continue
        seen.add(text)
        cleaned.append(
            {
                "label": str(item.get("label", "候选")).strip() or "候选",
                "text": text,
            }
        )
    return cleaned[:3]


async def generate_reply(
    contact: Contact,
    conversation: str,
    settings: RuntimeSettings,
    style_preset_id: str = "",
) -> dict[str, Any]:
    """Generate draft replies via the LangGraph multi-role agent runtime."""
    # Local import avoids circular dependency: agent.tools -> services helpers.
    from app.agent.graph import run_generate_agent

    return await run_generate_agent(
        contact,
        conversation,
        settings,
        style_preset_id=style_preset_id,
    )


def save_feedback(
    contact: Contact,
    conversation: str,
    selected_text: str,
    final_text: str,
    scene: str,
) -> None:
    feedback = {
        "contact_id": contact.contact_id,
        "relationship": contact.relationship,
        "conversation": conversation,
        "selected_text": selected_text,
        "final_text": final_text,
        "scene": scene,
    }
    append_jsonl(FEEDBACK_FILE, feedback)
    append_jsonl(
        MESSAGES_FILE,
        {
            "contact_id": contact.contact_id,
            "relationship": contact.relationship,
            "scene": scene,
            "incoming": [conversation],
            "my_reply": [final_text],
            "source": "feedback",
        },
    )
    from .self_skill import distill_self_skill

    distill_self_skill()


def get_public_settings() -> dict[str, Any]:
    stored = load_runtime_config()
    return {**stored, "api_key": ""}


def get_runtime_settings() -> RuntimeSettings:
    stored = load_runtime_config()
    return RuntimeSettings(**stored)


def save_public_settings(settings: RuntimeSettings) -> None:
    save_runtime_config(settings.model_dump())


def corpus_stats() -> dict[str, Any]:
    records = read_jsonl(MESSAGES_FILE)
    raw_messages = read_jsonl(WECHAT_RAW_MESSAGES_FILE)
    feedback = read_jsonl(FEEDBACK_FILE)
    imported = [item for item in records if item.get("source") != "demo"]
    relationships = Counter(item.get("relationship", "unknown") for item in imported)
    return {
        "records": len(imported),
        "raw_messages": len(raw_messages),
        "feedback": len(feedback),
        "relationships": relationships,
        "demo_records": len(records) - len(imported),
        "profile": read_json(PROFILE_FILE, {}),
    }
