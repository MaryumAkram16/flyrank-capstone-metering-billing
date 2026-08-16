from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field, UniqueConstraint


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=_utcnow)


class Plan(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    api_call_limit: int
    ai_token_limit: int
    price_id: Optional[str] = None


class Subscription(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id")
    plan_id: int = Field(foreign_key="plan.id")
    stripe_subscription_id: Optional[str] = None
    status: str = "active"  # active | trialing | past_due | canceled
    updated_at: datetime = Field(default_factory=_utcnow)


class UsageEvent(SQLModel, table=True):
    """
    One recorded row of billable activity. Idempotency is enforced per tenant:
    the same (tenant_id, idempotency_key) pair can only ever produce one row.
    """
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_tenant_idempotency"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id")
    idempotency_key: str
    type: str  # "api_call" | "ai_tokens"
    quantity: int
    metadata_json: Optional[str] = None  # token breakdown for ai_tokens, JSON-encoded
    created_at: datetime = Field(default_factory=_utcnow)


class ProcessedWebhookEvent(SQLModel, table=True):
    """Dedup table for webhook events — same event id processed at most once."""
    stripe_event_id: str = Field(primary_key=True)
    processed_at: datetime = Field(default_factory=_utcnow)


class CheckoutSession(SQLModel, table=True):
    """
    A pending or completed Checkout session. Mirrors Stripe's checkout.Session
    shape closely enough that swapping in real Stripe later only touches
    app/checkout.py and app/fake_stripe.py, not the data model or webhook logic.
    """
    id: str = Field(primary_key=True)  # e.g. "cs_test_<hex>"
    tenant_id: int = Field(foreign_key="tenant.id")
    plan_id: int = Field(foreign_key="plan.id")
    status: str = "open"  # open | complete
    created_at: datetime = Field(default_factory=_utcnow)
