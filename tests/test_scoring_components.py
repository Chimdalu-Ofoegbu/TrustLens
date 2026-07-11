"""Unit tests for scoring.stats and scoring.components.

Anchor values and reason templates are VERBATIM from 02-RESEARCH.md ("The
Empirical Formula Specification (v2 - dry-run verified)"). They pin the
research-locked formulas: if an anchor fails, the implementation
transcription is wrong - fix the code, never the anchor.
"""
import pytest

from indexer.category import CATEGORIES
from scoring.components import (
    CANONICAL_CATEGORIES,
    CRED_FLOOR,
    MIN_CATEGORY_PRICED,
    PRICE_DEV_SPAN,
    SOLD_REF,
    SUPPORT_REF,
    THIN_SALES,
    WEIGHTS,
    c_listing_age_consistency,
    c_price_vs_category,
    c_rating_credibility,
    c_review_signal_ratio,
    c_sales_volume_velocity,
    fmt_price,
    log_scale,
    percentile,
)
from scoring.stats import RATING_EXPECTED_SALES, Stats, build_stats

# Stats stub carrying the real-census base rate (research-verified: 20 of 23
# agents with >= 20 sales display a rating -> 87%).
STATS_STUB = Stats(
    category_pools={},
    market_pool=(),
    rated_hi=20,
    total_hi=23,
    rating_display_pct=87,
)

CAT = "Market Data & Analytics"
POOL_STATS = Stats(
    category_pools={
        CAT: (1.0, 2.0, 3.0, 4.0, 5.0),  # exactly MIN_CATEGORY_PRICED entries
        "Other Services": (1.0, 2.0, 3.0),  # under the bar -> marketplace fallback
    },
    market_pool=(0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0),
    rated_hi=0,
    total_hi=0,
    rating_display_pct=0,
)


# --- frozen constants --------------------------------------------------------


def test_constants_are_the_research_locked_values():
    assert (SOLD_REF, SUPPORT_REF, THIN_SALES) == (500, 50, 5)
    assert CRED_FLOOR == 0.30
    assert (MIN_CATEGORY_PRICED, PRICE_DEV_SPAN) == (5, 45)
    assert RATING_EXPECTED_SALES == 20


def test_weights_are_locked_and_sum_to_one():
    assert WEIGHTS == {
        "sales_volume_velocity": 0.30,
        "review_signal_ratio": 0.20,
        "rating_credibility": 0.25,
        "price_vs_category": 0.15,
        "listing_age_consistency": 0.10,
    }
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


# --- helpers ------------------------------------------------------------------


def test_log_scale_bounds():
    assert log_scale(0, 500) == 0.0
    assert log_scale(500, 500) == 1.0
    assert log_scale(10_000, 500) == 1.0  # capped at the anchor


def test_percentile_mid_rank_is_deterministic_under_ties():
    assert percentile((1.0, 1.0, 1.0), 1.0) == 0.5


def test_percentile_extremes_and_median_position():
    pool = (1.0, 2.0, 3.0, 4.0, 5.0)
    assert percentile(pool, 0.5) == 0.0
    assert percentile(pool, 10.0) == 1.0
    assert percentile(pool, 3.0) == 0.5


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.5e-05, "0.000015"),  # never scientific notation (real price of id 2023)
        (0.0, "0"),
        (0.002, "0.002"),
        (1.0, "1"),
        (0.1, "0.1"),
    ],
)
def test_fmt_price_fixed_decimal(value, expected):
    assert fmt_price(value) == expected


# --- C1 sales_volume_velocity -------------------------------------------------

C1_ANCHORS = [
    (0, 0),
    (1, 11),
    (2, 18),
    (9, 37),
    (25, 52),
    (98, 74),
    (175, 83),
    (371, 95),
    (500, 100),
    (1550, 100),
]


@pytest.mark.parametrize(("sold", "expected"), C1_ANCHORS)
def test_c1_anchor_scores(sold, expected):
    comp = c_sales_volume_velocity(sold, 1)
    assert comp["score"] == expected
    assert comp["weight"] == WEIGHTS["sales_volume_velocity"]
    assert comp["observed"] == sold
    assert comp["benchmark"] == SOLD_REF
    assert comp["flagged"] is False


def test_c1_zero_sales_reason_single_snapshot():
    comp = c_sales_volume_velocity(0, 1)
    assert comp["reason"] == (
        "no completed sales observed in the snapshot"
        "; sales velocity unavailable — insufficient history (single snapshot)"
    )


def test_c1_sold_reason_with_multi_snapshot_note():
    comp = c_sales_volume_velocity(9, 2)
    assert comp["reason"] == (
        "9 unit(s) sold (volume scale tops out at 500+)"
        "; sales velocity not computed in this score version"
    )


# --- C2 review_signal_ratio ----------------------------------------------------


def test_c2_rated_with_null_pct_precedes_thin_check():
    # Branch order is frozen: the None-pct check comes before the thin check.
    # Synthetic shape: rated, positive_pct None, sold 1 -> 70 (not the 65 cap).
    comp = c_review_signal_ratio(5.0, None, 1, STATS_STUB)
    assert comp["score"] == 70
    assert comp["reason"] == (
        "rating displayed; positive-review share not shown on the listing (1 sales)"
    )
    assert comp["benchmark"] is None


def test_c2_zero_positive_pct_is_a_value_not_none():
    # positive_pct 0.0 is real data (3 census rows) - must hit the thin branch.
    comp = c_review_signal_ratio(2.0, 0.0, 1, STATS_STUB)
    assert comp["score"] == 40  # min(round(40 + 0), 65)
    assert comp["observed"] == 0.0


def test_c2_thin_sales_cap_at_65():
    comp = c_review_signal_ratio(5.0, 100.0, 2, STATS_STUB)
    assert comp["score"] == 65
    assert comp["reason"] == (
        "rating displayed with 100% positive on only 2 sale(s)"
        " — limited volume behind the review signal"
    )


def test_c2_no_cap_at_thin_sales_boundary():
    comp = c_review_signal_ratio(5.0, 100.0, 5, STATS_STUB)
    assert comp["score"] == 100


def test_c2_full_volume_branch():
    comp = c_review_signal_ratio(4.9, 92.86, 547, STATS_STUB)
    assert comp["score"] == 96  # round(40 + 60 * 92.86 / 100), research anchor
    assert comp["reason"] == "rating displayed with 92.86% positive across 547 sales"


def test_c2_unrated_high_sales_renders_base_rate_exactly():
    comp = c_review_signal_ratio(None, None, 1370, STATS_STUB)
    assert comp["score"] == 35
    assert comp["benchmark"] == 87
    assert comp["reason"] == (
        "no displayed rating despite 1370 units sold — "
        "87% of agents with 20+ sales display one (20 of 23)"
    )


def test_c2_unrated_low_sales_is_insufficient():
    comp = c_review_signal_ratio(None, None, 3, STATS_STUB)
    assert comp["score"] is None
    assert comp["reason"] == "insufficient data — no displayed rating and only 3 sale(s)"


# --- C3 rating_credibility ------------------------------------------------------

C3_ANCHORS = [
    (5.0, 1550, 100, False),
    (4.9, 547, 98, False),
    (5.0, 2, 50, True),
    (5.0, 1, 42, True),
    (2.0, 1, 17, False),
    (5.0, 0, 30, True),
]


@pytest.mark.parametrize(("rating", "sold", "score", "flagged"), C3_ANCHORS)
def test_c3_anchor_scores_and_flags(rating, sold, score, flagged):
    comp = c_rating_credibility(rating, sold)
    assert (comp["score"], comp["flagged"]) == (score, flagged)
    assert comp["observed"] == rating
    assert comp["benchmark"] == 5.0


def test_c3_unrated_is_insufficient_not_zero():
    comp = c_rating_credibility(None, 100)
    assert comp["score"] is None
    assert comp["flagged"] is False
    assert comp["reason"] == "insufficient data — no rating displayed to evaluate"


def test_c3_flagged_reason_is_neutral_never_accusatory():
    comp = c_rating_credibility(5.0, 2)
    assert comp["reason"] == (
        "perfect 5.0 rating backed by only 2 sale(s) — pattern consistent with "
        "limited review history; low confidence, flagged for thin data "
        "(not an assessment of conduct)"
    )
    assert "not an assessment of conduct" in comp["reason"]


def test_c3_supported_reason():
    comp = c_rating_credibility(5.0, 1550)
    assert comp["reason"] == "5/5 rating supported by 1550 sales"


def test_c3_moderate_volume_reason():
    comp = c_rating_credibility(4.5, 10)
    assert comp["reason"] == "4.5/5 rating with moderate volume behind it (10 sale(s))"


# --- C4 price_vs_category -------------------------------------------------------


def test_c4_price_none_is_insufficient():
    comp = c_price_vs_category(None, CAT, POOL_STATS)
    assert comp["score"] is None
    assert comp["benchmark"] is None
    assert comp["reason"] == (
        "insufficient data — no listed price to compare against category"
    )


def test_c4_zero_price_scores_it_is_a_real_price():
    comp = c_price_vs_category(0.0, CAT, POOL_STATS)
    assert comp["score"] is not None  # 8 real census rows list 0.00 USDT


def test_c4_within_norm_at_median():
    comp = c_price_vs_category(3.0, CAT, POOL_STATS)
    assert comp["score"] == 100
    assert comp["reason"] == (
        "price 3 USDT within Market Data & Analytics norm "
        "(P50 among 5 priced agents; median 3 USDT)"
    )
    assert comp["benchmark"] == 3.0
    assert comp["observed"] == 3.0


def test_c4_below_norm():
    comp = c_price_vs_category(0.5, CAT, POOL_STATS)
    assert comp["score"] == 55  # deviation 1.0 -> 100 - 45
    assert comp["reason"] == (
        "price 0.5 USDT below Market Data & Analytics norm "
        "(0.5 vs median 3 USDT, P0 among 5)"
    )


def test_c4_above_norm():
    comp = c_price_vs_category(50.0, CAT, POOL_STATS)
    assert comp["score"] == 55
    assert comp["reason"] == (
        "price 50 USDT above Market Data & Analytics norm "
        "(50 vs median 3 USDT, P100 among 5)"
    )


def test_c4_small_category_falls_back_to_marketplace_pool():
    # "Other Services" has 3 priced (< MIN_CATEGORY_PRICED) -> marketplace pool.
    comp = c_price_vs_category(2.0, "Other Services", POOL_STATS)
    assert "marketplace norm" in comp["reason"]
    assert comp["benchmark"] == 3.0  # marketplace median, not the category's


def test_c4_missing_category_key_falls_back_to_marketplace_pool():
    comp = c_price_vs_category(2.0, "Trading & Investing", POOL_STATS)
    assert "marketplace norm" in comp["reason"]


def test_c4_canonical_set_is_the_nine_derived_buckets():
    # Single source of truth: the reason-text allowlist IS indexer.category's
    # bucket list — the "9 fixed category names" mitigation, enforced.
    assert CANONICAL_CATEGORIES == frozenset(CATEGORIES)
    assert len(CANONICAL_CATEGORIES) == 9


def test_c4_non_canonical_category_never_renders_into_reason():
    # WR-02 regression: a hostile category string must never reach outward
    # reason text, even when its pool clears MIN_CATEGORY_PRICED — both the
    # pool and the label fall back to the fixed marketplace vocabulary.
    hostile = "totally-a-scam-category"
    stats = Stats(
        category_pools={hostile: (1.0, 2.0, 3.0, 4.0, 5.0)},  # >= MIN_CATEGORY_PRICED
        market_pool=(0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0),
        rated_hi=0,
        total_hi=0,
        rating_display_pct=0,
    )
    comp = c_price_vs_category(4.0, hostile, stats)
    assert hostile not in comp["reason"]
    assert "marketplace norm" in comp["reason"]
    assert comp["benchmark"] == 3.0  # marketplace median — hostile pool never used


def test_c4_priced_agent_with_no_priced_pools_is_insufficient_not_crash():
    # WR-03 regression: stats built entirely from unpriced rows used to raise
    # ZeroDivisionError for any priced row (percentile divides by len(pool)).
    stats = build_stats([_row(sold=3), _row(sold=0)])  # zero priced rows anywhere
    comp = c_price_vs_category(4.0, CAT, stats)
    assert comp["score"] is None
    assert comp["observed"] == 4.0
    assert comp["benchmark"] is None
    assert comp["flagged"] is False
    assert comp["reason"] == (
        "insufficient data — no priced agents available for comparison"
    )


# --- C5 listing_age_consistency --------------------------------------------------


def test_c5_single_snapshot_reason():
    comp = c_listing_age_consistency("2026-07-10T00:00:00Z", 1)
    assert comp["score"] is None
    assert comp["reason"] == (
        "insufficient history — listing observed in a single snapshot "
        "(2026-07-10); age and consistency not yet measurable"
    )
    assert comp["observed"] == 1
    assert comp["benchmark"] == 2


def test_c5_two_snapshots_still_none_in_this_score_version():
    comp = c_listing_age_consistency("2026-07-10T00:00:00Z", 2)
    assert comp["score"] is None
    assert comp["reason"] == (
        "insufficient history — age and consistency not computed in this score version"
    )


# --- frozen component dict shape --------------------------------------------------


def test_all_five_components_share_the_frozen_dict_shape():
    comps = {
        "sales_volume_velocity": c_sales_volume_velocity(9, 1),
        "review_signal_ratio": c_review_signal_ratio(5.0, 100.0, 9, STATS_STUB),
        "rating_credibility": c_rating_credibility(5.0, 9),
        "price_vs_category": c_price_vs_category(None, CAT, STATS_STUB),
        "listing_age_consistency": c_listing_age_consistency("2026-07-10T00:00:00Z", 1),
    }
    for name, comp in comps.items():
        assert set(comp) == {"score", "weight", "observed", "benchmark", "flagged", "reason"}
        assert comp["weight"] == WEIGHTS[name]
        assert isinstance(comp["flagged"], bool)
        assert isinstance(comp["reason"], str) and comp["reason"]


# --- build_stats -------------------------------------------------------------------


def _row(category=CAT, price_usdt=None, sold=0, rating=None):
    return {"category": category, "price_usdt": price_usdt, "sold": sold, "rating": rating}


def test_build_stats_pools_include_zero_price_exclude_none():
    rows = [
        _row(price_usdt=2.0),
        _row(price_usdt=0.0),  # 0.0 is a real price - identity check, not truthiness
        _row(price_usdt=None),
        _row(category="Security & Trust", price_usdt=1.0),
    ]
    stats = build_stats(rows)
    assert stats.market_pool == (0.0, 1.0, 2.0)
    assert stats.category_pools[CAT] == (0.0, 2.0)
    assert stats.category_pools["Security & Trust"] == (1.0,)


def test_build_stats_base_rate():
    rows = [
        _row(sold=25, rating=5.0),
        _row(sold=30, rating=4.8),
        _row(sold=40, rating=None),
        _row(sold=19, rating=5.0),  # below the 20-sales bar - not counted
    ]
    stats = build_stats(rows)
    assert (stats.rated_hi, stats.total_hi) == (2, 3)
    assert stats.rating_display_pct == 67  # round(100 * 2 / 3)


def test_build_stats_guards_total_hi_zero():
    stats = build_stats([_row(sold=1), _row(sold=0)])
    assert stats.total_hi == 0
    assert stats.rating_display_pct == 0  # no ZeroDivisionError
