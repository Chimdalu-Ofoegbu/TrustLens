"""Behavior tests for indexer.category.

The 9-bucket ordered keyword table is LOCKED (research: "Category Derivation -
Final Table & Verified Distribution", converged over 3 iterations against all
272 real census rows). These tests pin the matching mechanics: bucket order,
word-boundary vs substring semantics, the two vetted regex keywords, and the
Other Services fallback.
"""
from indexer.category import derive_category


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
