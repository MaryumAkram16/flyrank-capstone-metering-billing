from datetime import datetime, timezone

from sqlmodel import Session, func, select

from app.models import Plan, Subscription, UsageEvent

ACTIVE_STATUSES = {"active", "trialing"}


class QuotaExceededError(Exception):
    """Raised when a request would push usage over the plan's monthly limit → 429."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class PaymentRequiredError(Exception):
    """Raised when the tenant has no active subscription → 402."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def get_plan_for_tenant(session: Session, tenant_id: int) -> Plan:
    subscription = session.exec(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    ).first()

    if subscription is None:
        raise PaymentRequiredError(f"No subscription found for tenant {tenant_id}.")

    if subscription.status not in ACTIVE_STATUSES:
        raise PaymentRequiredError(
            f"Subscription status is '{subscription.status}' — payment required to resume access."
        )

    plan = session.get(Plan, subscription.plan_id)
    if plan is None:
        raise PaymentRequiredError(f"Subscription references a missing plan.")
    return plan


def current_usage(session: Session, tenant_id: int, usage_type: str) -> int:
    """Sum of quantity for this tenant + usage type, for the current calendar month."""
    since = _month_start()
    total = session.exec(
        select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.type == usage_type,
            UsageEvent.created_at >= since,
        )
    ).one()
    return int(total or 0)


def _limit_for(plan: Plan, usage_type: str) -> int:
    return plan.api_call_limit if usage_type == "api_call" else plan.ai_token_limit


def enforce_quota(
    session: Session, tenant_id: int, usage_type: str, quantity: int
) -> tuple[int, int]:
    """
    Check whether `quantity` more usage is allowed before it happens.

    A request that lands EXACTLY on the limit (used + quantity == limit) is allowed —
    the limit is inclusive. Only usage that would exceed it is rejected.

    Returns (used_before_this_call, limit). Raises PaymentRequiredError or
    QuotaExceededError if the request should be blocked.
    """
    plan = get_plan_for_tenant(session, tenant_id)
    limit = _limit_for(plan, usage_type)
    used = current_usage(session, tenant_id, usage_type)

    if used + quantity > limit:
        raise QuotaExceededError(
            f"Usage quota exceeded for '{usage_type}': {used}/{limit} used this month, "
            f"this request needs {quantity} more."
        )

    return used, limit
