import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .chat_analysis import analyze_chat_records
from .storage import (
    CONTACT_SKILL_DIR,
    GIRLS_CHAT_STYLE_FILE,
    MESSAGES_FILE,
    PERSONA_FILE,
    SELF_MEMORY_FILE,
    SELF_SKILL_META_FILE,
    WECHAT_RAW_MESSAGES_FILE,
    read_json,
    read_jsonl,
    write_json,
)


RELATIONSHIP_LABELS = {
    "partner": "partner",
    "friend": "friend",
    "family": "family",
}


DISTILLATION_WINDOW_DAYS = 365


def _distillation_cutoff_timestamp(now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    return int((current - timedelta(days=DISTILLATION_WINDOW_DAYS)).timestamp())


def _row_timestamp(row: dict[str, Any]) -> int:
    for key in ("create_time", "timestamp", "last_reply_at"):
        value = row.get(key)
        if value:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    for key in ("incoming_times", "reply_times"):
        values = row.get(key)
        if isinstance(values, list):
            timestamps = []
            for value in values:
                try:
                    timestamps.append(int(value))
                except (TypeError, ValueError):
                    continue
            if timestamps:
                return max(timestamps)
    return 0


def _recent_rows(
    rows: list[dict[str, Any]],
    *,
    cutoff_timestamp: int | None = None,
) -> tuple[list[dict[str, Any]], set[str]]:
    """Return rows belonging to sessions active within the distillation window."""
    cutoff = (
        cutoff_timestamp
        if cutoff_timestamp is not None
        else _distillation_cutoff_timestamp()
    )
    latest_by_session: dict[str, int] = {}
    for row in rows:
        session_id = str(
            row.get("wechat_talker") or row.get("contact_id") or ""
        ).strip()
        if not session_id:
            continue
        latest_by_session[session_id] = max(
            latest_by_session.get(session_id, 0),
            _row_timestamp(row),
        )
    # Unit fixtures and old hand-written demo records may omit timestamps or
    # use tiny synthetic values such as 100/120. Real Unix timestamps are
    # already above this compatibility boundary.
    if latest_by_session and (
        max(latest_by_session.values()) == 0
        or (
            cutoff_timestamp is None
            and max(latest_by_session.values()) < 1_000_000_000
        )
    ):
        return rows, set(latest_by_session)
    recent_sessions = {
        session_id
        for session_id, latest_timestamp in latest_by_session.items()
        if latest_timestamp >= cutoff
    }
    return (
        [
            row
            for row in rows
            if str(
                row.get("wechat_talker") or row.get("contact_id") or ""
            ).strip()
            in recent_sessions
        ],
        recent_sessions,
    )

GOODNIGHT_RE = re.compile(r"(?:晚安|安安|good\s*night|goodnight)", re.I)


def _goodnight_count(text: str) -> int:
    return len(GOODNIGHT_RE.findall(text or ""))


def _girls_chat_candidates(
    raw_messages: list[dict[str, Any]] | None = None,
    *,
    recent_only: bool = False,
) -> list[dict[str, Any]]:
    """Find private-chat candidates from explainable mutual goodnight turns."""
    rows = raw_messages if raw_messages is not None else read_jsonl(WECHAT_RAW_MESSAGES_FILE)
    if recent_only:
        rows, _ = _recent_rows(rows)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("chat_type") != "private":
            continue
        talker = str(row.get("wechat_talker") or row.get("contact_id") or "").strip()
        text = str(row.get("text") or "").strip()
        if not talker or not text or not _goodnight_count(text):
            continue
        grouped[talker].append(row)

    candidates: list[dict[str, Any]] = []
    for talker, messages in grouped.items():
        messages.sort(key=lambda item: int(item.get("create_time") or 0))
        mutual = 0
        other_count = 0
        self_count = 0
        last_goodnight_side: bool | None = None
        last_goodnight_time = 0
        for row in messages:
            is_self = bool(row.get("is_from_me"))
            count = _goodnight_count(str(row.get("text") or ""))
            if is_self:
                self_count += count
            else:
                other_count += count
            timestamp = int(row.get("create_time") or 0)
            if (
                last_goodnight_side is not None
                and last_goodnight_side != is_self
                and (
                    not timestamp
                    or not last_goodnight_time
                    or timestamp - last_goodnight_time <= 12 * 3600
                )
            ):
                mutual += 1
            last_goodnight_side = is_self
            last_goodnight_time = timestamp
        if not mutual:
            continue
        display_name = next(
            (
                str(row.get("display_name") or "").strip()
                for row in messages
                if str(row.get("display_name") or "").strip()
            ),
            talker,
        )
        candidates.append(
            {
                "talker": talker,
                "contact_id": next(
                    (
                        str(row.get("contact_id") or "").strip()
                        for row in messages
                        if row.get("contact_id")
                    ),
                    f"wechat:{talker}",
                ),
                "display_name": display_name,
                "mutual_goodnight_count": mutual,
                "other_goodnight_count": other_count,
                "self_goodnight_count": self_count,
                "private_raw_message_count": sum(
                    1 for row in rows
                    if row.get("chat_type") == "private"
                    and str(row.get("wechat_talker") or row.get("contact_id") or "").strip() == talker
                ),
            }
        )
    return sorted(
        candidates,
        key=lambda item: (
            item["mutual_goodnight_count"],
            item["private_raw_message_count"],
        ),
        reverse=True,
    )


def distill_girls_chat_style() -> dict[str, Any]:
    all_raw_messages = read_jsonl(WECHAT_RAW_MESSAGES_FILE)
    raw_messages, recent_sessions = _recent_rows(all_raw_messages)
    candidates = _girls_chat_candidates(raw_messages)
    private_talkers = {
        str(row.get("wechat_talker") or row.get("contact_id") or "").strip()
        for row in raw_messages
        if row.get("chat_type") == "private"
        and str(row.get("wechat_talker") or row.get("contact_id") or "").strip()
    }
    candidate_talkers = {item["talker"] for item in candidates}
    candidate_coverage = {
        "private_session_count": len(private_talkers),
        "candidate_session_count": len(candidate_talkers),
        "excluded_session_count": max(0, len(private_talkers) - len(candidate_talkers)),
        "candidate_session_rate": round(
            len(candidate_talkers) / len(private_talkers) * 100, 1
        )
        if private_talkers
        else 0,
        "all_private_session_count": len(
            {
                str(row.get("wechat_talker") or row.get("contact_id") or "").strip()
                for row in all_raw_messages
                if row.get("chat_type") == "private"
                and str(row.get("wechat_talker") or row.get("contact_id") or "").strip()
            }
        ),
        "recent_session_count": len(recent_sessions),
        "excluded_inactive_session_count": max(
            0,
            len(
                {
                    str(row.get("wechat_talker") or row.get("contact_id") or "").strip()
                    for row in all_raw_messages
                    if row.get("chat_type") == "private"
                    and str(row.get("wechat_talker") or row.get("contact_id") or "").strip()
                }
            )
            - len(private_talkers),
        ),
        "cutoff_timestamp": _distillation_cutoff_timestamp(),
        "cutoff_days": DISTILLATION_WINDOW_DAYS,
        "activity_rule": "only sessions with a message in the last 365 days are distilled",
        "rule": "私聊双方在 12 小时内相邻互道晚安",
        "scope": "仅统计当前已读取并写入 raw messages 的私聊",
    }
    candidate_ids = {item["contact_id"] for item in candidates}
    records = [
        row
        for row in _real_records(recent_only=True)
        if row.get("chat_type") == "private"
        and (
            str(row.get("contact_id") or "") in candidate_ids
            or str(row.get("wechat_talker") or "") in candidate_talkers
        )
    ]
    replies = _replies(records)
    now = datetime.now(timezone.utc).isoformat()
    existing = read_json(SELF_SKILL_META_FILE, {})
    if not candidates or not replies:
        meta = {
            "generated_at": now,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "sample_count": len(replies),
            "record_count": len(records),
            "coverage": candidate_coverage,
            "confidence_note": "\u8fd9\u662f\u57fa\u4e8e\u201c\u665a\u5b89\u4e92\u9053\u201d\u7684\u542f\u53d1\u5f0f\u5019\u9009\uff0c\u4e0d\u662f\u6027\u522b\u8bc6\u522b\u3002",
        }
        existing["girls_chat_style"] = meta
        write_json(SELF_SKILL_META_FILE, existing)
        GIRLS_CHAT_STYLE_FILE.write_text(
            "# Girls chat expression style\n\n"
            "- \u6682\u65e0\u8db3\u591f\u7684\u79c1\u804a\u5019\u9009\u6837\u672c\u3002\n"
            "- \u5019\u9009\u53ea\u662f\u57fa\u4e8e\u665a\u5b89\u4e92\u9053\u7684\u542f\u53d1\u5f0f\u6807\u8bb0\uff0c\u4e0d\u662f\u6027\u522b\u8bc6\u522b\u3002\n",
            encoding="utf-8",
        )
        return {
            "generated": False,
            "candidate_count": len(candidates),
            "sample_count": len(replies),
            "summary": "\u6682\u65e0\u53ef\u7528\u7684\u665a\u5b89\u4e92\u9053\u79c1\u804a\u5019\u9009\u3002",
            "meta": meta,
        }

    style_profiles = _style_profiles(records)
    aggregate = {
        "sample_count": len(replies),
        "record_count": len(records),
        "confidence": "high" if len(replies) >= 50 else "medium" if len(replies) >= 10 else "low",
        "candidate_count": len(candidates),
        "common_rules": [
            "\u53ea\u590d\u7528\u8868\u8fbe\u957f\u5ea6\u3001\u8bed\u6c14\u3001\u8ffd\u95ee\u9891\u7387\u548c\u60c5\u7eea\u5f3a\u5ea6",
            "\u4e0d\u5e26\u5165\u7279\u5b9a\u4eba\u7269\u7684\u79f0\u547c\u3001\u7ecf\u5386\u3001\u4e8b\u5b9e\u6216\u804a\u5929\u8bb0\u5fc6",
            "\u6839\u636e\u5f53\u524d\u5bf9\u8bdd\u52a8\u4f5c\u4fdd\u6301\u81ea\u7136\u63a5\u8bdd\uff0c\u4e0d\u673a\u68b0\u6dfb\u52a0\u5173\u5fc3\u6216\u6682\u6001",
        ],
    }
    previous_meta = read_json(SELF_SKILL_META_FILE, {})
    meta = {
        "generated_at": now,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "sample_count": len(replies),
        "record_count": len(records),
        "aggregate": aggregate,
        "coverage": candidate_coverage,
        "style_profiles": style_profiles,
        "confidence_note": "\u8fd9\u662f\u57fa\u4e8e\u201c\u665a\u5b89\u4e92\u9053\u201d\u7684\u542f\u53d1\u5f0f\u5019\u9009\uff0c\u4e0d\u662f\u6027\u522b\u8bc6\u522b\u3002",
    }
    existing["girls_chat_style"] = meta
    existing["style_profiles"] = existing.get("style_profiles") or _style_profiles(_real_records())
    write_json(SELF_SKILL_META_FILE, existing)
    GIRLS_CHAT_STYLE_FILE.write_text(
        "\n".join(
            [
                "# Girls chat expression style",
                "",
                f"- \u5019\u9009\u6570\u91cf: {len(candidates)}",
                f"- \u805a\u5408\u56de\u590d\u6837\u672c: {len(replies)}",
                f"- \u53ef\u8bfb\u79c1\u804a\u4f1a\u8bdd: {candidate_coverage['private_session_count']}",
                f"- \u7b5b\u51fa\u5019\u9009: {candidate_coverage['candidate_session_count']} "
                f"({candidate_coverage['candidate_session_rate']}%)",
                f"- \u672a\u7b5b\u51fa\u79c1\u804a: {candidate_coverage['excluded_session_count']}",
                "- \u5019\u9009\u89c4\u5219: \u79c1\u804a\u4e2d\u5b58\u5728\u53cc\u65b9\u5728 12 \u5c0f\u65f6\u5185\u76f8\u90bb\u4e92\u9053\u665a\u5b89\u3002",
                "- \u4ec5\u4f7f\u7528\u6211\u7684\u5df2\u5b8c\u6210\u56de\u590d\uff0c\u4e0d\u4f20\u9012\u8054\u7cfb\u4eba\u8eab\u4efd\u6216\u5386\u53f2\u5185\u5bb9\u3002",
                f"- \u53ef\u89e3\u91ca\u63a7\u5236: {aggregate['common_rules'][0]}",
                "",
                "## Distillation boundary",
                "- \u8fd9\u4e0d\u662f\u6027\u522b\u8bc6\u522b\uff0c\u53ea\u662f\u7528\u665a\u5b89\u4e92\u9053\u4f5c\u4e3a\u5019\u9009\u7b5b\u9009\u7ebf\u7d22\u3002",
                "- \u8fd9\u4e2a\u98ce\u683c\u53ea\u8fc1\u79fb\u8868\u8fbe\u65b9\u5f0f\uff0c\u4e0d\u8fc1\u79fb\u5177\u4f53\u4eba\u7269\u7684\u8eab\u4efd\u3001\u8bb0\u5fc6\u6216\u4e8b\u5b9e\u3002",
                "",
                "## Style distribution",
                *[
                    f"- {profile['name']}: {profile['sample_count']} \u6761"
                    f" ({round(profile['sample_count'] / len(replies) * 100, 1)}%)"
                    for profile in style_profiles.values()
                ],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "generated": True,
        "candidate_count": len(candidates),
        "sample_count": len(replies),
        "coverage": candidate_coverage,
        "summary": f"\u5df2\u4ece {len(candidates)} \u4e2a\u79c1\u804a\u5019\u9009\u4e2d\u805a\u5408 {len(replies)} \u6761\u56de\u590d\u6837\u672c\u3002",
        "meta": meta,
    }


def get_girls_chat_style() -> dict[str, Any]:
    meta = read_json(SELF_SKILL_META_FILE, {}).get("girls_chat_style") or {}
    return {
        "ready": bool(meta.get("sample_count")),
        "meta": meta,
        "skill_file": str(GIRLS_CHAT_STYLE_FILE),
    }


def _real_records(*, recent_only: bool = False) -> list[dict[str, Any]]:
    records = [
        row
        for row in read_jsonl(MESSAGES_FILE)
        if row.get("source") != "demo"
        and row.get("my_reply")
        and (
            row.get("chat_type") != "group"
            or (
                isinstance(row.get("participant_count"), int)
                and row["participant_count"] <= 10
            )
        )
    ]
    if recent_only:
        records, _ = _recent_rows(records)
    return records


def _replies(records: list[dict[str, Any]]) -> list[str]:
    return [
        reply.strip()
        for record in records
        for reply in record.get("my_reply", [])
        if reply and reply.strip()
    ]


def _top_particles(text: str, limit: int = 8) -> list[tuple[str, int]]:
    particles = re.findall(r"[哈呵啊呀哦呢嘛吧喽哎嗯诶]+", text)
    return Counter(particles).most_common(limit)


def _top_endings(replies: list[str], limit: int = 8) -> list[tuple[str, int]]:
    return Counter(
        reply[-2:] for reply in replies if len(reply) >= 2
    ).most_common(limit)


def _format_counts(items: list[tuple[str, int]]) -> str:
    return "、".join(f"{value}({count})" for value, count in items) or "暂无"


def _contact_skill_file(contact_id: str):
    digest = hashlib.sha256(contact_id.encode("utf-8")).hexdigest()[:16]
    return CONTACT_SKILL_DIR / f"{digest}.md"


def _contact_profile(
    contact_id: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    replies = _replies(records)
    analysis = analyze_chat_records(records)
    lengths = sorted(len(reply) for reply in replies)
    median_length = lengths[len(lengths) // 2] if lengths else 0
    average_length = round(sum(lengths) / len(lengths), 1) if lengths else 0
    particles = _top_particles("\n".join(replies), 6)
    endings = _top_endings(replies, 6)
    scenes = Counter(record.get("scene", "daily") for record in records)
    if median_length <= 4:
        length_style = "偏短，优先一两句接话"
    elif median_length <= 10:
        length_style = "短句为主，必要时补充一句"
    else:
        length_style = "可以完整表达，但优先自然分段"
    question_style = (
        "较常用追问"
        if analysis["question_rate"] >= 20
        else "偶尔追问"
        if analysis["question_rate"] >= 8
        else "较少主动追问"
    )
    emotion_style = (
        "常用笑声或表情"
        if analysis["laughter_emoji_rate"] >= 15
        else "适度使用笑声或表情"
        if analysis["laughter_emoji_rate"] >= 5
        else "少用笑声或表情"
    )
    return {
        "contact_id": contact_id,
        "display_name": next(
            (
                record.get("display_name", "")
                for record in records
                if record.get("display_name")
            ),
            "",
        ),
        "sample_count": len(replies),
        "record_count": len(records),
        "confidence": (
            "high"
            if len(replies) >= 50
            else "medium"
            if len(replies) >= 10
            else "low"
        ),
        "average_reply_length": average_length,
        "median_reply_length": median_length,
        "question_rate": analysis["question_rate"],
        "laughter_emoji_rate": analysis["laughter_emoji_rate"],
        "median_response_seconds": analysis["median_response_seconds"],
        "active_hours": analysis["active_hours"][:5],
        "common_particles": [value for value, _ in particles],
        "common_endings": [value for value, _ in endings],
        "scene_counts": dict(scenes),
        "style_rules": [length_style, question_style, emotion_style],
    }


def _write_contact_profile(profile: dict[str, Any]) -> None:
    CONTACT_SKILL_DIR.mkdir(parents=True, exist_ok=True)
    path = _contact_skill_file(profile["contact_id"])
    path.write_text(
        "\n".join(
            [
                "# Contact expression profile",
                f"- samples: {profile['sample_count']}",
                f"- confidence: {profile['confidence']}",
                f"- average length: {profile['average_reply_length']}",
                f"- common particles: {', '.join(profile['common_particles'])}",
                f"- common endings: {', '.join(profile['common_endings'])}",
                "",
                "## Style rules",
                *[f"- {rule}" for rule in profile["style_rules"]],
                "- This profile contains statistics only; it does not transfer identity or facts.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _style_only_profile(profile: dict[str, Any], preset_id: str) -> dict[str, Any]:
    style_names = {
        "style:concise": "简洁短句",
        "style:questioning": "主动追问",
        "style:playful": "轻松幽默",
        "style:expressive": "完整表达",
        "style:balanced": "自然均衡",
    }
    return {
        "id": preset_id,
        "name": style_names.get(preset_id, "表达风格"),
        "sample_count": profile.get("sample_count", 0),
        "confidence": profile.get("confidence", "low"),
        "average_reply_length": profile.get("average_reply_length", 0),
        "median_reply_length": profile.get("median_reply_length", 0),
        "question_rate": profile.get("question_rate", 0),
        "laughter_emoji_rate": profile.get("laughter_emoji_rate", 0),
        "median_response_seconds": profile.get("median_response_seconds"),
        "active_hours": profile.get("active_hours", [])[:5],
        "common_particles": profile.get("common_particles", [])[:8],
        "common_endings": profile.get("common_endings", [])[:8],
        "style_rules": profile.get("style_rules", [])[:6],
    }


def distill_self_skill() -> dict[str, Any]:
    all_records = _real_records()
    records, recent_sessions = _recent_rows(all_records)
    replies = _replies(records)
    if not replies:
        return {
            "generated": False,
            "sample_count": 0,
            "summary": "没有真实本人回复样本，暂时无法生成个人 Skill。",
        }

    analysis = analyze_chat_records(records)
    all_text = "\n".join(replies)
    average_length = round(sum(len(reply) for reply in replies) / len(replies), 1)
    punctuation = Counter(char for char in all_text if char in "，。！？!?~")
    particles = _top_particles(all_text)
    endings = _top_endings(replies)
    emoji_count = sum(
        bool(re.search(r"[\U0001F300-\U0001FAFF]|哈哈|呵呵|hhh|233", reply))
        for reply in replies
    )

    contact_profiles: dict[str, dict[str, Any]] = {}
    contact_records: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        contact_id = str(record.get("contact_id", "")).strip()
        if contact_id:
            contact_records.setdefault(contact_id, []).append(record)
    for contact_id, rows in sorted(contact_records.items()):
        profile = _contact_profile(contact_id, rows)
        contact_profiles[contact_id] = profile
        _write_contact_profile(profile)

    relationship_meta: dict[str, Any] = {}
    relationship_sections: list[str] = []
    for relationship, label in RELATIONSHIP_LABELS.items():
        relation_replies = _replies(
            [row for row in records if row.get("relationship") == relationship]
        )
        if not relation_replies:
            continue
        relation_endings = _top_endings(relation_replies, 5)
        relationship_meta[relationship] = {
            "sample_count": len(relation_replies),
            "average_length": round(
                sum(len(reply) for reply in relation_replies)
                / len(relation_replies),
                1,
            ),
            "common_endings": [value for value, _ in relation_endings],
            **analysis.get("relationships", {}).get(relationship, {}),
        }
        relationship_sections.append(
            f"### {label}\n"
            f"- samples: {len(relation_replies)}\n"
            f"- common endings: {_format_counts(relation_endings)}"
        )

    self_memory = "\n".join(
        [
            "# Self Memory",
            f"- extracted from {len(replies)} real replies",
            "- Do not infer identity, history, location, promises, or facts without evidence.",
            "",
            "## Relationship summaries",
            *relationship_sections,
        ]
    )
    persona = "\n".join(
        [
            "# Persona",
            "- Reuse the user's observed length, tone, and relationship distance.",
            "- Do not invent facts, promises, locations, schedules, money, health, or decisions.",
            f"- Average reply length: {average_length}",
            f"- Emoji or laughter sample rate: {round(emoji_count / len(replies) * 100)}%",
            f"- Question rate: {analysis['question_rate']}%",
            f"- Common particles: {_format_counts(particles)}",
            f"- Common endings: {_format_counts(endings)}",
            f"- Common punctuation: {_format_counts(punctuation.most_common(6))}",
        ]
    )
    SELF_MEMORY_FILE.write_text(self_memory + "\n", encoding="utf-8")
    PERSONA_FILE.write_text(persona + "\n", encoding="utf-8")
    now = datetime.now(timezone.utc).isoformat()
    previous_meta = read_json(SELF_SKILL_META_FILE, {})
    meta = {
        "name": "My WeChat expression",
        "slug": "my-wechat-self",
        "version": "v1",
        "created_at": read_json(SELF_SKILL_META_FILE, {}).get("created_at", now),
        "updated_at": now,
        "sample_count": len(replies),
        "distillation_window": {
            "days": DISTILLATION_WINDOW_DAYS,
            "cutoff_timestamp": _distillation_cutoff_timestamp(),
            "activity_rule": "only sessions with a message in the last 365 days are distilled",
            "all_session_count": len(
                {
                    str(row.get("contact_id") or "").strip()
                    for row in all_records
                    if str(row.get("contact_id") or "").strip()
                }
            ),
            "recent_session_count": len(recent_sessions),
            "excluded_inactive_session_count": max(
                0,
                len(
                    {
                        str(row.get("contact_id") or "").strip()
                        for row in all_records
                        if str(row.get("contact_id") or "").strip()
                    }
                )
                - len(recent_sessions),
            ),
        },
        "relationship_profiles": relationship_meta,
        "contact_profiles": contact_profiles,
        "style_profiles": _style_profiles(records),
        "analysis": analysis,
        "sources": ["data/messages.jsonl"],
    }
    if previous_meta.get("girls_chat_style"):
        meta["girls_chat_style"] = previous_meta["girls_chat_style"]
    write_json(SELF_SKILL_META_FILE, meta)
    from .services import distill_profile

    distill_profile()
    # 全局样本变化后同步刷新聚合风格文档，避免 meta.json 与 Skill 摘要出现旧统计。
    if meta.get("girls_chat_style"):
        distill_girls_chat_style()
    return {
        "generated": True,
        "sample_count": len(replies),
        "summary": f"已从 {len(replies)} 条真实回复生成 Self Memory 和 Persona。",
        "meta": meta,
    }


def get_self_skill() -> dict[str, Any]:
    meta = read_json(SELF_SKILL_META_FILE, {})
    self_memory = (
        SELF_MEMORY_FILE.read_text(encoding="utf-8")
        if SELF_MEMORY_FILE.exists()
        else ""
    )
    persona = (
        PERSONA_FILE.read_text(encoding="utf-8")
        if PERSONA_FILE.exists()
        else ""
    )
    return {
        "ready": bool(meta and persona),
        "meta": meta,
        "self_memory": self_memory,
        "persona": persona,
    }


def get_style_presets() -> list[dict[str, Any]]:
    payload = get_self_skill()
    if not payload["ready"]:
        return []
    meta = payload["meta"]
    profiles = meta.get("style_profiles") or _style_profiles(_real_records())
    presets = [
        {
            **_style_only_profile(profile, profile["id"]),
            "description": profile.get("description", ""),
        }
        for profile in profiles.values()
    ]
    girls = meta.get("girls_chat_style") or {}
    if girls.get("sample_count"):
        girls_profiles = girls.get("style_profiles") or {}
        girls_profile = girls_profiles.get("balanced") or next(
            iter(girls_profiles.values()), {}
        )
        presets.append(
            {
                **_style_only_profile(girls_profile, "style:girls-chat"),
                "id": "style:girls-chat",
                "sample_count": girls.get("sample_count", 0),
                "profile_sample_count": girls_profile.get("sample_count", 0),
                "name": "\u5973\u751f\u804a\u5929\u98ce\u683c",
                "description": (
                    f"\u4ec5\u4f7f\u7528 {girls.get('candidate_count', 0)} "
                    f"\u4e2a\u665a\u5b89\u4e92\u9053\u79c1\u804a\u7684\u805a\u5408\u8868\u8fbe\u8d8b\u52bf"
                ),
                "candidate_count": girls.get("candidate_count", 0),
                "confidence_note": girls.get("confidence_note", ""),
            }
        )
    return presets
    """
    presets = [
        _style_only_profile(profile, f"contact:{contact_id}")
        for contact_id, profile in (meta.get("contact_profiles") or {}).items()
    ]
    if meta.get("sample_count"):
        presets.insert(
            0,
            {
                "id": "global",
                "name": "全局个人风格",
                "sample_count": meta.get("sample_count", 0),
                "confidence": "medium",
                "style_rules": [],
            },
        )
    return presets
    """


def get_style_prompt(contact_id: str = "", style_preset_id: str = "") -> str:
    payload = get_self_skill()
    if payload["ready"]:
        selected_id = (
            style_preset_id
            if style_preset_id.startswith("style:")
            else "style:balanced"
        )
        style_key = selected_id.removeprefix("style:")
        if selected_id == "style:girls-chat":
            girls = payload["meta"].get("girls_chat_style") or {}
            profiles = girls.get("style_profiles") or {}
            profile = profiles.get("balanced") or next(iter(profiles.values()), {})
            style_source = {
                "candidate_count": girls.get("candidate_count", 0),
                "sample_count": girls.get("sample_count", 0),
                "profile_sample_count": profile.get("sample_count", 0),
                "confidence_note": girls.get("confidence_note", ""),
                "identity_boundary": (
                    "只迁移表达层特征，不迁移特定人物的身份、称呼、经历、事实或聊天记忆"
                ),
                "common_rules": (girls.get("aggregate") or {}).get(
                    "common_rules", []
                ),
            }
        else:
            profiles = payload["meta"].get("style_profiles") or _style_profiles(_real_records())
            profile = profiles.get(style_key) or profiles.get("balanced") or {}
            style_source = {}
        return json.dumps(
            {
                "meta": {
                    "sample_count": payload["meta"].get("sample_count", 0),
                    "style_preset_id": selected_id,
                    "style_profile": {
                        **_style_only_profile(profile, selected_id),
                        "description": profile.get("description", ""),
                        **style_source,
                    },
                },
                "persona_rules": payload["persona"],
            },
            ensure_ascii=False,
        )
    """
    if not payload["ready"]:
        return "个人 Self Skill 尚未生成"
    selected_id = style_preset_id or (f"contact:{contact_id}" if contact_id else "global")
    source_id = selected_id.removeprefix("contact:")
    profile = (
        {"sample_count": payload["meta"].get("sample_count", 0)}
        if selected_id == "global"
        else payload["meta"].get("contact_profiles", {}).get(source_id) or {}
    )
    return json.dumps(
        {
            "meta": {
                "sample_count": payload["meta"].get("sample_count", 0),
                "style_preset_id": selected_id,
                "style_profile": _style_only_profile(profile, selected_id),
            },
            "persona_rules": payload["persona"],
        },
        ensure_ascii=False,
    )
    """


def get_self_skill_prompt(contact_id: str = "") -> str:
    payload = get_self_skill()
    if not payload["ready"]:
        return "个人 Self Skill 尚未生成"
    contact_profile = payload["meta"].get("contact_profiles", {}).get(contact_id)
    return json.dumps(
        {
            "meta": {
                "sample_count": payload["meta"].get("sample_count", 0),
                "relationship_profiles": payload["meta"].get(
                    "relationship_profiles", {}
                ),
                "contact_profile": contact_profile,
            },
            "self_memory": payload["self_memory"],
            "persona": payload["persona"],
        },
        ensure_ascii=False,
    )


STYLE_DEFINITIONS = (
    ("concise", "\u7b80\u6d01\u77ed\u53e5", "\u77ed\u53e5\u4e3a\u4e3b\uff0c\u5c11\u91cf\u8ffd\u95ee\uff0c\u9002\u5408\u5feb\u901f\u63a5\u8bdd"),
    ("questioning", "\u4e3b\u52a8\u8ffd\u95ee", "\u4f1a\u7528\u4e00\u4e2a\u81ea\u7136\u95ee\u9898\u628a\u5bf9\u8bdd\u5f80\u524d\u63a8\u8fdb"),
    ("playful", "\u8f7b\u677e\u5e7d\u9ed8", "\u9002\u5ea6\u4f7f\u7528\u7b11\u58f0\u3001\u8bed\u6c14\u8bcd\u6216\u8868\u60c5"),
    ("expressive", "\u5b8c\u6574\u8868\u8fbe", "\u4f1a\u8865\u5145\u5fc5\u8981\u4fe1\u606f\uff0c\u4f46\u4fdd\u6301\u81ea\u7136\u5206\u6bb5"),
    ("balanced", "\u81ea\u7136\u5747\u8861", "\u5728\u957f\u5ea6\u3001\u8ffd\u95ee\u548c\u60c5\u7eea\u8868\u8fbe\u4e4b\u95f4\u4fdd\u6301\u5747\u8861"),
)


def _reply_is_question(reply: str) -> bool:
    return any(
        marker in reply
        for marker in ("?", "\uff1f", "\u5417", "\u5462", "\u600e\u4e48", "\u4e3a\u4ec0\u4e48")
    )


def _reply_is_playful(reply: str) -> bool:
    return bool(re.search(r"[\U0001F300-\U0001FAFF]|哈哈|呵呵|嘿嘿|hhh|233", reply, re.I))


def _style_bucket(reply: str, median_length: float) -> str:
    if _reply_is_playful(reply):
        return "playful"
    if _reply_is_question(reply):
        return "questioning"
    if len(reply) <= max(4, median_length):
        return "concise"
    if len(reply) >= max(10, median_length * 2):
        return "expressive"
    return "balanced"


def _style_profiles(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    replies = _replies(records)
    if not replies:
        return {}
    lengths = sorted(len(reply) for reply in replies)
    median_length = lengths[len(lengths) // 2]
    buckets: dict[str, list[str]] = {key: [] for key, _, _ in STYLE_DEFINITIONS}
    for reply in replies:
        buckets[_style_bucket(reply, median_length)].append(reply)

    profiles: dict[str, dict[str, Any]] = {}
    for key, name, description in STYLE_DEFINITIONS:
        bucket = buckets[key]
        if not bucket:
            continue
        analysis = analyze_chat_records(
            [{"my_reply": [reply], "source": "wechat"} for reply in bucket]
        )
        profiles[key] = {
            "id": f"style:{key}",
            "name": name,
            "description": description,
            "sample_count": len(bucket),
            "confidence": (
                "high" if len(bucket) >= 50 else "medium" if len(bucket) >= 10 else "low"
            ),
            "average_reply_length": analysis["average_reply_length"],
            "median_reply_length": analysis["median_reply_length"],
            "question_rate": analysis["question_rate"],
            "laughter_emoji_rate": analysis["laughter_emoji_rate"],
            "common_particles": [
                value for value, _ in _top_particles("\n".join(bucket), 6)
            ],
            "common_endings": [value for value, _ in _top_endings(bucket, 6)],
            "style_rules": [
                description,
                "\u4e0d\u8fc1\u79fb\u6765\u6e90\u804a\u5929\u4e2d\u7684\u8eab\u4efd\u3001\u4e8b\u5b9e\u3001\u79f0\u547c\u6216\u7ecf\u5386",
            ],
        }
    return profiles
