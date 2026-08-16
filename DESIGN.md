# Design Doc — Usage Metering & Billing Engine

## Problem
SaaS tenants need three questions answered correctly, under retries and failures:
1. How much have they used this month?
2. What does that cost?
3. Have they hit their plan's limit?

A single bug here means double-charging, giving away free access, or losing revenue.
This system meters usage idempotently, enforces quotas at exact boundaries, computes
AI-token cost with real pricing rules, and keeps subscription state in sync with Stripe
via verified, deduplicated webhooks.

## Data model

- **Tenant** — id, name, created_at
- **Plan** — id, name (Free/Pro), api_call_limit, ai_token_limit, price_id (Stripe)
- **Subscription** — id, tenant_id, plan_id, stripe_subscription_id, status, updated_at
- **UsageEvent** — id, tenant_id, type (api_call | ai_tokens), quantity, idempotency_key (unique),
  metadata (input/cached_input/output/reasoning token breakdown for ai_tokens), created_at
- **ProcessedWebhookEvent** — stripe_event_id (unique, for dedup), processed_at

Tenant isolation: every query is scoped by `tenant_id`; no cross-tenant reads.

## API surface

- `POST /generate` — dummy billable endpoint. Body: `{tenant_id, idempotency_key, usage_type, quantity, token_breakdown?}`.
  Flow: MeterService.record → quota check → cost calc → response.
- `GET /usage?tenant_id=` — rollup: `{used, limit, cost}` per usage type for the current month.
- `POST /checkout` — creates a Stripe test-mode Checkout session for the Pro plan.
- `POST /webhooks/stripe` — verifies signature, dedupes by `stripe_event_id`, updates
  Subscription/Plan on `checkout.session.completed`, `customer.subscription.updated`,
  `customer.subscription.deleted`.

## Idempotency strategy

`UsageEvent.idempotency_key` is unique per tenant. On `POST /generate`, attempt insert;
on unique-constraint conflict, fetch and return the original event's result instead of
creating a new one. Same pattern for webhooks, keyed on Stripe's `event.id`.

## Layer sketch

```
HTTP layer (FastAPI routes)
   ↓
Service layer (metering.py, quotas.py, pricing.py, webhooks.py)
   ↓
Data layer (SQLModel models + db.py session)
```
Routes never touch the DB directly — only through service functions, so the DB
(SQLite → Postgres) or payment provider could be swapped without touching business logic.

## Non-goal

No proration, invoicing, or overage billing in the core build — those are stretch
goals only if the core Definition of Done ships first.
