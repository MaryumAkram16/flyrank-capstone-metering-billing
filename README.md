# Usage Metering & Billing Engine

The backend service every SaaS needs: how much has this customer used, what does it
cost, and have they hit their limit? Idempotent metering, exact quota boundaries,
AI-token cost math, and Stripe test-mode subscription sync.

## Architecture

```
Client ──► POST /generate
              └─► MeterService.record(tenant, type, qty, idempotency_key)
                    ├─ duplicate key? → return original result
                    ├─ store usage_event
                    └─► Quota check ─► allowed
                          └─ limit exceeded → 402 / 429 + message

GET /usage ◄── rollup(usage_events) → { used, limit, cost }

FakeStripe Checkout (test mode) ─► subscription created
FakeStripe ─signed webhook─► /webhooks/stripe
   ├─► verify signature (forged → 400)
   ├─► dedupe event (replay → ignored)
   └─► update tenant plan/status
```

### Checkout flow (FakeStripe)

```
POST /checkout {tenant_id, plan_name}
   → creates a CheckoutSession, returns {id, url}

POST /fake-checkout/{id}/pay          (stands in for Stripe's hosted page)
   → marks the session complete, returns a signed
     checkout.session.completed event (does NOT touch the DB)

POST /webhooks/stripe                 (the real integration point)
   → verifies the signature, dedupes by event id,
     updates Subscription.plan_id/status
```

## Setup (clean machine)

```
git clone <repo-url>
cd flyrank-capstone-metering-billing
py -3.11 -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env           # fill in Stripe test keys
python -m app.seed             # seed a tenant near quota
uvicorn app.main:app --reload
```

Run tests: `pytest -q`

## Limitations

- No proration, invoicing, or overage billing (out of core scope — see DESIGN.md non-goal).
- AI token usage is simulated, not pulled from a real model call.
- **Payment provider**: this uses a self-built "FakeStripe" (`app/fake_stripe.py`) instead of
  real Stripe. Stripe, Paddle, Lemon Squeezy, and Razorpay all require a seller entity
  registered in a supported country, and Pakistan isn't on any of their lists — verified while
  building this. FakeStripe reproduces Stripe's actual webhook contract (HMAC-SHA256 signing
  over `"<timestamp>.<payload>"`, a `Stripe-Signature`-style header, Stripe-shaped events) so
  signature verification, replay protection, and dedup are genuinely tested — not faked away.
  Swapping in real Stripe later only touches `app/fake_stripe.py` and `app/checkout.py`; the
  webhook handler and data model don't change.

## Status

Phase 1 (design) — done.
Phase 2 (core billing logic: idempotent metering + quota enforcement) — done, 11/11 tests passing.
Phase 3 (FakeStripe checkout + signed/deduped webhooks) — done, 21/21 tests passing.
See DESIGN.md and EVIDENCE.md for current state.
