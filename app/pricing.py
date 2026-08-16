"""
Token & call pricing — pinned constants, integer money math throughout.

Money is represented in MICRO-DOLLARS (1,000,000 micro-dollars = $1) as a
plain int, never a float, so rounding error can't compound across millions
of usage events.

Token categories cannot simply be summed and priced at one flat rate:
  - cached input tokens are billed CHEAPER than fresh input tokens
  - reasoning tokens are billed at the OUTPUT rate, not a separate rate,
    and not for free
  - input, cached input, and output are three genuinely different prices,
    and mixing them into a single total loses the distinction that matters
"""
import json

from sqlmodel import Session, select

from app.models import UsageEvent
from app.time_utils import month_start

# Price per 1,000,000 tokens, in micro-dollars. Pinned — change here, not inline,
# and every change here should be covered by tests/test_pricing.py.
PRICE_PER_MILLION_TOKENS_MICRO_DOLLARS = {
    "input": 150_000,        # $0.15 / 1M input tokens
    "cached_input": 30_000,  # $0.03 / 1M cached input tokens — 5x cheaper than fresh input
    "output": 600_000,       # $0.60 / 1M output tokens — reasoning tokens are billed at this rate too
}

# Flat cost per metered API call, in micro-dollars.
PRICE_PER_API_CALL_MICRO_DOLLARS = 100  # $0.0001 / call


def calculate_ai_token_cost_micro_dollars(
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int = 0,
) -> int:
    """
    Reasoning ("thinking") tokens count as output tokens for pricing — some
    model providers bill hidden reasoning tokens at the output rate, not as
    a separate free or discounted category. Categories are priced
    independently and only summed at the end, never averaged or flattened.
    """
    billable_output_tokens = output_tokens + reasoning_tokens

    cost = (
        input_tokens * PRICE_PER_MILLION_TOKENS_MICRO_DOLLARS["input"]
        + cached_input_tokens * PRICE_PER_MILLION_TOKENS_MICRO_DOLLARS["cached_input"]
        + billable_output_tokens * PRICE_PER_MILLION_TOKENS_MICRO_DOLLARS["output"]
    ) // 1_000_000

    return cost


def calculate_api_call_cost_micro_dollars(call_count: int) -> int:
    return call_count * PRICE_PER_API_CALL_MICRO_DOLLARS


def calculate_event_cost_micro_dollars(usage_type: str, quantity: int, metadata: dict | None) -> int:
    """Cost for one usage event, dispatched by type. `metadata` holds the token breakdown for ai_tokens."""
    if usage_type == "ai_tokens":
        meta = metadata or {}
        return calculate_ai_token_cost_micro_dollars(
            meta.get("input_tokens", 0),
            meta.get("cached_input_tokens", 0),
            meta.get("output_tokens", 0),
            meta.get("reasoning_tokens", 0),
        )
    return calculate_api_call_cost_micro_dollars(quantity)


def rollup_cost_micro_dollars(session: Session, tenant_id: int) -> int:
    """Total cost across all of a tenant's usage events for the current calendar month."""
    since = month_start()
    events = session.exec(
        select(UsageEvent).where(UsageEvent.tenant_id == tenant_id, UsageEvent.created_at >= since)
    ).all()

    total = 0
    for event in events:
        metadata = json.loads(event.metadata_json) if event.metadata_json else None
        total += calculate_event_cost_micro_dollars(event.type, event.quantity, metadata)
    return total


def micro_dollars_to_display(micro_dollars: int) -> str:
    """Format micro-dollars as a human-readable dollar string, e.g. '$0.780000'."""
    return f"${micro_dollars / 1_000_000:.6f}"
