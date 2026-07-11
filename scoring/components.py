"""Five pure TrustScore component functions with frozen constants and templates.

Every component returns the SAME frozen dict shape:

    {"score": int | None, "weight": float, "observed": ..., "benchmark": ...,
     "flagged": bool, "reason": str}

- ``score: None`` is the explicit insufficient-data state — a number is
  never fabricated for missing evidence.
- ``flagged`` is False everywhere except the rating-credibility
  thin-perfect case (brief verbatim: "5.0 with <5 sales = low confidence,
  flagged not accused").
- Reason strings are fixed TEMPLATES interpolating numbers and canonical
  category bucket names ONLY (enforced against CANONICAL_CATEGORIES).
  Agent names, taglines, or any other listing text NEVER enter a
  template: listing text is attacker-influenceable, and outward wording
  about named vendors is a defamation surface, not a style choice.
- All checks on rating/positive_pct/price_usdt use ``is None`` identity —
  never truthiness — because 0.0 is real data for each of those fields.

Constants are research-locked (02-RESEARCH.md, dry-run verified over all
272 real agents). Do not tune them without bumping the score version.
"""
from __future__ import annotations

import math

from indexer.category import CATEGORIES
from scoring.stats import RATING_EXPECTED_SALES, Stats

SOLD_REF = 500          # volume log anchor: >= 500 units -> 100
SUPPORT_REF = 50        # rating-support anchor: >= 50 units -> full support
THIN_SALES = 5          # brief: "5.0 with <5 sales = low confidence"
CRED_FLOOR = 0.30       # thin evidence -> neutral-low credibility, never punitive-zero
MIN_CATEGORY_PRICED = 5  # below this, price percentile falls back to marketplace pool
PRICE_DEV_SPAN = 45     # price subscore = 100 - 45 * deviation (range 55..100)
# Reason templates may interpolate ONLY these fixed bucket names (single
# source of truth: indexer.category, a pure module — no I/O, no wall clock).
# Any other category value — e.g. a Phase 5 'listed' category scraped from a
# marketplace page — is listing-influenced text and must never render into
# outward reason text.
CANONICAL_CATEGORIES = frozenset(CATEGORIES)
WEIGHTS = {
    "sales_volume_velocity": 0.30,
    "review_signal_ratio":   0.20,
    "rating_credibility":    0.25,
    "price_vs_category":     0.15,
    "listing_age_consistency": 0.10,
}


def log_scale(value: float, ref: float) -> float:
    """0 at value=0, 1.0 at value>=ref, log-shaped between."""
    return min(1.0, math.log10(1 + value) / math.log10(1 + ref))


def percentile(pool, value: float) -> float:
    """pool sorted ascending; self-inclusive mid-rank; deterministic under ties."""
    less = sum(1 for x in pool if x < value)
    equal = sum(1 for x in pool if x == value)
    return (less + 0.5 * equal) / len(pool)


def fmt_price(p: float) -> str:
    """Fixed-decimal, never scientific: 1.5e-05 -> '0.000015', 0.0 -> '0'."""
    return f"{p:.8f}".rstrip("0").rstrip(".")


def _median(pool) -> float:
    """pool sorted ascending, non-empty; even length averages the two middles."""
    n, mid = len(pool), len(pool) // 2
    return pool[mid] if n % 2 else (pool[mid - 1] + pool[mid]) / 2


def c_sales_volume_velocity(sold: int, distinct_snapshots: int) -> dict:
    """Sales volume on a log anchor; velocity is a documented v2 seam.

    Velocity design for >= 2 distinct snapshots (v2 data): blend a
    sold-delta-per-day term into the volume score. Intentionally NOT
    implemented in this score version — every current agent has exactly
    one distinct captured_at, so only the degradation notes are reachable.
    """
    score = round(100 * log_scale(sold, SOLD_REF))
    if distinct_snapshots < 2:
        note = "; sales velocity unavailable — insufficient history (single snapshot)"
    else:
        note = "; sales velocity not computed in this score version"
    if sold == 0:
        reason = "no completed sales observed in the snapshot" + note
    else:
        reason = f"{sold} unit(s) sold (volume scale tops out at 500+)" + note
    return {
        "score": score,
        "weight": WEIGHTS["sales_volume_velocity"],
        "observed": sold,
        "benchmark": SOLD_REF,
        "flagged": False,
        "reason": reason,
    }


def c_review_signal_ratio(
    rating: float | None, positive_pct: float | None, sold: int, stats: Stats
) -> dict:
    """Observed review signal vs the signal expected at this sales volume.

    The census carries no review counts; rating presence, positive_pct and
    sold are the only review evidence. Branch order is frozen: the
    None-positive_pct check precedes the thin-sales check (real case:
    id 2169 is rated with no displayed positive share).
    """
    benchmark = None
    if rating is not None and positive_pct is None:
        score = 70
        reason = (
            f"rating displayed; positive-review share not shown on the listing ({sold} sales)"
        )
    elif rating is not None and sold < THIN_SALES:
        score = min(round(40 + 60 * positive_pct / 100), 65)
        reason = (
            f"rating displayed with {positive_pct:g}% positive on only {sold} sale(s)"
            " — limited volume behind the review signal"
        )
    elif rating is not None:
        score = round(40 + 60 * positive_pct / 100)
        reason = f"rating displayed with {positive_pct:g}% positive across {sold} sales"
    elif sold >= RATING_EXPECTED_SALES:
        score = 35
        benchmark = stats.rating_display_pct
        reason = (
            f"no displayed rating despite {sold} units sold — "
            f"{stats.rating_display_pct}% of agents with 20+ sales display one "
            f"({stats.rated_hi} of {stats.total_hi})"
        )
    else:
        score = None
        reason = f"insufficient data — no displayed rating and only {sold} sale(s)"
    return {
        "score": score,
        "weight": WEIGHTS["review_signal_ratio"],
        "observed": positive_pct,
        "benchmark": benchmark,
        "flagged": False,
        "reason": reason,
    }


def c_rating_credibility(rating: float | None, sold: int) -> dict:
    """Displayed rating discounted by log sales support, floored at CRED_FLOOR.

    The CRED_FLOOR exists because the floorless v1 formula ranked a rated
    agent below an identical unrated one — thin evidence must floor near
    "no information", never near punitive zero. The flag, not the
    subscore, carries the thin-data warning. Do not remove the floor.
    """
    if rating is None:
        return {
            "score": None,
            "weight": WEIGHTS["rating_credibility"],
            "observed": None,
            "benchmark": 5.0,
            "flagged": False,
            "reason": "insufficient data — no rating displayed to evaluate",
        }
    support = log_scale(sold, SUPPORT_REF)
    score = round(100 * (rating / 5.0) * (CRED_FLOOR + (1 - CRED_FLOOR) * support))
    flagged = rating == 5.0 and sold < THIN_SALES
    if flagged:
        reason = (
            f"perfect 5.0 rating backed by only {sold} sale(s) — pattern consistent with "
            "limited review history; low confidence, flagged for thin data "
            "(not an assessment of conduct)"
        )
    elif sold >= SUPPORT_REF:
        reason = f"{rating:g}/5 rating supported by {sold} sales"
    else:
        reason = f"{rating:g}/5 rating with moderate volume behind it ({sold} sale(s))"
    return {
        "score": score,
        "weight": WEIGHTS["rating_credibility"],
        "observed": rating,
        "benchmark": 5.0,
        "flagged": flagged,
        "reason": reason,
    }


def c_price_vs_category(price_usdt: float | None, category: str, stats: Stats) -> dict:
    """Price percentile within the category pool (marketplace fallback).

    Price extremity is an observation, never a heavy penalty: the score
    spans [55, 100] by construction. Categories with fewer than
    MIN_CATEGORY_PRICED priced agents fall back to the marketplace pool
    (real trigger: "Other Services", 3 priced), as does any category
    outside CANONICAL_CATEGORIES — only the fixed bucket vocabulary may
    render into reason text, never an arbitrary category string.

    Stats need not contain any priced row: if the marketplace pool is
    also empty, the component degrades to the explicit insufficient-data
    state instead of dividing by zero (unreachable via compute_all, which
    builds stats from the same rows it scores, but score_agent and this
    function are public API accepting externally built stats).
    """
    if price_usdt is None:
        return {
            "score": None,
            "weight": WEIGHTS["price_vs_category"],
            "observed": None,
            "benchmark": None,
            "flagged": False,
            "reason": "insufficient data — no listed price to compare against category",
        }
    pool = stats.category_pools.get(category, ())
    label = category
    if category not in CANONICAL_CATEGORIES or len(pool) < MIN_CATEGORY_PRICED:
        pool = stats.market_pool
        label = "marketplace"  # never render text outside the fixed vocabulary
    if not pool:
        return {
            "score": None,
            "weight": WEIGHTS["price_vs_category"],
            "observed": price_usdt,
            "benchmark": None,
            "flagged": False,
            "reason": "insufficient data — no priced agents available for comparison",
        }
    p = percentile(pool, price_usdt)
    deviation = abs(p - 0.5) * 2
    score = round(100 - PRICE_DEV_SPAN * deviation)
    fp = fmt_price(price_usdt)
    med = _median(pool)
    fm = fmt_price(med)
    pp = round(p * 100)
    n = len(pool)
    if deviation <= 0.5:
        reason = (
            f"price {fp} USDT within {label} norm "
            f"(P{pp} among {n} priced agents; median {fm} USDT)"
        )
    else:
        direction = "below" if p < 0.5 else "above"
        reason = (
            f"price {fp} USDT {direction} {label} norm "
            f"({fp} vs median {fm} USDT, P{pp} among {n})"
        )
    return {
        "score": score,
        "weight": WEIGHTS["price_vs_category"],
        "observed": price_usdt,
        "benchmark": round(med, 6),
        "flagged": False,
        "reason": reason,
    }


def c_listing_age_consistency(first_seen: str, distinct_snapshots: int) -> dict:
    """Listing age/consistency — always insufficient in this score version.

    Design seam for >= 2 distinct snapshots (v2 data): age = days between
    min/max captured_at on a log anchor; consistency = penalize field
    regressions across snapshots. Formulas intentionally NOT implemented —
    all 272 current agents have exactly one distinct captured_at, and
    history must never be fabricated.
    """
    if distinct_snapshots < 2:
        reason = (
            "insufficient history — listing observed in a single snapshot "
            f"({first_seen[:10]}); age and consistency not yet measurable"
        )
    else:
        reason = (
            "insufficient history — age and consistency not computed in this score version"
        )
    return {
        "score": None,
        "weight": WEIGHTS["listing_age_consistency"],
        "observed": distinct_snapshots,
        "benchmark": 2,
        "flagged": False,
        "reason": reason,
    }
