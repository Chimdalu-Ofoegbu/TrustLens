"""Golden-value pins and enforcement layers over all 272 real census agents.

Pins come from the 02-RESEARCH.md dry-run (executed against the real
database, cross-process byte-identical). DEVIATION RULE: if any golden
mismatches, the formula transcription is wrong — fix the scoring code
against the research spec; NEVER edit the pinned values.

Also enforces SCOR-03 in two layers (scoring/ source scan + all 272
rendered cards) and SCOR-01 byte-identity across fresh builds.
"""
import re
from collections import Counter
from pathlib import Path

import pytest

from indexer.census import load_census
from scoring import (
    DISCLAIMER,
    GRADE_DESCRIPTIONS,
    build_stats,
    score_agent,
    serialize_components,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CENSUS = REPO_ROOT / "data" / "okx-marketplace-census-2026-07-10.csv"
SCORING_DIR = REPO_ROOT / "scoring"
BANNED = re.compile(r"(?i)(fraud|scam|fake|manipulat)")

COMPONENT_NAMES = {
    "sales_volume_velocity",
    "review_signal_ratio",
    "rating_credibility",
    "price_vs_category",
    "listing_age_consistency",
}


def build_rows():
    records, _ = load_census(CENSUS)
    return [
        {"id": r.id, "category": r.category, "sold": r.sold, "rating": r.rating,
         "positive_pct": r.positive_pct, "price_usdt": r.price_usdt,
         "first_seen": "2026-07-10T00:00:00Z"}
        for r in sorted(records, key=lambda r: r.id)
    ]


def build_cards():
    rows = build_rows()
    stats = build_stats(rows)
    return {row["id"]: score_agent(row, stats, 1) for row in rows}  # 1 distinct snapshot: production reality


@pytest.fixture(scope="module")
def rows():
    return build_rows()


@pytest.fixture(scope="module")
def cards(rows):
    stats = build_stats(rows)
    return {row["id"]: score_agent(row, stats, 1) for row in rows}


# --- 1. golden values (research dry-run observed) -----------------------------

GOLDEN = {
    "3118": (95, "A", "high"),    # CoinWM Open API, the 1.55K-sold parse case
    "3345": (94, "A", "high"),    # CJK-named agent
    "2013": (73, "B", "medium"),  # CoinAnk: 1370 sold, unrated
    "1965": (82, "B", "high"),    # CertiK
    "2169": (56, "C", "medium"),  # FundingArb: rated, positive_pct NULL
    "2177": (46, "D", "low"),     # Coin Oracle
    "2791": (41, "D", "low"),     # name-collision twin, scored
    "3152": (32, "F", "low"),     # Messari: 2.0 rating, 0% positive
    "2662": (None, "NR", "low"),  # name-collision twin, zero evidence
    "4137": (None, "NR", "low"),  # prose sold cell -> 0, unrated
}


def test_golden_values(cards):
    for agent_id, expected in GOLDEN.items():
        card = cards[agent_id]
        assert (card["score"], card["grade"], card["confidence"]) == expected, agent_id


# --- 2. grade distribution ------------------------------------------------------


def test_grade_distribution(cards):
    grades = Counter(card["grade"] for card in cards.values())
    assert dict(grades) == {"A": 12, "B": 9, "C": 19, "D": 54, "F": 27, "NR": 151}
    assert sum(1 for c in cards.values() if c["score"] is not None) == 121
    assert sum(1 for c in cards.values() if c["score"] is None) == 151


# --- 3. confidence distribution ---------------------------------------------------


def test_confidence_distribution(cards):
    confidence = Counter(card["confidence"] for card in cards.values())
    assert dict(confidence) == {"high": 14, "medium": 26, "low": 232}


# --- 4. thin-perfect cohort (brief-verbatim case) -----------------------------------


def test_thin_perfect_cohort_flagged_never_accused_never_top_ranked(rows, cards):
    cohort = [row["id"] for row in rows if row["rating"] == 5.0 and row["sold"] < 5]
    assert len(cohort) == 42
    for agent_id in cohort:
        card = cards[agent_id]
        assert card["components"]["rating_credibility"]["flagged"] is True, agent_id
        assert card["confidence"] == "low", agent_id
    grades = Counter(cards[agent_id]["grade"] for agent_id in cohort)
    assert dict(grades) == {"D": 34, "F": 8}


# --- 5. every component of every card carries a reason --------------------------------


def test_every_component_of_every_card_has_a_reason(cards):
    assert len(cards) == 272
    for agent_id, card in cards.items():
        # NR is a successful response: all five components render on every card.
        assert set(card["components"]) == COMPONENT_NAMES, agent_id
        for name, comp in card["components"].items():
            assert isinstance(comp["reason"], str) and comp["reason"], (agent_id, name)


# --- 6. exact reason pin (proves the base-rate wiring) ----------------------------------


def test_exact_reason_pin_for_base_rate_wiring(cards):
    assert cards["2013"]["components"]["review_signal_ratio"]["reason"] == (
        "no displayed rating despite 1370 units sold — "
        "87% of agents with 20+ sales display one (20 of 23)"
    )


# --- 7. banned vocabulary, rendered layer (SCOR-03) ---------------------------------------


def test_banned_vocabulary_rendered_layer(cards):
    for agent_id, card in cards.items():
        blob = serialize_components(card["components"]) + card["grade"] + card["confidence"]
        assert not BANNED.search(blob), agent_id
    assert not BANNED.search(DISCLAIMER)
    for grade, text in GRADE_DESCRIPTIONS.items():
        assert not BANNED.search(text), grade


# --- 8. banned vocabulary, source layer (SCOR-03) -------------------------------------------


def test_banned_vocabulary_source_layer():
    # The regex literal lives here in tests/, outside the scanned tree.
    files = sorted(SCORING_DIR.rglob("*.py"))
    assert files, "scoring/ package must exist"
    for path in files:
        assert not BANNED.search(path.read_text(encoding="utf-8")), path.name


# --- 9. no-I/O source guard -------------------------------------------------------------------

FORBIDDEN_IMPORT = re.compile(
    r"^(?:import|from)\s+(os|sys|time|datetime|random|socket|httpx|requests|urllib)\b"
)
SQLITE_IMPORT = re.compile(r"^(?:import|from)\s+sqlite3\b")


def test_no_io_imports_in_scoring_source():
    for path in sorted(SCORING_DIR.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            assert not FORBIDDEN_IMPORT.match(line), f"{path.name}:{lineno}: {line}"
            if path.name != "persist.py":  # plan 02-02's sanctioned sqlite3 exception
                assert not SQLITE_IMPORT.match(line), f"{path.name}:{lineno}: {line}"


# --- 10. byte-identity (SCOR-01) ------------------------------------------------------------------


def test_byte_identity_across_fresh_builds():
    first = build_cards()
    second = build_cards()
    assert set(first) == set(second)
    for agent_id, card in first.items():
        other = second[agent_id]
        assert (card["score"], card["grade"], card["confidence"]) == (
            other["score"], other["grade"], other["confidence"],
        ), agent_id
        assert serialize_components(card["components"]) == serialize_components(
            other["components"]
        ), agent_id
