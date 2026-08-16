from app.pricing import (
    PRICE_PER_API_CALL_MICRO_DOLLARS,
    PRICE_PER_MILLION_TOKENS_MICRO_DOLLARS,
    calculate_ai_token_cost_micro_dollars,
    calculate_api_call_cost_micro_dollars,
    calculate_event_cost_micro_dollars,
    micro_dollars_to_display,
)


def test_pure_input_tokens_priced_at_input_rate():
    cost = calculate_ai_token_cost_micro_dollars(
        input_tokens=1_000_000, cached_input_tokens=0, output_tokens=0, reasoning_tokens=0
    )
    assert cost == PRICE_PER_MILLION_TOKENS_MICRO_DOLLARS["input"] == 150_000


def test_cached_input_tokens_are_cheaper_than_fresh_input():
    fresh_cost = calculate_ai_token_cost_micro_dollars(1_000_000, 0, 0, 0)
    cached_cost = calculate_ai_token_cost_micro_dollars(0, 1_000_000, 0, 0)
    assert cached_cost < fresh_cost
    assert cached_cost == PRICE_PER_MILLION_TOKENS_MICRO_DOLLARS["cached_input"] == 30_000


def test_reasoning_tokens_are_billed_at_the_output_rate():
    """Reasoning tokens are not free and not a separate rate — they cost the same as output."""
    output_cost = calculate_ai_token_cost_micro_dollars(0, 0, 1_000_000, 0)
    reasoning_cost = calculate_ai_token_cost_micro_dollars(0, 0, 0, 1_000_000)
    assert output_cost == reasoning_cost == PRICE_PER_MILLION_TOKENS_MICRO_DOLLARS["output"] == 600_000


def test_reasoning_and_output_tokens_combine_additively_at_the_same_rate():
    combined = calculate_ai_token_cost_micro_dollars(0, 0, 500_000, 500_000)
    single = calculate_ai_token_cost_micro_dollars(0, 0, 1_000_000, 0)
    assert combined == single


def test_mixed_categories_are_priced_independently_not_flattened():
    """
    The pinned regression case: 500k of each of input, cached_input, output,
    and reasoning tokens. If categories were (incorrectly) summed and priced
    at one flat rate, this would NOT equal the sum of each category priced
    separately. Pin the exact expected total.
    """
    cost = calculate_ai_token_cost_micro_dollars(
        input_tokens=500_000,
        cached_input_tokens=500_000,
        output_tokens=500_000,
        reasoning_tokens=500_000,
    )
    expected = (
        500_000 * PRICE_PER_MILLION_TOKENS_MICRO_DOLLARS["input"]
        + 500_000 * PRICE_PER_MILLION_TOKENS_MICRO_DOLLARS["cached_input"]
        + 1_000_000 * PRICE_PER_MILLION_TOKENS_MICRO_DOLLARS["output"]  # output + reasoning combined
    ) // 1_000_000
    assert cost == expected == 690_000


def test_zero_tokens_cost_zero():
    assert calculate_ai_token_cost_micro_dollars(0, 0, 0, 0) == 0


def test_api_call_cost_is_flat_rate_per_call():
    assert calculate_api_call_cost_micro_dollars(1) == PRICE_PER_API_CALL_MICRO_DOLLARS
    assert calculate_api_call_cost_micro_dollars(1000) == 1000 * PRICE_PER_API_CALL_MICRO_DOLLARS


def test_event_cost_dispatches_by_usage_type():
    api_cost = calculate_event_cost_micro_dollars("api_call", 500, metadata=None)
    assert api_cost == 500 * PRICE_PER_API_CALL_MICRO_DOLLARS

    token_cost = calculate_event_cost_micro_dollars(
        "ai_tokens",
        quantity=1_000_000,  # ignored for ai_tokens — cost comes from metadata breakdown
        metadata={"input_tokens": 1_000_000, "cached_input_tokens": 0, "output_tokens": 0},
    )
    assert token_cost == PRICE_PER_MILLION_TOKENS_MICRO_DOLLARS["input"]


def test_event_cost_missing_metadata_defaults_to_zero_tokens():
    cost = calculate_event_cost_micro_dollars("ai_tokens", quantity=100, metadata=None)
    assert cost == 0


def test_micro_dollars_to_display_formats_as_dollars():
    assert micro_dollars_to_display(150_000) == "$0.150000"
    assert micro_dollars_to_display(0) == "$0.000000"
    assert micro_dollars_to_display(1_000_000) == "$1.000000"
