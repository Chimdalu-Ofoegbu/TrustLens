"""Marketplace statistics built once per refresh and passed into scoring.

Stats is the pure, precomputed benchmark context for the five component
functions (research pattern: "Stats precomputed once per refresh, passed
in"). Building it from plain row mappings keeps every scoring function
free of I/O: callers fetch rows however they like, this module reduces
them to price pools and the rating-display base rate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

RATING_EXPECTED_SALES = 20   # sales level at which a displayed rating is the marketplace norm


@dataclass(frozen=True)
class Stats:
    """Benchmark pools and the rating-display base rate for one snapshot."""

    category_pools: dict[str, tuple[float, ...]]  # priced agents per category, sorted ascending
    market_pool: tuple[float, ...]                # all priced agents, sorted ascending
    rated_hi: int             # agents with sold >= RATING_EXPECTED_SALES displaying a rating
    total_hi: int             # agents with sold >= RATING_EXPECTED_SALES
    rating_display_pct: int   # round(100 * rated_hi / total_hi); 0 when total_hi == 0


def build_stats(rows: Iterable[Mapping]) -> Stats:
    """Reduce agent rows to benchmark pools and the rating-display base rate.

    Pools include only rows whose price_usdt is not None — an identity
    check, because 0.0 is a real listed price (8 real census rows), never
    a missing value. On the real census this yields rated_hi=20,
    total_hi=23, rating_display_pct=87.
    """
    by_category: dict[str, list[float]] = {}
    market: list[float] = []
    rated_hi = 0
    total_hi = 0
    for row in rows:
        price = row["price_usdt"]
        if price is not None:
            by_category.setdefault(row["category"], []).append(price)
            market.append(price)
        if row["sold"] >= RATING_EXPECTED_SALES:
            total_hi += 1
            if row["rating"] is not None:
                rated_hi += 1
    rating_display_pct = round(100 * rated_hi / total_hi) if total_hi else 0
    return Stats(
        category_pools={cat: tuple(sorted(pool)) for cat, pool in by_category.items()},
        market_pool=tuple(sorted(market)),
        rated_hi=rated_hi,
        total_hi=total_hi,
        rating_display_pct=rating_display_pct,
    )
