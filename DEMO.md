# DEMO.md — the final 6-minute demo

Matches §13 of the capstone brief exactly. Rehearse this twice before the real thing.

## Setup (before the demo starts)

```
rm -f billing.db          # or: del billing.db   (start from a clean slate)
python -m app.seed        # creates Free/Pro plans + tenant_id=1 at 999/1000 API calls
uvicorn app.main:app --reload
```

In a second terminal, run the automated walkthrough once to rehearse the flow and see exact
expected output:

```
python -m tools.demo
```

Alternatively, open `http://localhost:8000/dashboard` in a browser for a visual walkthrough —
click "Meter 1 API call" repeatedly to watch the gauge fill and the warning/critical alert
appear, then "Upgrade to Pro" to watch the plan flip live. Good as a visual companion during
the demo, alongside (not instead of) the terminal output the evaluator actually probes against.

## The flow, live (narrate each step)

1. **Boundary refusal** — `POST /generate` for tenant 1, one more API call. It lands exactly on
   1000/1000 (allowed, boundary is inclusive). One more after that → `429` with a clear message.
2. **Retry, no double-count** — same `idempotency_key` as the allowed call → `duplicate: true`,
   same `usage_event_id`. One row, not two.
3. **Checkout → Pro** — `POST /checkout` → `POST /fake-checkout/{id}/pay` → deliver the signed
   event to `POST /webhooks/stripe` → `GET /usage` now shows Pro limits (100,000 / 10,000,000).
4. **Forged webhook rejected, replay ignored** — send an event signed with the wrong secret →
   `400`, nothing changes. Resend the real event from step 3 → `ignored_duplicate`.
5. **Final `/usage`** — used / limit / cost all lining up, with `pytest -q` (31 passing) on screen.
6. **Closing line**: "Usage, money, and customer access stay correct under retries, failures, and
   real-world conditions."

## If asked "why not real Stripe?"

Have this ready — it's in README.md → Limitations and EVIDENCE.md → Stripe integration:
Stripe, Paddle, Lemon Squeezy, and Razorpay all require a seller entity registered in a
supported country, and Pakistan isn't on any of their lists — verified this while building
Phase 3. FakeStripe (`app/fake_stripe.py`) reproduces Stripe's actual webhook contract
(HMAC-SHA256 signing, `Stripe-Signature`-style header, Stripe-shaped events), so signature
verification, replay protection, and dedup are genuinely tested, not faked away. Swapping in
real Stripe later only touches `app/fake_stripe.py` and `app/checkout.py`.

## If something doesn't go as expected live

- Server not seeded / wrong tenant state → `rm billing.db && python -m app.seed` and restart.
- Forgot the exact curl syntax → `python -m tools.demo` prints every request and response, use
  it as a live reference instead of typing commands from memory.
