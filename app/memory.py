from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.message_text import display_message_text

FACT_TYPES = {"preference", "plan", "identity", "event", "habit"}
LOW_CONFIDENCE = 0.5
MAX_FACT_CHARS = 80
MAX_SUMMARY_CHARS = 240
_SECRET_RE = re.compile(r"api[_-]?key|password|secret|token", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_path():
    import app.storage as storage

    return storage.CONFIG_DB_FILE


def _clip(text: str, limit: int) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE IF NOT EXISTS memory_facts ("
        "id INTEGER PRIMARY KEY,"
        "contact_id TEXT NOT NULL,"
        "fact_type TEXT NOT NULL,"
        "content TEXT NOT NULL,"
        "key_hash TEXT NOT NULL UNIQUE,"
        "confidence REAL NOT NULL DEFAULT 0.6,"
        "first_seen_at TEXT NOT NULL,"
        "updated_at TEXT NOT NULL,"
        "source_message_id TEXT NOT NULL DEFAULT ''"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_facts_contact "
        "ON memory_facts(contact_id, updated_at)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS memory_summaries ("
        "contact_id TEXT PRIMARY KEY,"
        "content TEXT NOT NULL,"
        "updated_at TEXT NOT NULL"
        ")"
    )
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS memory_facts_fts "
            "USING fts5(contact_id UNINDEXED, key_hash UNINDEXED, content)"
        )
    except sqlite3.OperationalError:
        pass
    return connection


def fact_key_hash(contact_id: str, fact_type: str, key: str) -> str:
    normalized = re.sub(r"\s+", "", f"{contact_id}|{fact_type}|{key}".lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _fact_key(fact: dict[str, Any]) -> str:
    explicit = str(fact.get("key") or "").strip()
    if explicit:
        return explicit
    content = str(fact.get("content") or "").strip()
    matched = re.search(r"(?:不吃|爱吃|喜欢吃|过敏)(.+)$", content)
    if matched:
        return matched.group(1).strip(" 。！!?")
    return content


def upsert_facts(contact_id: str, facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stored: list[dict[str, Any]] = []
    connection = _connect()
    try:
        for fact in facts:
            content = _clip(str(fact.get("content") or ""), MAX_FACT_CHARS)
            fact_type = str(fact.get("fact_type") or "event")
            if not content or fact_type not in FACT_TYPES or _SECRET_RE.search(content):
                continue
            key_hash = fact_key_hash(contact_id, fact_type, _fact_key({**fact, "content": content}))
            confidence = float(fact.get("confidence") or 0.6)
            source_id = str(fact.get("source_message_id") or "")
            now = _now()
            existing = connection.execute(
                "SELECT first_seen_at FROM memory_facts WHERE key_hash = ?",
                (key_hash,),
            ).fetchone()
            connection.execute(
                "INSERT INTO memory_facts("
                "contact_id, fact_type, content, key_hash, confidence, "
                "first_seen_at, updated_at, source_message_id"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(key_hash) DO UPDATE SET "
                "content=excluded.content, "
                "confidence=excluded.confidence, "
                "updated_at=excluded.updated_at, "
                "source_message_id=excluded.source_message_id",
                (
                    contact_id,
                    fact_type,
                    content,
                    key_hash,
                    confidence,
                    existing["first_seen_at"] if existing else now,
                    now,
                    source_id,
                ),
            )
            try:
                connection.execute(
                    "DELETE FROM memory_facts_fts WHERE key_hash = ?", (key_hash,)
                )
                connection.execute(
                    "INSERT INTO memory_facts_fts(contact_id, key_hash, content) "
                    "VALUES (?, ?, ?)",
                    (contact_id, key_hash, content),
                )
            except sqlite3.OperationalError:
                pass
            stored.append(
                {
                    "contact_id": contact_id,
                    "fact_type": fact_type,
                    "content": content,
                    "key_hash": key_hash,
                    "confidence": confidence,
                    "source_message_id": source_id,
                }
            )
        connection.commit()
    finally:
        connection.close()
    if stored:
        try:
            refresh_summary(contact_id)
        except Exception:
            pass
    return stored


def list_facts(
    contact_id: str,
    query: str = "",
    limit: int = 8,
) -> list[dict[str, Any]]:
    try:
        connection = _connect()
    except Exception:
        return []
    try:
        token = str(query or "").strip()
        if token:
            fts_query = '"' + token.replace('"', " ").strip() + '"'
            try:
                rows = connection.execute(
                    "SELECT f.contact_id, f.fact_type, f.content, f.key_hash, "
                    "f.confidence, f.updated_at "
                    "FROM memory_facts f "
                    "JOIN memory_facts_fts fts ON f.key_hash = fts.key_hash "
                    "WHERE f.contact_id = ? AND memory_facts_fts MATCH ? "
                    "ORDER BY f.updated_at DESC LIMIT ?",
                    (contact_id, fts_query, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = connection.execute(
                    "SELECT contact_id, fact_type, content, key_hash, "
                    "confidence, updated_at FROM memory_facts "
                    "WHERE contact_id = ? AND content LIKE ? "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (contact_id, f"%{token}%", limit),
                ).fetchall()
        else:
            rows = connection.execute(
                "SELECT contact_id, fact_type, content, key_hash, "
                "confidence, updated_at FROM memory_facts "
                "WHERE contact_id = ? ORDER BY updated_at DESC LIMIT ?",
                (contact_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []
    finally:
        connection.close()


def get_summary(contact_id: str) -> str:
    if not contact_id:
        return ""
    try:
        connection = _connect()
    except Exception:
        return ""
    try:
        row = connection.execute(
            "SELECT content FROM memory_summaries WHERE contact_id = ?",
            (contact_id,),
        ).fetchone()
        return str(row["content"] if row else "")
    except Exception:
        return ""
    finally:
        connection.close()


def refresh_summary(contact_id: str) -> str:
    facts = list_facts(contact_id, limit=6)
    content = _clip("；".join(item["content"] for item in facts if item.get("content")), MAX_SUMMARY_CHARS)
    connection = _connect()
    try:
        connection.execute(
            "INSERT INTO memory_summaries(contact_id, content, updated_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(contact_id) DO UPDATE SET "
            "content=excluded.content, updated_at=excluded.updated_at",
            (contact_id, content, _now()),
        )
        connection.commit()
    finally:
        connection.close()
    return content


def extract_facts_from_incoming(
    messages: list[dict[str, Any]],
    contact_id: str,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for message in messages:
        if message.get("is_from_me"):
            continue
        text = display_message_text(message)
        if not text or text.startswith("[") or _SECRET_RE.search(text):
            continue
        source_id = str(
            (message.get("id") or {}).get("local_id")
            or message.get("source_message_id")
            or ""
        )
        clipped = _clip(text, MAX_FACT_CHARS)
        if re.search(r"不吃|过敏|不喜欢吃", text):
            facts.append(
                {
                    "fact_type": "preference",
                    "content": clipped,
                    "key": _fact_key({"content": clipped, "fact_type": "preference"}),
                    "confidence": 0.7,
                    "source_message_id": source_id,
                }
            )
        if re.search(r"养了|我是|叫", text) and not re.search(r"不吃", text):
            facts.append(
                {
                    "fact_type": "identity",
                    "content": clipped,
                    "confidence": 0.65,
                    "source_message_id": source_id,
                }
            )
        if re.search(r"出差|下周|计划|要去", text):
            facts.append(
                {
                    "fact_type": "plan",
                    "content": clipped,
                    "confidence": 0.65,
                    "source_message_id": source_id,
                }
            )
    return facts


async def extract_facts_via_model(
    messages: list[dict[str, Any]],
    contact_id: str,
    settings: Any,
) -> list[dict[str, Any]]:
    if not contact_id or getattr(settings, "provider", "demo") == "demo":
        return []
    incoming = []
    for message in messages:
        if message.get("is_from_me"):
            continue
        text = display_message_text(message)
        if text and not text.startswith("[") and not _SECRET_RE.search(text):
            incoming.append(_clip(text, MAX_FACT_CHARS))
    if not incoming:
        return []
    from app.agent.llm import chat_completion, extract_json

    prompt = (
        "只从对方消息抽取可跨会话复用的短事实。"
        "不要保存整段聊天、密钥、密码或配置。"
        "fact_type 只能是 preference/plan/identity/event/habit。"
        "content 不超过 80 字。没有事实则 facts 为空数组。只输出 JSON。\n"
        f"messages={incoming}\n"
        '{"facts":[{"fact_type":"preference","content":"...","key":"...","confidence":0.7}]}'
    )
    payload = extract_json(
        await chat_completion(settings, prompt, temperature=0.0, force_json=True)
    )
    facts: list[dict[str, Any]] = []
    for item in payload.get("facts") or []:
        if not isinstance(item, dict):
            continue
        fact_type = str(item.get("fact_type") or "")
        content = _clip(str(item.get("content") or ""), MAX_FACT_CHARS)
        if fact_type not in FACT_TYPES or not content:
            continue
        facts.append(
            {
                "fact_type": fact_type,
                "content": content,
                "key": str(item.get("key") or content),
                "confidence": float(item.get("confidence") or 0.6),
            }
        )
    return facts


def sync_incoming_facts(
    contact_id: str,
    messages: list[dict[str, Any]],
    *,
    chat_type: str = "private",
) -> int:
    try:
        if not contact_id:
            return 0
        _ = chat_type
        facts = extract_facts_from_incoming(messages, contact_id)
        return len(upsert_facts(contact_id, facts))
    except Exception:
        return 0


def relevant_facts(
    contact_id: str,
    conversation: str,
    limit: int = 6,
) -> list[dict[str, Any]]:
    try:
        tokens = [
            token
            for token in re.findall(r"[\u4e00-\u9fff]+|\w+", conversation)
            if len(token) >= 2
        ]
        matched: list[dict[str, Any]] = []
        seen: set[str] = set()
        for token in tokens[-8:]:
            for fact in list_facts(contact_id, token, limit=limit):
                if fact["key_hash"] in seen:
                    continue
                seen.add(fact["key_hash"])
                matched.append(fact)
        if not matched:
            matched = list_facts(contact_id, limit=limit)
        labeled = []
        for fact in matched[:limit]:
            content = str(fact.get("content") or "")
            if float(fact.get("confidence") or 0) < LOW_CONFIDENCE:
                content = f"可能：{content}"
            labeled.append({**fact, "content": content})
        return labeled
    except Exception:
        return []
