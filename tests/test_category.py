"""Behavior + full-census snapshot tests for indexer.category.

The 9-bucket ordered keyword table is LOCKED (research: "Category Derivation -
Final Table & Verified Distribution", converged over 3 iterations against all
272 real census rows). The behavior tests pin the matching mechanics: bucket
order, word-boundary vs substring semantics, the two vetted regex keywords,
and the Other Services fallback. The full-census section pins all 272 real
assignments (distribution + exact Other Services membership) so any keyword
drift fails loudly instead of silently re-bucketing agents (research
Pitfall 7).
"""
import csv
from collections import Counter
from pathlib import Path

from indexer.category import CATEGORIES, derive_category

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "okx-marketplace-census-2026-07-10.csv"


def _rows():
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_rug_beats_trade_bucket_order():
    # Bucket 1 keyword 'rug' must win over bucket 7 'trade' — order matters.
    assert derive_category("RugRadar", "detect rug pulls before you trade") == "Security & Trust"


def test_blackjack_cjk_substring():
    # '21点' is non-ASCII -> substring match; no tagline needed.
    assert derive_category("BlackjackCoach · 21点教练", "") == "Sports & Prediction"


def test_bazi_lifestyle():
    assert derive_category("八字精批 · Bazi Deep Read", "deep bazi reading") == "Lifestyle & Health"


def test_not_astrology_negation():
    # The (?<!not ) lookbehind keeps 'not astrology' out of Lifestyle & Health;
    # 'onchain'/'data' then route it to Market Data & Analytics (id 4043).
    assert (
        derive_category("ChainAlmanac", "daily briefs based on real onchain data, not astrology")
        == "Market Data & Analytics"
    )


def test_trading_volume_exclusion():
    # \btrading\b(?!\s+(volume|agents)\b) must NOT match 'trading volume';
    # 'volume'/'markets' then route it to Market Data & Analytics.
    assert (
        derive_category("VolumeBot", "tracks trading volume across markets")
        == "Market Data & Analytics"
    )


def test_swap_is_trading_defi():
    assert derive_category("SwapHelper", "best swap routes") == "Trading & DeFi"


def test_fallback_other_services():
    # No keyword matches anywhere -> the fixed fallback, never empty.
    assert derive_category("zzzz", "qqqq") == "Other Services"


def test_determinism_identical_calls():
    first = derive_category("RugRadar", "detect rug pulls before you trade")
    second = derive_category("RugRadar", "detect rug pulls before you trade")
    assert first == second


# --- Full-census pins (Pitfall 7: keyword drift must fail loudly) ------------

# Research-verified counts over all 272 real rows (2026-07-10).
EXPECTED_DISTRIBUTION = {
    "Market Data & Analytics": 70,
    "Security & Trust": 45,
    "Trading & DeFi": 41,
    "Lifestyle & Health": 30,
    "Social & News": 27,
    "Developer Tools & Infra": 22,
    "Sports & Prediction": 17,
    "Creative & Media": 15,
    "Other Services": 5,
}

# The 5 genuinely generic professional-services agents (research-verified):
# 3723 创业直觉顾问, 3932 文档交付工坊, 3700 NexusAgent,
# 3701 ProjectRoadmap Agent, 3746 AgentForge.
OTHER_SERVICES_IDS = {"3723", "3932", "3700", "3701", "3746"}


def _derive(row):
    return derive_category(row["name"].strip(), row["tagline"].strip())


def _only_row_with_name(rows, needle):
    matches = [row for row in rows if needle in row["name"]]
    assert len(matches) == 1, (
        f"expected exactly 1 census row whose name contains {needle!r}, got {len(matches)}"
    )
    return matches[0]


def _row_by_id(rows, agent_id):
    matches = [row for row in rows if row["id"] == agent_id]
    assert len(matches) == 1, (
        f"expected exactly 1 census row with id {agent_id!r}, got {len(matches)}"
    )
    return matches[0]


def test_census_has_272_rows():
    assert len(_rows()) == 272


def test_full_census_distribution():
    # THE drift pin: a keyword-table edit that re-buckets even one agent
    # changes these counts and fails here (research Pitfall 7).
    counts = Counter(_derive(row) for row in _rows())
    assert dict(counts) == EXPECTED_DISTRIBUTION


def test_other_services_exact_members():
    # The fallback must not swallow the catalog: exactly these 5 ids land there.
    other = {row["id"] for row in _rows() if _derive(row) == "Other Services"}
    assert other == OTHER_SERVICES_IDS


def test_spot_checks():
    rows = _rows()
    # AutoLoop (id 1410): 'loan' keywords, not Lifestyle via 'health factor'.
    assert _derive(_only_row_with_name(rows, "AutoLoop")) == "Trading & DeFi"
    # ChainAlmanac (id 4043): the 'not astrology' negation holds on the real row.
    assert _derive(_only_row_with_name(rows, "ChainAlmanac")) == "Market Data & Analytics"
    # Falsify (id 4188): via 'adversarial' - tagline truncates before 'audits'.
    assert _derive(_only_row_with_name(rows, "Falsify")) == "Security & Trust"
    # PROOFPRINT (id 4296): svg artwork.
    assert _derive(_only_row_with_name(rows, "PROOFPRINT")) == "Creative & Media"
    # CoinWM (id 3118): social-data flavor; disclosed fuzzy assignment.
    assert _derive(_only_row_with_name(rows, "CoinWM")) == "Social & News"
    # XMLaunch (id 1406): meme coin, despite 'upload an image'.
    assert _derive(_only_row_with_name(rows, "XMLaunch")) == "Trading & DeFi"
    # NicheScope: id-based lookup (name cell is 'ASP赛道情报 · NicheScope').
    assert _derive(_row_by_id(rows, "4137")) == "Market Data & Analytics"
    # id 3345 这个能吃吗？: research published no bucket for this row - assert
    # only that it lands in a real category, never empty.
    category_3345 = _derive(_row_by_id(rows, "3345"))
    assert category_3345 in CATEGORIES
    assert category_3345 != ""


def test_no_empty_categories():
    for row in _rows():
        category = _derive(row)
        assert isinstance(category, str)
        assert category
        assert category in CATEGORIES


def test_determinism_over_census():
    rows = _rows()
    first = {row["id"]: _derive(row) for row in rows}
    second = {row["id"]: _derive(row) for row in rows}
    assert first == second
