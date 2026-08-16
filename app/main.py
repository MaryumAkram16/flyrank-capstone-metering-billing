import json
import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from app.checkout import CheckoutError, complete_checkout_session, create_checkout_session
from app.db import get_session, init_db
from app.fake_stripe import SignatureVerificationError, build_event, sign_payload, verify_and_parse
from app.metering import record_usage
from app.quotas import (
    PaymentRequiredError,
    QuotaExceededError,
    current_usage,
    enforce_quota,
    get_plan_for_tenant,
)
from app.webhook_handlers import handle_event

# FakeStripe stands in for real Stripe test mode (see app/fake_stripe.py for why).
# In a real Stripe setup this would be the whsec_ signing secret from the Dashboard.
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_fake_test_secret_change_me")

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


class CheckoutRequest(BaseModel):
    tenant_id: int
    plan_name: str  # e.g. "Pro"


@app.post("/checkout")
def checkout(payload: CheckoutRequest, session: Session = Depends(get_session)):
    """Creates a Checkout session — the equivalent of Stripe's Checkout Session create call."""
    try:
        cs = create_checkout_session(session, payload.tenant_id, payload.plan_name)
    except CheckoutError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": cs.id, "url": f"/fake-checkout/{cs.id}/pay", "status": cs.status}


@app.post("/fake-checkout/{session_id}/pay")
def fake_checkout_pay(session_id: str, session: Session = Depends(get_session)):
    """
    Dev-only stand-in for Stripe's hosted Checkout page. Simulates the customer
    paying, then returns the event + signature that "Stripe" would deliver to
    the webhook endpoint. This endpoint does NOT touch Subscription/Plan —
    only POST /webhooks/stripe does that, same separation as real Stripe.
    """
    try:
        data_object = complete_checkout_session(session, session_id)
    except CheckoutError as e:
        raise HTTPException(status_code=400, detail=str(e))

    event = build_event("checkout.session.completed", data_object)
    payload_bytes = json.dumps(event).encode()
    signature = sign_payload(payload_bytes, STRIPE_WEBHOOK_SECRET)

    return {"event": event, "stripe_signature": signature}


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request, session: Session = Depends(get_session)):
    """
    Real webhook endpoint. Verifies the signature first — a forged or
    tampered payload never reaches event-processing logic.
    """
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = verify_and_parse(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return handle_event(session, event)
