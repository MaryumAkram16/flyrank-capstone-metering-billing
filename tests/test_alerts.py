from app.alerts import compute_alerts


def test_no_alert_below_80_percent():
    assert compute_alerts(api_used=500, api_limit=1000, token_used=1000, token_limit=100_000) == []


def test_warning_alert_at_exactly_80_percent():
    alerts = compute_alerts(api_used=800, api_limit=1000, token_used=0, token_limit=100_000)
    assert len(alerts) == 1
    assert alerts[0]["level"] == "warning"
    assert alerts[0]["usage_type"] == "api_call"


def test_no_warning_just_under_80_percent():
    assert compute_alerts(api_used=799, api_limit=1000, token_used=0, token_limit=100_000) == []


def test_critical_alert_at_exactly_100_percent():
    alerts = compute_alerts(api_used=1000, api_limit=1000, token_used=0, token_limit=100_000)
    assert len(alerts) == 1
    assert alerts[0]["level"] == "critical"


def test_critical_alert_takes_priority_over_warning():
    """A usage_type is never both warning AND critical — only the higher-severity one fires."""
    alerts = compute_alerts(api_used=1000, api_limit=1000, token_used=0, token_limit=100_000)
    assert len(alerts) == 1


def test_alerts_for_both_usage_types_are_independent():
    alerts = compute_alerts(api_used=1000, api_limit=1000, token_used=90_000, token_limit=100_000)
    assert len(alerts) == 2
    levels_by_type = {a["usage_type"]: a["level"] for a in alerts}
    assert levels_by_type["api_call"] == "critical"
    assert levels_by_type["ai_tokens"] == "warning"


def test_warning_message_never_rounds_up_to_100_percent():
    """
    Regression: 999/1000 is 99.9%, a warning — the message must say 99%, never
    round up to '100%' (100% is reserved for the critical level).
    """
    alerts = compute_alerts(api_used=999, api_limit=1000, token_used=0, token_limit=100_000)
    assert len(alerts) == 1
    assert alerts[0]["level"] == "warning"
    assert "100%" not in alerts[0]["message"]
    assert "99%" in alerts[0]["message"]


def test_zero_limit_does_not_crash():
    assert compute_alerts(api_used=0, api_limit=0, token_used=0, token_limit=100) == []
