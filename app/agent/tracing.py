from __future__ import annotations

import time
from typing import Any


def start_timer() -> float:
    return time.perf_counter()


def make_trace_event(
    role: str,
    status: str,
    started_at: float,
    summary: str,
    **extra: Any,
) -> dict[str, Any]:
    event = {
        "role": role,
        "status": status,
        "duration_ms": int((time.perf_counter() - started_at) * 1000),
        "summary": summary,
    }
    event.update(extra)
    return event
