"""系统健康与模型调用日志等元信息路由。"""

from fastapi import APIRouter

from ..storage import MODEL_CALLS_FILE, read_jsonl

router = APIRouter()


@router.get("/api/health")
def health() -> dict:
    return {"status": "ok", "local_only": True}


@router.get("/api/logs/model-calls")
def model_call_logs(limit: int = 50) -> list[dict]:
    """Return redacted model-call metadata; prompts and responses are never logged."""
    return read_jsonl(MODEL_CALLS_FILE)[-max(1, min(limit, 200)) :]
