"""
Usage alerts — §9 stretch goal: notify customers at 80% and 100% of quota.

Pure function of (used, limit) pairs — no DB access, so it's trivially testable
and reusable from both the API response and, later, a background notifier.
"""
from typing import Optional


def _alert_for(used: int, limit: int, usage_type: str) -> Optional[dict]:
    if limit <= 0:
        return None

    percent = used / limit

    if percent >= 1.0:
        return {
            "level": "critical",
            "usage_type": usage_type,
            "message": f"{usage_type} usage is at 100% of quota ({used}/{limit}).",
        }
    if percent >= 0.8:
        return {
            "level": "warning",
            "usage_type": usage_type,
            "message": f"{usage_type} usage is at {int(percent * 100)}% of quota ({used}/{limit}).",
        }
    return None


def compute_alerts(api_used: int, api_limit: int, token_used: int, token_limit: int) -> list[dict]:
    """Returns a list of active alerts (0, 1, or 2 entries) for the two usage types."""
    alerts = []
    api_alert = _alert_for(api_used, api_limit, "api_call")
    if api_alert:
        alerts.append(api_alert)
    token_alert = _alert_for(token_used, token_limit, "ai_tokens")
    if token_alert:
        alerts.append(token_alert)
    return alerts
