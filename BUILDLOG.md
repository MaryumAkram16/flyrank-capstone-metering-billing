# BUILDLOG.md

Honest log of where AI helped, where it was wrong, and what was changed. Updated per session.

## Session 1 — 2026-08-16
- What I asked AI for: full build of the capstone across Phases 1-5 — design doc, data model,
  idempotent metering, quota enforcement, Stripe integration, cost math, and demo prep.
- What it got right: the idempotency and quota-boundary logic worked correctly on the first
  test run (11/11 passing). The pinned pricing math (cached input cheaper, reasoning billed as
  output) matched hand-calculated expected values exactly on the first live test.
- What it got wrong / had to fix: (1) Stripe is not usable from Pakistan — neither are Paddle,
  Lemon Squeezy, or Razorpay, all of which require a seller entity in a supported country. AI
  researched this and proposed a self-built "FakeStripe" mirroring Stripe's actual webhook
  signing contract instead, which I approved. (2) While refactoring `app/quotas.py` to share a
  `month_start()` helper, a `str_replace` edit went wrong and left a duplicated, broken
  `current_usage` function with `get_plan_for_tenant`'s body accidentally clobbered. Caught by
  viewing the file before moving on — rewrote the file cleanly and reran the full suite to
  confirm the fix. (3) Phase 4 made `quantity` optional on `/generate` for `ai_tokens` (derived
  from the token breakdown) but the `api_call` branch still required an explicit `quantity`,
  which broke the demo script's plain API-call requests with a 400. Caught by actually running
  the demo end-to-end against a live server rather than trusting the test suite alone — fixed
  by defaulting `api_call` quantity to 1 when omitted.
- What I changed or wrote myself: reviewed and approved the FakeStripe design decision; ran
  `pytest -q` and the live demo myself after each phase to confirm the numbers before moving on.
