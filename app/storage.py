import json
import sqlite3
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CONFIG_DIR = ROOT / "config"
SAFETY_FILE = CONFIG_DIR / "safety.yaml"
SKILLS_DIR = ROOT / "skills"
FRONTEND_DIST = ROOT / "frontend" / "dist"

MESSAGES_FILE = DATA_DIR / "messages.jsonl"
WECHAT_RAW_MESSAGES_FILE = DATA_DIR / "wechat-raw-messages.jsonl"
FEEDBACK_FILE = DATA_DIR / "feedback.jsonl"
PROFILE_FILE = DATA_DIR / "profile.json"
CONFIG_DB_FILE = DATA_DIR / "config.sqlite3"
AUTOMATION_STATE_FILE = DATA_DIR / "automation-state.json"
AUTOMATION_EVENTS_FILE = DATA_DIR / "automation-events.jsonl"
WECHAT_COVERAGE_FILE = DATA_DIR / "wechat-read-coverage.json"
SELF_SKILL_DIR = DATA_DIR / "self-skill"
SELF_MEMORY_FILE = SELF_SKILL_DIR / "self.md"
PERSONA_FILE = SELF_SKILL_DIR / "persona.md"
SELF_SKILL_META_FILE = SELF_SKILL_DIR / "meta.json"
GIRLS_CHAT_STYLE_FILE = SELF_SKILL_DIR / "girls-chat-style.md"
CONTACT_SKILL_DIR = SELF_SKILL_DIR / "contacts"

DEFAULT_RUNTIME_SETTINGS = {
    "provider": "demo",
    "base_url": "http://127.0.0.1:11434",
    "model": "qwen3:8b",
    "api_key": "",
}

DEFAULT_AUTO_REPLY_SETTINGS = {
    "memory_sync_enabled": True,
    "enabled": False,
    "dry_run": True,
    "real_send_acknowledged": False,
    "poll_interval_seconds": 3,
    "takeover_delay_seconds": 300,
    "allowed_contact_ids": [],
    "auto_send_levels": ["L0"],
    "contact_settings": {},
}


DEMO_CONTACTS = [
    {
        "contact_id": "demo-partner",
        "display_name": "示例·情侣",
        "relationship": "partner",
        "preferred_address": "宝",
        "message_length": "short",
        "emoji_level": "low",
        "humor_level": "medium",
        "boundaries": ["不代替本人承诺见面", "不处理转账和借款"],
        "is_demo": True,
    },
    {
        "contact_id": "demo-friend",
        "display_name": "示例·好友",
        "relationship": "friend",
        "preferred_address": "",
        "message_length": "very_short",
        "emoji_level": "medium",
        "humor_level": "high",
        "boundaries": ["认真求助时不继续玩笑"],
        "is_demo": True,
    },
    {
        "contact_id": "demo-family",
        "display_name": "示例·家人",
        "relationship": "family",
        "preferred_address": "妈",
        "message_length": "medium",
        "emoji_level": "none",
        "humor_level": "low",
        "boundaries": ["不编造位置、吃饭和健康情况"],
        "is_demo": True,
    },
]


DEMO_MESSAGES = [
    {
        "contact_id": "demo-partner",
        "relationship": "partner",
        "scene": "comfort",
        "incoming": ["今天真的特别累"],
        "my_reply": ["怎么啦宝，先歇会儿，跟我说说"],
        "source": "demo",
    },
    {
        "contact_id": "demo-partner",
        "relationship": "partner",
        "scene": "daily",
        "incoming": ["你忙完了吗"],
        "my_reply": ["快啦，忙完就来找你"],
        "source": "demo",
    },
    {
        "contact_id": "demo-friend",
        "relationship": "friend",
        "scene": "joking",
        "incoming": ["我今天又迟到了"],
        "my_reply": ["不愧是你哈哈哈"],
        "source": "demo",
    },
    {
        "contact_id": "demo-friend",
        "relationship": "friend",
        "scene": "invitation",
        "incoming": ["周末出来吃饭不"],
        "my_reply": ["行啊，整起"],
        "source": "demo",
    },
    {
        "contact_id": "demo-family",
        "relationship": "family",
        "scene": "daily",
        "incoming": ["晚上回来吃饭吗"],
        "my_reply": ["回来，我下班前再跟你说一声"],
        "source": "demo",
    },
    {
        "contact_id": "demo-family",
        "relationship": "family",
        "scene": "concern",
        "incoming": ["最近是不是又没好好休息"],
        "my_reply": ["这两天有点忙，我今晚早点睡，你别担心"],
        "source": "demo",
    },
]


def ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (ROOT / "private").mkdir(parents=True, exist_ok=True)
    initialize_config_storage(seed_demo_contacts=not CONFIG_DB_FILE.exists())
    if not MESSAGES_FILE.exists():
        for item in DEMO_MESSAGES:
            append_jsonl(MESSAGES_FILE, item)
    if not WECHAT_RAW_MESSAGES_FILE.exists():
        WECHAT_RAW_MESSAGES_FILE.touch()
    if not FEEDBACK_FILE.exists():
        FEEDBACK_FILE.touch()
    if not PROFILE_FILE.exists():
        write_json(
            PROFILE_FILE,
            {
                "sample_count": 0,
                "summary": "尚未使用你的聊天记录进行风格提炼。",
                "expression_dna": [],
                "relationship_profiles": {},
            },
        )
    if not AUTOMATION_STATE_FILE.exists():
        write_json(AUTOMATION_STATE_FILE, {"cursors": {}, "last_run_at": ""})
    if not AUTOMATION_EVENTS_FILE.exists():
        AUTOMATION_EVENTS_FILE.touch()
    SELF_SKILL_DIR.mkdir(parents=True, exist_ok=True)
    CONTACT_SKILL_DIR.mkdir(parents=True, exist_ok=True)


def _connect_config_db() -> sqlite3.Connection:
    path = CONFIG_DB_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS settings "
        "(name TEXT PRIMARY KEY, payload TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS contacts "
        "(contact_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
    )
    return connection


def _load_setting(
    connection: sqlite3.Connection,
    name: str,
    default: dict[str, Any],
) -> dict[str, Any]:
    row = connection.execute(
        "SELECT payload FROM settings WHERE name = ?", (name,)
    ).fetchone()
    if row:
        return json.loads(row[0])
    connection.execute(
        "INSERT INTO settings(name, payload) VALUES(?, ?)",
        (name, json.dumps(default, ensure_ascii=False)),
    )
    connection.commit()
    return default


def initialize_config_storage(*, seed_demo_contacts: bool = True) -> None:
    connection = _connect_config_db()
    try:
        _load_setting(connection, "runtime", DEFAULT_RUNTIME_SETTINGS)
        _load_setting(connection, "auto_reply", DEFAULT_AUTO_REPLY_SETTINGS)
        count = connection.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        if not count and seed_demo_contacts:
            connection.executemany(
                "INSERT OR REPLACE INTO contacts(contact_id, payload) VALUES(?, ?)",
                [
                    (str(item["contact_id"]), json.dumps(item, ensure_ascii=False))
                    for item in DEMO_CONTACTS
                    if item.get("contact_id")
                ],
            )
            connection.commit()
    finally:
        connection.close()


def load_runtime_config() -> dict[str, Any]:
    connection = _connect_config_db()
    try:
        return _load_setting(connection, "runtime", DEFAULT_RUNTIME_SETTINGS)
    finally:
        connection.close()


def save_runtime_config(
    value: dict[str, Any]
) -> None:
    connection = _connect_config_db()
    try:
        connection.execute(
            "INSERT OR REPLACE INTO settings(name, payload) VALUES(?, ?)",
            ("runtime", json.dumps(value, ensure_ascii=False)),
        )
        connection.commit()
    finally:
        connection.close()


def load_auto_reply_config() -> dict[str, Any]:
    connection = _connect_config_db()
    try:
        return _load_setting(connection, "auto_reply", DEFAULT_AUTO_REPLY_SETTINGS)
    finally:
        connection.close()


def save_auto_reply_config(
    value: dict[str, Any],
) -> None:
    connection = _connect_config_db()
    try:
        connection.execute(
            "INSERT OR REPLACE INTO settings(name, payload) VALUES(?, ?)",
            ("auto_reply", json.dumps(value, ensure_ascii=False)),
        )
        connection.commit()
    finally:
        connection.close()


def load_contacts() -> list[dict[str, Any]]:
    connection = _connect_config_db()
    try:
        rows = connection.execute(
            "SELECT payload FROM contacts ORDER BY rowid"
        ).fetchall()
        if rows:
            return [json.loads(row[0]) for row in rows]
        return []
    finally:
        connection.close()


def save_contacts(
    contacts: list[dict[str, Any]],
) -> None:
    connection = _connect_config_db()
    try:
        connection.execute("DELETE FROM contacts")
        connection.executemany(
            "INSERT INTO contacts(contact_id, payload) VALUES(?, ?)",
            [
                (str(item["contact_id"]), json.dumps(item, ensure_ascii=False))
                for item in contacts
                if item.get("contact_id")
            ],
        )
        connection.commit()
    finally:
        connection.close()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            content = handle.read()
        if not content.strip():
            return default
        return json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    temporary.replace(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False) + "\n")


def load_skill(skill_id: str) -> dict[str, Any]:
    path = SKILLS_DIR / "relationships" / f"{skill_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(skill_id)
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_all_skills() -> list[dict[str, Any]]:
    return [load_skill(skill_id) for skill_id in ("partner", "friend", "family")]


def load_safety_config() -> dict[str, Any]:
    """Load risk labels and keywords from the single runtime safety config."""
    if not SAFETY_FILE.exists():
        return {}
    with SAFETY_FILE.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}
