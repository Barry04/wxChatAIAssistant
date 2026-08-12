from typing import Literal

from pydantic import BaseModel, Field


Relationship = Literal["partner", "friend", "family"]


class Contact(BaseModel):
    contact_id: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=80)
    relationship: Relationship
    wechat_username: str = Field(default="", max_length=160)
    chat_type: Literal["private", "group"] = "private"
    participant_count: int | None = Field(default=None, ge=1)
    group_trigger_mode: Literal["mention_only", "all_messages"] = "mention_only"
    group_mention_keywords: list[str] = Field(default_factory=list)
    preferred_address: str = Field(default="", max_length=40)
    message_length: Literal["very_short", "short", "medium"] = "short"
    emoji_level: Literal["none", "low", "medium", "high"] = "low"
    humor_level: Literal["low", "medium", "high"] = "medium"
    boundaries: list[str] = Field(default_factory=list)
    style_preset_id: str = Field(default="", max_length=120)
    is_demo: bool = False


class ContactStyleUpdate(BaseModel):
    style_preset_id: str = Field(default="", max_length=120)


class ImportTextRequest(BaseModel):
    contact_id: str
    relationship: Relationship
    content: str = Field(min_length=1)
    self_label: str = "我"


class GenerateRequest(BaseModel):
    contact_id: str
    conversation: str = Field(min_length=1, max_length=12000)
    style_preset_id: str = Field(default="", max_length=120)


class FeedbackRequest(BaseModel):
    contact_id: str
    conversation: str
    selected_text: str
    final_text: str = Field(min_length=1)
    scene: str = "daily"


class RuntimeSettings(BaseModel):
    provider: Literal["demo", "ollama", "openai-compatible"] = "demo"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3:8b"
    api_key: str = ""


class AutoReplyContactSettings(BaseModel):
    memory_sync_enabled: bool | None = None
    enabled: bool | None = None
    dry_run: bool | None = None
    real_send_acknowledged: bool | None = None
    takeover_delay_seconds: int | None = Field(default=None, ge=0, le=3600)
    auto_send_levels: list[Literal["L0", "L1", "L2", "L3"]] | None = None


class AutoReplySettings(BaseModel):
    memory_sync_enabled: bool = True
    enabled: bool = False
    dry_run: bool = True
    real_send_acknowledged: bool = False
    poll_interval_seconds: int = Field(default=3, ge=1, le=30)
    takeover_delay_seconds: int = Field(default=300, ge=0, le=3600)
    allowed_contact_ids: list[str] = Field(default_factory=list)
    auto_send_levels: list[Literal["L0", "L1", "L2", "L3"]] = Field(
        default_factory=lambda: ["L0"]
    )
    contact_settings: dict[str, AutoReplyContactSettings] = Field(
        default_factory=dict
    )


class AutomationConfirmationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200)


class WeChatHistoryImportRequest(BaseModel):
    session_limit: int = Field(default=100, ge=1, le=500)
    session_offset: int = Field(default=0, ge=0, le=500)
    messages_per_session: int = Field(default=50000, ge=20, le=50000)
    include_groups: bool = True


class WeChatContactImportRequest(BaseModel):
    message_limit: int = Field(default=50000, ge=20, le=50000)
