# EVIDENCE.md

One pasted proof per Definition-of-Done checkbox. Fill in as each phase completes —
a test name + output, a curl transcript, or a log line. Claims without evidence score as not done.

## Metering
- [x] A billable action creates exactly one usage event, even under retries (deduplicated by idempotency key)
  - Evidence: `tests/test_metering.py::test_duplicate_idempotency_key_does_not_double_count` and
    `test_retry_ten_times_still_one_event` — 10 identical retries produce exactly 1 row.
- [x] A test proves double-counting cannot happen
  - Evidence: `pytest -q tests/test_metering.py` → 5 passed. Includes a race-condition path
    (`IntegrityError` caught in `record_usage`) for concurrent identical requests.

## Quotas
- [x] Usage is checked against the tenant's plan; requests over the limit are rejected
  - Evidence: `tests/test_quotas.py::test_rejects_the_call_that_would_exceed_the_limit`
- [x] Responses carry correct status codes (429 / 402) and a message explaining why
  - Evidence: `test_allows_request_that_lands_exactly_on_the_limit` (boundary inclusive),
    `test_rejects_when_no_subscription_exists` / `test_rejects_when_subscription_is_canceled`
    (402 via `PaymentRequiredError`), `test_rejects_the_call_that_would_exceed_the_limit`
    (429 via `QuotaExceededError`). `app/main.py` maps these to HTTP 402/429 with `.message` as detail.
    Full suite: `pytest -q` → 11 passed.

## Cost calculation
- [x] Monthly usage rolls up into a cost figure per tenant
  - Evidence: live run — `GET /usage?tenant_id=1` → `{"api_calls":{"used":999,...},"ai_tokens":{"used":100000,...},
    "cost":{"micro_dollars":126000,"display":"$0.126000"}}` — combines 999 API calls ($0.0999) +
    100k AI tokens ($0.0261) into one rollup, computed fresh from stored usage events each call.
- [x] AI token pricing handles cached input tokens, reasoning tokens, and output pricing correctly
  - Evidence: `tests/test_pricing.py::test_cached_input_tokens_are_cheaper_than_fresh_input` (cached
    priced at $0.03/1M vs $0.15/1M fresh), `test_reasoning_tokens_are_billed_at_the_output_rate`
    (reasoning == output rate, not free, not separate), `test_mixed_categories_are_priced_independently_not_flattened`
    (pinned regression: 500k of each category → exactly $0.690000, proving categories aren't summed at
    one flat rate). Live run: `POST /generate` with input=50000, cached_input=20000, output=20000,
    reasoning=10000 → `cost_micro_dollars: 26100` ($0.0261), matching hand-computed expected value exactly.
- [x] Pricing constants are pinned and covered by tests
  - Evidence: `app/pricing.py` — `PRICE_PER_MILLION_TOKENS_MICRO_DOLLARS` and
    `PRICE_PER_API_CALL_MICRO_DOLLARS` are the single source of truth; `tests/test_pricing.py`
    (11 tests) asserts against these constants directly, not hardcoded numbers, so a constant
    change and a calculation bug can't silently cancel out. Full suite: `pytest -q` → 31 passed.

## Stripe integration

**Note:** real Stripe (and Paddle, Lemon Squeezy, Razorpay) all require a
seller entity registered in a supported country — Pakistan is not on any of
their lists. With mentor sign-off, this capstone uses a self-built
"FakeStripe" (`app/fake_stripe.py`) that reproduces Stripe's actual webhook
contract: HMAC-SHA256 signing over `"<timestamp>.<payload>"`, a
`Stripe-Signature`-style header, and Stripe-shaped events
(`checkout.session.completed`, `customer.subscription.updated/deleted`).
See README "Limitations" for the full rationale.

- [x] Subscription checkout works end-to-end in test mode
  - Evidence: live run — `POST /checkout {tenant_id:1, plan_name:"Pro"}` → session created;
    `POST /fake-checkout/{id}/pay` → signed event returned; `POST /webhooks/stripe` with that
    event → `{"status":"processed", ...}`. `GET /usage?tenant_id=1` before: `{"api_calls":{"used":999,"limit":1000}}`
    (Free). After: `{"api_calls":{"used":999,"limit":100000}}` (Pro) — plan flipped live.
- [x] Webhooks verify signatures, ignore duplicate events, and update tenant plan/status
  - Evidence: `tests/test_webhooks.py` — 12 tests covering valid signature, forged signature
    (rejected), tampered payload (rejected), stale timestamp (rejected), malformed header
    (rejected), checkout→plan sync, exact-once dedup, subscription deleted/updated, unknown
    event types ignored gracefully. Live run: replaying the same signed event → `ignored_duplicate`;
    sending with a wrong secret → `HTTP 400 {"detail":"Signature does not match payload"}`.
    Full suite: `pytest -q` → 21 passed.

## Data model, tests & documentation
- [ ] Database includes tenants, plans, subscriptions, and usage events; customer data isolated per tenant
  - Evidence:
- [ ] Tests cover: duplicate usage prevention, quota boundary cases (at/just under/over), cost calculations, invalid-webhook rejection, duplicate-webhook handling
  - Evidence:
- [ ] README + architecture diagram + setup instructions; submission-pack files present
  - Evidence:
