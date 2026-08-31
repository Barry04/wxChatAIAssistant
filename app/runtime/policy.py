from dataclasses import dataclass
from typing import Literal

# Automatic sending is intentionally limited to ordinary L0 chat. L1/L2
# remain draftable but always require an explicit confirmation.
AUTO_SENDABLE_LEVELS = {"L0"}

PolicyDecision = Literal["auto_send", "needs_confirmation", "blocked"]


@dataclass(frozen=True)
class PolicyResult:
    decision: PolicyDecision
    reason: str


def evaluate_send_policy(
    *,
    candidate: str,
    risk_level: str,
    auto_send_levels: list[str] | tuple[str, ...],
    requires_confirmation: bool,
    provider: str,
    model_fallback: bool,
    dry_run: bool,
    enabled: bool,
    real_send_acknowledged: bool,
) -> PolicyResult:
    """判断能否自动交给 Operator；不改写正文，也不发送。"""
    if risk_level == "L3" or not candidate:
        return PolicyResult(
            "blocked",
            "risk_l3" if risk_level == "L3" else "no_candidate",
        )

    sendable = (
        risk_level in AUTO_SENDABLE_LEVELS
        and risk_level in auto_send_levels
        and not requires_confirmation
    )
    if sendable:
        if (
            provider == "demo"
            or model_fallback
            or dry_run
            or not enabled
            or not real_send_acknowledged
        ):
            reason = (
                "demo_provider"
                if provider == "demo"
                else "model_fallback"
                if model_fallback
                else "dry_run"
                if dry_run
                else "real_send_not_acknowledged"
            )
            return PolicyResult("needs_confirmation", reason)
        return PolicyResult("auto_send", "policy_ok")

    return PolicyResult(
        "needs_confirmation",
        "model_fallback"
        if model_fallback
        else "low_confidence_or_multi_message"
        if requires_confirmation
        else "risk_confirmation",
    )
