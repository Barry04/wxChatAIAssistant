from app.runtime.policy import evaluate_send_policy


def _policy(**overrides):
    values = {
        "candidate": "候选回复",
        "risk_level": "L0",
        "auto_send_levels": ["L0"],
        "requires_confirmation": False,
        "provider": "ollama",
        "model_fallback": False,
        "dry_run": False,
        "enabled": True,
        "real_send_acknowledged": True,
    }
    values.update(overrides)
    return evaluate_send_policy(**values)


def test_policy_allows_verified_l0_auto_send():
    result = _policy()
    assert result.decision == "auto_send"


def test_demo_provider_never_auto_sends():
    result = _policy(provider="demo")
    assert result.decision == "needs_confirmation"
    assert result.reason == "demo_provider"


def test_model_fallback_never_auto_sends():
    result = _policy(model_fallback=True)
    assert result.decision == "needs_confirmation"
    assert result.reason == "model_fallback"


def test_dry_run_never_auto_sends():
    result = _policy(dry_run=True)
    assert result.decision == "needs_confirmation"
    assert result.reason == "dry_run"


def test_real_send_not_acknowledged_never_auto_sends():
    result = _policy(real_send_acknowledged=False)
    assert result.decision == "needs_confirmation"
    assert result.reason == "real_send_not_acknowledged"


def test_risk_l3_is_blocked():
    result = _policy(candidate="", risk_level="L3")
    assert result.decision == "blocked"
    assert result.reason == "risk_l3"


def test_risk_l3_with_candidate_is_still_blocked():
    result = _policy(candidate="不该发出去", risk_level="L3")
    assert result.decision == "blocked"
    assert result.reason == "risk_l3"


def test_disabled_never_auto_sends():
    result = _policy(enabled=False)
    assert result.decision == "needs_confirmation"
    assert result.reason == "real_send_not_acknowledged"


def test_low_confidence_never_auto_sends():
    result = _policy(requires_confirmation=True)
    assert result.decision == "needs_confirmation"
    assert result.reason == "low_confidence_or_multi_message"
