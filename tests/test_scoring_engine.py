"""Unit tests for scoring.engine: NR rule, renormalization, grades, confidence.

Uses synthetic rows only — golden pins over the real census live in
tests/test_scoring_golden.py. The NR rule, grade bands, and confidence
rubric are research-locked (02-RESEARCH.md "Aggregation, NR, grades,
confidence").
"""
import json
import re

import pytest

from scoring import (
    DISCLAIMER,
    GRADE_BANDS,
    GRADE_DESCRIPTIONS,
    SCORE_VERSION,
    WEIGHTS,
    build_stats,
    grade_for,
    score_agent,
    serialize_components,
)

COMPONENT_NAMES = {
    "sales_volume_velocity",
    "review_signal_ratio",
    "rating_credibility",
    "price_vs_category",
    "listing_age_consistency",
}


def mk_row(
    sold=0,
    rating=None,
    positive_pct=None,
    price_usdt=None,
    category="Trading & Investing",
    first_seen="2026-07-10T00:00:00Z",
):
    return {
        "sold": sold,
        "rating": rating,
        "positive_pct": positive_pct,
        "price_usdt": price_usdt,
        "category": category,
        "first_seen": first_seen,
    }


STATS_ROWS = [
    mk_row(sold=25, rating=5.0, positive_pct=100.0, price_usdt=0.5),
    mk_row(sold=30, rating=4.8, positive_pct=95.0, price_usdt=1.0),
    mk_row(sold=60, rating=4.9, positive_pct=98.0, price_usdt=2.0),
    mk_row(sold=40, price_usdt=3.0),  # unrated with 20+ sales
    mk_row(price_usdt=4.0),
    mk_row(price_usdt=10.0),
]


@pytest.fixture(scope="module")
def stats():
    return build_stats(STATS_ROWS)


# --- envelope constants --------------------------------------------------------


def test_score_version_and_grade_bands():
    assert SCORE_VERSION == "1.0.0"
    assert GRADE_BANDS == (("A", 85), ("B", 70), ("C", 55), ("D", 40), ("F", 0))


def test_grade_for_band_edges():
    assert [grade_for(s) for s in (100, 85, 84, 70, 69, 55, 54, 40, 39, 0)] == [
        "A", "A", "B", "B", "C", "C", "D", "D", "F", "F",
    ]


BANNED = re.compile(r"(?i)(fraud|scam|fake|manipulat)")


def test_disclaimer_and_grade_descriptions_are_neutral():
    assert not BANNED.search(DISCLAIMER)
    assert set(GRADE_DESCRIPTIONS) == {"A", "B", "C", "D", "F", "NR"}
    for text in GRADE_DESCRIPTIONS.values():
        assert not BANNED.search(text)


# --- NR rule --------------------------------------------------------------------


def test_nr_rule_zero_evidence(stats):
    card = score_agent(mk_row(), stats, 1)
    assert (card["score"], card["grade"], card["confidence"]) == (None, "NR", "low")
    # NR is a successful response: all five components still rendered.
    assert set(card["components"]) == COMPONENT_NAMES
    for comp in card["components"].values():
        assert comp["reason"]


def test_nr_card_with_price_still_scores_c4(stats):
    card = score_agent(mk_row(price_usdt=2.0), stats, 1)
    assert card["grade"] == "NR"
    assert card["components"]["price_vs_category"]["score"] is not None


# --- aggregation / renormalization ------------------------------------------------


def test_renormalization_over_available_weight(stats):
    # Fully-populated v1 agent: C5 is always None -> exactly 4 scored
    # components renormalizing over total weight 0.90.
    card = score_agent(
        mk_row(sold=100, rating=4.8, positive_pct=95.0, price_usdt=2.0), stats, 1
    )
    scored = {k: c for k, c in card["components"].items() if c["score"] is not None}
    assert set(scored) == COMPONENT_NAMES - {"listing_age_consistency"}
    total_w = sum(WEIGHTS[k] for k in scored)
    assert total_w == pytest.approx(0.90)
    weighted = sum(WEIGHTS[k] * c["score"] for k, c in scored.items())
    assert card["score"] == round(weighted / total_w)


def test_single_component_agent_chainprobe_shape(stats):
    # sold=1, unrated, unpriced: only C1 scores — the floor of the scored
    # population (real agent 3117 ChainProbe has this shape).
    card = score_agent(mk_row(sold=1), stats, 1)
    scored = [k for k, c in card["components"].items() if c["score"] is not None]
    assert scored == ["sales_volume_velocity"]
    assert card["score"] == card["components"]["sales_volume_velocity"]["score"]
    assert card["confidence"] == "low"


# --- confidence rubric --------------------------------------------------------------


def test_confidence_high(stats):
    card = score_agent(
        mk_row(sold=100, rating=4.8, positive_pct=95.0, price_usdt=2.0), stats, 1
    )
    assert card["confidence"] == "high"


def test_confidence_medium_unrated_high_sales_coinank_shape(stats):
    # CoinAnk shape: huge volume, no rating, priced -> 3 scored components
    # (C1, C2 observation branch, C4) -> medium.
    card = score_agent(mk_row(sold=1370, price_usdt=2.0), stats, 1)
    scored = [k for k, c in card["components"].items() if c["score"] is not None]
    assert len(scored) == 3
    assert card["confidence"] == "medium"


def test_confidence_low_when_flagged(stats):
    card = score_agent(
        mk_row(sold=2, rating=5.0, positive_pct=100.0, price_usdt=2.0), stats, 1
    )
    assert card["components"]["rating_credibility"]["flagged"] is True
    assert card["confidence"] == "low"


def test_confidence_low_when_thin_sales(stats):
    card = score_agent(
        mk_row(sold=3, rating=4.0, positive_pct=80.0, price_usdt=2.0), stats, 1
    )
    assert card["confidence"] == "low"


def test_confidence_low_when_two_or_fewer_scored_despite_sales(stats):
    # sold=10 (>= LOW_CONF_SOLD), unrated, unpriced -> only C1 scores.
    card = score_agent(mk_row(sold=10), stats, 1)
    scored = [k for k, c in card["components"].items() if c["score"] is not None]
    assert len(scored) <= 2
    assert card["confidence"] == "low"


# --- sparse externally built stats -----------------------------------------------


def test_score_agent_priced_row_against_priceless_stats_does_not_crash():
    # WR-03 regression via the public API: score_agent documents no "stats
    # must contain a priced row" precondition, so a priced row scored against
    # externally built priceless stats must degrade C4 to insufficient data —
    # never ZeroDivisionError.
    priceless = build_stats([mk_row(sold=3), mk_row(sold=40, rating=4.0, positive_pct=90.0)])
    card = score_agent(
        mk_row(sold=10, rating=4.5, positive_pct=90.0, price_usdt=2.0), priceless, 1
    )
    c4 = card["components"]["price_vs_category"]
    assert c4["score"] is None
    assert c4["reason"] == "insufficient data — no priced agents available for comparison"
    assert card["score"] is not None  # remaining components still aggregate


# --- deterministic serialization ------------------------------------------------------


def test_serialize_components_byte_identical_and_canonical(stats):
    card = score_agent(
        mk_row(sold=100, rating=4.8, positive_pct=95.0, price_usdt=2.0), stats, 1
    )
    s1 = serialize_components(card["components"])
    s2 = serialize_components(card["components"])
    assert s1 == s2
    canonical = json.dumps(
        json.loads(s1), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert s1 == canonical


def test_same_row_scored_twice_is_identical(stats):
    row = mk_row(sold=60, rating=4.9, positive_pct=98.0, price_usdt=1.0)
    card_a = score_agent(row, stats, 1)
    card_b = score_agent(row, stats, 1)
    assert (card_a["score"], card_a["grade"], card_a["confidence"]) == (
        card_b["score"], card_b["grade"], card_b["confidence"],
    )
    assert serialize_components(card_a["components"]) == serialize_components(
        card_b["components"]
    )
