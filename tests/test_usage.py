"""Tests for token/cost accounting."""

from __future__ import annotations

from typedout import Usage, cost_of, price_for, register_price


def test_usage_addition():
    a = Usage(input_tokens=10, output_tokens=5, requests=1, cost_usd=0.001)
    b = Usage(input_tokens=20, output_tokens=8, requests=1, cost_usd=0.002)
    total = a + b
    assert total.input_tokens == 30
    assert total.output_tokens == 13
    assert total.requests == 2
    assert abs(total.cost_usd - 0.003) < 1e-9
    assert total.total_tokens == 43


def test_usage_is_immutable():
    u = Usage(input_tokens=1)
    try:
        u.input_tokens = 2  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("Usage should be frozen")


def test_cost_of_known_model():
    # gpt-4o-mini: $0.15 / $0.60 per 1M tokens
    cost = cost_of("gpt-4o-mini", 1_000_000, 1_000_000)
    assert abs(cost - 0.75) < 1e-9


def test_cost_of_unknown_model_is_zero():
    assert cost_of("totally-made-up-model", 1000, 1000) == 0.0


def test_price_prefix_match():
    # A dated alias resolves to its family price.
    assert price_for("claude-3-5-sonnet-20241022") == (3.00, 15.00)


def test_register_custom_price():
    register_price("my-local-llm", 0.0, 0.0)
    assert price_for("my-local-llm") == (0.0, 0.0)
    assert cost_of("my-local-llm", 5000, 5000) == 0.0


def test_usage_str_is_readable():
    s = str(Usage(input_tokens=100, output_tokens=50, requests=1, cost_usd=0.00042))
    assert "150 tok" in s and "$" in s
