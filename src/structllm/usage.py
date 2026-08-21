"""Token and cost accounting.

``Usage`` is an immutable value object that adds up across calls, so an engine can
report both the cost of a single ``extract`` (including its retries) and a running
total for the whole session.

Prices are expressed in USD per one million tokens and are **illustrative
defaults** — they change often. Override them at runtime with
:func:`register_price` or pass your own numbers; nothing here calls the network.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional, Tuple

# (input_price, output_price) in USD per 1,000,000 tokens. Approximate; configurable.
_PRICES: Dict[str, Tuple[float, float]] = {
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-opus": (15.00, 75.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "mock-echo-1": (0.00, 0.00),
}


def register_price(model: str, input_per_mtok: float, output_per_mtok: float) -> None:
    """Register or override the price (USD per 1M tokens) for a model id."""
    _PRICES[model] = (float(input_per_mtok), float(output_per_mtok))


def price_for(model: str) -> Optional[Tuple[float, float]]:
    """Return ``(input, output)`` price per 1M tokens for *model*, or ``None``.

    Matching is exact first, then by longest known prefix so that dated aliases
    such as ``claude-3-5-sonnet-20241022`` resolve to their family price.
    """
    if model in _PRICES:
        return _PRICES[model]
    best: Optional[str] = None
    for key in _PRICES:
        if model.startswith(key) and (best is None or len(key) > len(best)):
            best = key
    return _PRICES[best] if best else None


def cost_of(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute the USD cost of a call, or ``0.0`` when the model price is unknown."""
    price = price_for(model)
    if price is None:
        return 0.0
    in_rate, out_rate = price
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


@dataclass(frozen=True)
class Usage:
    """Immutable tally of tokens, requests and cost. Add instances with ``+``."""

    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "Usage") -> "Usage":
        if not isinstance(other, Usage):
            return NotImplemented
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            requests=self.requests + other.requests,
            cost_usd=self.cost_usd + other.cost_usd,
        )

    def with_cost(self, cost_usd: float) -> "Usage":
        return replace(self, cost_usd=cost_usd)

    def __str__(self) -> str:
        return (
            f"{self.requests} req · "
            f"{self.input_tokens} in + {self.output_tokens} out = "
            f"{self.total_tokens} tok · ${self.cost_usd:.6f}"
        )
