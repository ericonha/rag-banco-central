"""Token cost estimate. Prices come from settings (USD per million tokens)."""
from __future__ import annotations


def compute_cost(
    tokens_in: int | None,
    tokens_out: int | None,
    price_in_per_mtok: float,
    price_out_per_mtok: float,
) -> float | None:
    """Cost in USD, or None when usage or prices are unknown."""
    if tokens_in is None or tokens_out is None:
        return None
    if price_in_per_mtok <= 0 and price_out_per_mtok <= 0:
        return None
    cost = (tokens_in * price_in_per_mtok + tokens_out * price_out_per_mtok) / 1_000_000
    return round(cost, 6)
