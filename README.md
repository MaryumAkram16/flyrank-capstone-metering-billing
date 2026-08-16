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

Stripe Checkout (test mode) ─► subscription created
Stripe ─signed webhook─► /webhooks/stripe
   ├─► verify signature (forged → 400)
   ├─► dedupe event (replay → ignored)
   └─► update tenant plan/status
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

## Status

Phase 1 (design) — done.
Phase 2 (core billing logic: idempotent metering + quota enforcement) — done, 11/11 tests passing.
See DESIGN.md and EVIDENCE.md for current state.
