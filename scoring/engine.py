"""Aggregation engine: NR rule, weighted renormalization, grades, confidence.

score_agent is pure — no I/O, no wall clock. Determinism guarantees:
half-even built-in round() everywhere, json.dumps with sorted keys and
fixed separators, and no set/dict iteration feeding any output ordering.
Constants are research-locked (02-RESEARCH.md); any formula, weight, or
band change bumps SCORE_VERSION.
"""
from __future__ import annotations

import json
from typing import Mapping

from scoring.components import (
    WEIGHTS,
    c_listing_age_consistency,
    c_price_vs_category,
    c_rating_credibility,
    c_review_signal_ratio,
    c_sales_volume_velocity,
)
from scoring.stats import Stats

SCORE_VERSION = "1.0.0"
GRADE_BANDS = (("A", 85), ("B", 70), ("C", 55), ("D", 40), ("F", 0))  # first match, score >= cut
HIGH_CONF_SOLD = 50
LOW_CONF_SOLD = 5
DISCLAIMER = (
    "TrustScore is a statistical estimate computed from public marketplace "
    "data as of the stated snapshot; it is not a statement of fact about any "
    "vendor or agent."
)
GRADE_DESCRIPTIONS = {
    "A": "high sales volume with a strong, well-supported displayed rating",
    "B": "solid sales volume with a strong rating, or exceptional volume without a displayed rating",
    "C": "modest sales volume with a displayed rating",
    "D": "thin evidence — limited sales or limited review signal behind the listing",
    "F": "minimal evidence or negative review signals in the observed data",
    "NR": "not rated — no transaction or review evidence observed yet",
}


def grade_for(score: int) -> str:
    return next(g for g, lo in GRADE_BANDS if score >= lo)


def serialize_components(components: dict) -> str:
    return json.dumps(components, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def score_agent(row: Mapping, stats: Stats, distinct_snapshots: int) -> dict:
    """Pure: no I/O, no wall clock. row needs keys category, sold, rating,
    positive_pct, price_usdt, first_seen."""
    sold, rating = row["sold"], row["rating"]
    components = {
        "sales_volume_velocity": c_sales_volume_velocity(sold, distinct_snapshots),
        "review_signal_ratio": c_review_signal_ratio(rating, row["positive_pct"], sold, stats),
        "rating_credibility": c_rating_credibility(rating, sold),
        "price_vs_category": c_price_vs_category(row["price_usdt"], row["category"], stats),
        "listing_age_consistency": c_listing_age_consistency(row["first_seen"], distinct_snapshots),
    }
    # NR rule (verbatim, research-locked): zero transaction evidence AND zero
    # review evidence -> honest not-rated state; components still rendered.
    if sold == 0 and rating is None:
        return {"score": None, "grade": "NR", "confidence": "low", "components": components}
    scored = {k: c for k, c in components.items() if c["score"] is not None}
    total_w = sum(WEIGHTS[k] for k in scored)  # renormalize over available evidence
    score = round(sum(WEIGHTS[k] * c["score"] for k, c in scored.items()) / total_w)
    grade = grade_for(score)
    flagged = components["rating_credibility"]["flagged"]
    if flagged or sold < LOW_CONF_SOLD or len(scored) <= 2:
        confidence = "low"
    elif len(scored) >= 4 and sold >= HIGH_CONF_SOLD and rating is not None:
        confidence = "high"
    else:
        confidence = "medium"
    return {"score": score, "grade": grade, "confidence": confidence, "components": components}
