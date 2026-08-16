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
- [ ] Monthly usage rolls up into a cost figure per tenant
  - Evidence:
- [ ] AI token pricing handles cached input tokens, reasoning tokens, and output pricing correctly
  - Evidence:
- [ ] Pricing constants are pinned and covered by tests
  - Evidence:

## Stripe integration
- [ ] Subscription checkout works end-to-end in Stripe test mode
  - Evidence:
- [ ] Webhooks verify signatures, ignore duplicate events, and update tenant plan/status
  - Evidence:

## Data model, tests & documentation
- [ ] Database includes tenants, plans, subscriptions, and usage events; customer data isolated per tenant
  - Evidence:
- [ ] Tests cover: duplicate usage prevention, quota boundary cases (at/just under/over), cost calculations, invalid-webhook rejection, duplicate-webhook handling
  - Evidence:
- [ ] README + architecture diagram + setup instructions; submission-pack files present
  - Evidence:
