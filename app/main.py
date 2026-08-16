from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.db import get_session, init_db
from app.metering import record_usage
from app.quotas import (
    PaymentRequiredError,
    QuotaExceededError,
    current_usage,
    enforce_quota,
    get_plan_for_tenant,
)

app = FastAPI(title="Usage Metering & Billing Engine")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


class GenerateRequest(BaseModel):
    tenant_id: int
    idempotency_key: str
    usage_type: str  # "api_call" | "ai_tokens"
    quantity: int
    metadata: Optional[dict] = None


@app.post("/generate")
def generate(payload: GenerateRequest, session: Session = Depends(get_session)):
    """
    Dummy billable endpoint. Flow:
      1. Duplicate idempotency key → return the original result, no side effects.
      2. Otherwise, check the quota BEFORE recording anything — a request that
         would exceed the limit is rejected and never metered.
      3. If allowed, record the usage event.
    """
    from sqlmodel import select

    from app.models import UsageEvent

    existing = session.exec(
        select(UsageEvent).where(
            UsageEvent.tenant_id == payload.tenant_id,
            UsageEvent.idempotency_key == payload.idempotency_key,
        )
    ).first()
    if existing is not None:
        return {
            "status": "ok",
            "duplicate": True,
            "usage_event_id": existing.id,
            "quantity": existing.quantity,
        }

    try:
        used_before, limit = enforce_quota(
            session, payload.tenant_id, payload.usage_type, payload.quantity
        )
    except PaymentRequiredError as e:
        raise HTTPException(status_code=402, detail=e.message)
    except QuotaExceededError as e:
        raise HTTPException(status_code=429, detail=e.message)

    event, created = record_usage(
        session,
        payload.tenant_id,
        payload.idempotency_key,
        payload.usage_type,
        payload.quantity,
        payload.metadata,
    )

    return {
        "status": "ok",
        "duplicate": not created,
        "usage_event_id": event.id,
        "quantity": event.quantity,
        "used_this_month": used_before + payload.quantity,
        "limit": limit,
    }


@app.get("/usage")
def usage(tenant_id: int, session: Session = Depends(get_session)):
    try:
        plan = get_plan_for_tenant(session, tenant_id)
    except PaymentRequiredError as e:
        raise HTTPException(status_code=402, detail=e.message)

    api_used = current_usage(session, tenant_id, "api_call")
    token_used = current_usage(session, tenant_id, "ai_tokens")

    return {
        "tenant_id": tenant_id,
        "api_calls": {"used": api_used, "limit": plan.api_call_limit},
        "ai_tokens": {"used": token_used, "limit": plan.ai_token_limit},
        # cost rollup lands in Phase 4 once pricing.py exists
    }
