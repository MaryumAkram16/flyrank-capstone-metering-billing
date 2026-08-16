# EVIDENCE.md

One pasted proof per Definition-of-Done checkbox. Fill in as each phase completes —
a test name + output, a curl transcript, or a log line. Claims without evidence score as not done.

## Metering
- [ ] A billable action creates exactly one usage event, even under retries (deduplicated by idempotency key)
  - Evidence:
- [ ] A test proves double-counting cannot happen
  - Evidence:

## Quotas
- [ ] Usage is checked against the tenant's plan; requests over the limit are rejected
  - Evidence:
- [ ] Responses carry correct status codes (429 / 402) and a message explaining why
  - Evidence:

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
