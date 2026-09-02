import re
from collections import Counter, defaultdict
from datetime import datetime
from statistics import median
from typing import Any

TEXT_KINDS = {"text"}
IMAGE_KINDS = {"image"}
EMOJI_KINDS = {"emoji", "sticker"}
QUESTION_MARKERS = ("?", "？", "吗", "嘛", "呢", "怎么", "为何", "为什么")
LAUGHTER_PATTERN = re.compile(
    r"[\U0001F300-\U0001FAFF]|哈哈|嘿嘿|呵呵|hhh|233",
    re.IGNORECASE,
)


def _percent(numerator: int | float, denominator: int | float) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def _valid_times(records: list[dict[str, Any]], key: str) -> list[int]:
    return [
        int(value)
        for record in records
        for value in record.get(key, [])
        if value
    ]


def _message_kinds(records: list[dict[str, Any]]) -> Counter:
    return Counter(
        str(kind or "unknown")
        for record in records
        for key in ("incoming_kinds", "reply_kinds")
        for kind in record.get(key, [])
    )


def _reply_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    replies = [
        str(reply).strip()
        for record in records
        for reply in record.get("my_reply", [])
        if str(reply).strip()
    ]
    lengths = [len(reply) for reply in replies]
    response_seconds = [
        int(record["response_seconds"])
        for record in records
        if record.get("response_seconds") is not None
        and 0 <= int(record["response_seconds"]) <= 7 * 24 * 3600
    ]
    reply_times = _valid_times(records, "reply_times")
    hours = Counter(
        datetime.fromtimestamp(timestamp).hour
        for timestamp in reply_times
    )
    late_night = sum(
        1
        for timestamp in reply_times
        if datetime.fromtimestamp(timestamp).hour >= 22
        or datetime.fromtimestamp(timestamp).hour <= 3
    )
    question_count = sum(
        1 for reply in replies if any(marker in reply for marker in QUESTION_MARKERS)
    )
    laughter_count = sum(bool(LAUGHTER_PATTERN.search(reply)) for reply in replies)

    return {
        "reply_count": len(replies),
        "average_reply_length": round(sum(lengths) / len(lengths), 1) if lengths else 0,
        "median_reply_length": round(float(median(lengths)), 1) if lengths else 0,
        "median_response_seconds": (
            round(float(median(response_seconds)), 1) if response_seconds else None
        ),
        "under_1min_rate": _percent(
            sum(seconds <= 60 for seconds in response_seconds),
            len(response_seconds),
        ),
        "under_5min_rate": _percent(
            sum(seconds <= 300 for seconds in response_seconds),
            len(response_seconds),
        ),
        "question_rate": _percent(question_count, len(replies)),
        "laughter_emoji_rate": _percent(laughter_count, len(replies)),
        "late_night_rate": _percent(late_night, len(reply_times)),
        "active_hours": [
            {"hour": hour, "count": count}
            for hour, count in hours.most_common(5)
        ],
    }


def analyze_chat_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    real_records = [
        record
        for record in records
        if record.get("source") != "demo" and record.get("my_reply")
    ]
    metrics = _reply_metrics(real_records)
    kinds = _message_kinds(real_records)
    kind_total = sum(kinds.values())
    reply_times = _valid_times(real_records, "reply_times")
    monthly = defaultdict(lambda: {"records": 0, "replies": 0})
    for record in real_records:
        times = [value for value in record.get("reply_times", []) if value]
        if times:
            month = datetime.fromtimestamp(int(times[0])).strftime("%Y-%m")
            monthly[month]["records"] += 1
            monthly[month]["replies"] += len(record.get("my_reply", []))

    relationships: dict[str, Any] = {}
    for relationship in ("partner", "friend", "family"):
        subset = [
            record
            for record in real_records
            if record.get("relationship") == relationship
        ]
        if subset:
            relationships[relationship] = _reply_metrics(subset)

    message_types = {
        "total": kind_total,
        "text_rate": _percent(sum(kinds[kind] for kind in TEXT_KINDS), kind_total),
        "image_rate": _percent(sum(kinds[kind] for kind in IMAGE_KINDS), kind_total),
        "emoji_rate": _percent(sum(kinds[kind] for kind in EMOJI_KINDS), kind_total),
        "counts": dict(kinds.most_common()),
    }
    return {
        "record_count": len(real_records),
        "session_count": len(
            {
                record.get("wechat_talker") or record.get("contact_id")
                for record in real_records
            }
        ),
        **metrics,
        "message_types": message_types,
        "relationships": relationships,
        "monthly_trend": [
            {"month": month, **monthly[month]}
            for month in sorted(monthly)
        ],
        "time_coverage": {
            "first_reply_at": min(reply_times) if reply_times else None,
            "last_reply_at": max(reply_times) if reply_times else None,
        },
    }
