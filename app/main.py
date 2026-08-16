import json
import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.alerts import compute_alerts
from app.checkout import CheckoutError, complete_checkout_session, create_checkout_session
from app.db import get_session, init_db
from app.fake_stripe import SignatureVerificationError, build_event, sign_payload, verify_and_parse
from app.metering import record_usage
from app.pricing import calculate_event_cost_micro_dollars, micro_dollars_to_display, rollup_cost_micro_dollars
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

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Usage Metering & Billing Engine")


@app.get("/dashboard")
def dashboard():
    """Serves the usage dashboard — a small vanilla-JS frontend over the JSON API below."""
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


class GenerateRequest(BaseModel):
    tenant_id: int
    idempotency_key: str
    usage_type: str  # "api_call" | "ai_tokens"
    quantity: Optional[int] = Field(default=None, gt=0)  # required for api_call; derived from metadata for ai_tokens
    metadata: Optional[dict] = None  # for ai_tokens: input_tokens, cached_input_tokens, output_tokens, reasoning_tokens


@app.post("/generate")
def generate(payload: GenerateRequest, session: Session = Depends(get_session)):
    """
    Dummy billable endpoint. Flow:
      1. Duplicate idempotency key → return the original result, no side effects.
      2. For ai_tokens, quantity is DERIVED from the token breakdown in metadata
         (input + cached_input + output + reasoning) — never taken from the client
         directly, so quota and cost always agree with what was actually recorded.
      3. Check the quota BEFORE recording anything — a request that would exceed
         the limit is rejected and never metered.
      4. If allowed, record the usage event and return its cost.
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
        existing_metadata = json.loads(existing.metadata_json) if existing.metadata_json else None
        cost = calculate_event_cost_micro_dollars(existing.type, existing.quantity, existing_metadata)
        return {
            "status": "ok",
            "duplicate": True,
            "usage_event_id": existing.id,
            "quantity": existing.quantity,
            "cost_micro_dollars": cost,
            "cost_display": micro_dollars_to_display(cost),
        }

    if payload.usage_type == "ai_tokens":
        meta = payload.metadata or {}
        required_fields = ["input_tokens", "cached_input_tokens", "output_tokens"]
        missing = [f for f in required_fields if f not in meta]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"ai_tokens usage requires metadata fields: {missing}",
            )

        token_fields = ["input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens"]
        invalid = [
            f for f in token_fields
            if f in meta and (not isinstance(meta[f], int) or meta[f] < 0)
        ]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Token counts must be non-negative integers: {invalid}",
            )

        quantity = (
            meta.get("input_tokens", 0)
            + meta.get("cached_input_tokens", 0)
            + meta.get("output_tokens", 0)
            + meta.get("reasoning_tokens", 0)
        )
    else:
        # api_call: quantity defaults to 1 (one call = one unit), but callers
        # can pass a larger batch size explicitly if they're metering in bulk.
        # Field(gt=0) on the request model already rejects zero/negative values.
        quantity = payload.quantity if payload.quantity is not None else 1

    try:
        used_before, limit = enforce_quota(session, payload.tenant_id, payload.usage_type, quantity)
    except PaymentRequiredError as e:
        raise HTTPException(status_code=402, detail=e.message)
    except QuotaExceededError as e:
        raise HTTPException(status_code=429, detail=e.message)

    event, created = record_usage(
        session,
        payload.tenant_id,
        payload.idempotency_key,
        payload.usage_type,
        quantity,
        payload.metadata,
    )

    cost = calculate_event_cost_micro_dollars(payload.usage_type, quantity, payload.metadata)

    return {
        "status": "ok",
        "duplicate": not created,
        "usage_event_id": event.id,
        "quantity": event.quantity,
        "used_this_month": used_before + quantity,
        "limit": limit,
        "cost_micro_dollars": cost,
        "cost_display": micro_dollars_to_display(cost),
    }


@app.get("/usage")
def usage(tenant_id: int, session: Session = Depends(get_session)):
    try:
        plan = get_plan_for_tenant(session, tenant_id)
    except PaymentRequiredError as e:
        raise HTTPException(status_code=402, detail=e.message)

    api_used = current_usage(session, tenant_id, "api_call")
    token_used = current_usage(session, tenant_id, "ai_tokens")
    cost = rollup_cost_micro_dollars(session, tenant_id)
    alerts = compute_alerts(api_used, plan.api_call_limit, token_used, plan.ai_token_limit)

    return {
        "tenant_id": tenant_id,
        "plan_name": plan.name,
        "api_calls": {"used": api_used, "limit": plan.api_call_limit},
        "ai_tokens": {"used": token_used, "limit": plan.ai_token_limit},
        "cost": {"micro_dollars": cost, "display": micro_dollars_to_display(cost)},
        "alerts": alerts,
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

    # Return the RAW payload string, not the parsed event object. The signature
    # was computed over these exact bytes — a caller that re-serializes the
    # parsed object (e.g. JavaScript's JSON.stringify) will produce different
    # bytes (different whitespace) and the signature will no longer match.
    # Real Stripe integrations hit this same class of bug: always verify
    # against the raw delivered body, never a re-encoded copy of it.
    return {"payload": payload_bytes.decode(), "stripe_signature": signature}


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
