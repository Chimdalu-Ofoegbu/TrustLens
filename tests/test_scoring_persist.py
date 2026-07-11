"""Behavior tests for scoring.persist — compute_all over the real census (02-02).

compute_all is the only scoring module that touches sqlite3 and it NEVER
commits: the caller owns the transaction (same contract as
indexer.db.upsert_agent). Every expected count and golden value below is a
research-locked dry-run result (.planning/phases/02-scoring-engine/
02-RESEARCH.md "Dry-Run Results", verified over all 272 real agents).
"""
import json
import re
import sqlite3
from pathlib import Path

import pytest

from indexer.census import load_census
from indexer.db import connect, init_db, insert_snapshot
from indexer.refresh import persist
from scoring import SCORE_VERSION, compute_all
from scoring.persist import INSERT_SCORE

CENSUS = Path(__file__).resolve().parents[1] / "data" / "okx-marketplace-census-2026-07-10.csv"
SEED_TS = "2026-07-10T00:00:00Z"
NEXT_TS = "2026-07-11T00:00:00Z"

# Research-pinned grade distribution over the real 272-agent census.
EXPECTED_GRADES = {"A": 12, "B": 9, "C": 19, "D": 54, "F": 27, "NR": 151}

COMPONENT_KEYS = {
    "listing_age_consistency",
    "price_vs_category",
    "rating_credibility",
    "review_signal_ratio",
    "sales_volume_velocity",
}

# SCOR-03 banned vocabulary — must never appear in any persisted blob.
BANNED = re.compile(r"(?i)(fraud|scam|fake|manipulat)")


@pytest.fixture(scope="module")
def records():
    recs, _ = load_census(CENSUS)
    return recs


@pytest.fixture()
def seeded(tmp_path, records):
    """Fresh DB with the real census loaded; scores table exists but empty."""
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    with conn:
        persist(conn, records, SEED_TS)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def computed(tmp_path_factory, records):
    """One computed scores table over the real census; read-only for dependents."""
    conn = connect(tmp_path_factory.mktemp("persist") / "census.db")
    init_db(conn)
    with conn:
        persist(conn, records, SEED_TS)
    with conn:
        result = compute_all(conn, SEED_TS, SEED_TS)
    yield result, conn
    conn.close()


# --- schema -------------------------------------------------------------

def test_init_db_creates_scores_table_with_exact_columns(tmp_path):
    conn = connect(tmp_path / "fresh.db")
    init_db(conn)
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(scores)")]
    assert cols == [
        "agent_id",
        "score",
        "grade",
        "confidence",
        "score_version",
        "generated_at",
        "data_as_of",
        "components",
    ]
    conn.close()


# --- full-census compute --------------------------------------------------

def test_compute_all_counts_and_grade_distribution(computed):
    (scored, not_rated), conn = computed
    assert (scored, not_rated) == (121, 151)
    assert conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0] == 272
    dist = dict(conn.execute("SELECT grade, COUNT(*) FROM scores GROUP BY grade"))
    assert dist == EXPECTED_GRADES


def test_nr_rows_roundtrip_null_score(computed):
    _, conn = computed
    # NR is a successful row, not an error: score NULL + grade 'NR' coincide
    # exactly — no half-written states in either direction.
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    assert q("SELECT COUNT(*) FROM scores WHERE score IS NULL AND grade = 'NR'") == 151
    assert q("SELECT COUNT(*) FROM scores WHERE score IS NULL") == 151
    assert q("SELECT COUNT(*) FROM scores WHERE grade = 'NR'") == 151


def test_golden_spot_checks(computed):
    _, conn = computed

    def card(agent_id):
        row = conn.execute(
            "SELECT score, grade, confidence FROM scores WHERE agent_id = ?",
            (agent_id,),
        ).fetchone()
        assert row is not None, f"agent {agent_id} missing from scores"
        return (row["score"], row["grade"], row["confidence"])

    assert card("3118") == (95, "A", "high")
    assert card("2013") == (73, "B", "medium")
    assert card("3152") == (32, "F", "low")
    assert card("2662") == (None, "NR", "low")


def test_envelope_columns_stamped(computed):
    _, conn = computed
    row = conn.execute(
        "SELECT score_version, generated_at, data_as_of FROM scores WHERE agent_id = ?",
        ("3118",),
    ).fetchone()
    assert row["score_version"] == SCORE_VERSION
    assert row["generated_at"] == SEED_TS
    assert row["data_as_of"] == SEED_TS


# --- determinism & self-cleaning -------------------------------------------

def test_recompute_is_byte_identical_and_self_cleaning(seeded):
    conn = seeded
    with conn:
        compute_all(conn, SEED_TS, SEED_TS)
    first = [tuple(r) for r in conn.execute("SELECT * FROM scores ORDER BY agent_id")]
    with conn:
        compute_all(conn, SEED_TS, SEED_TS)
    second = [tuple(r) for r in conn.execute("SELECT * FROM scores ORDER BY agent_id")]
    assert len(second) == 272  # DELETE+INSERT never accumulates rows
    assert first == second


# --- transaction contract ----------------------------------------------------

def test_rollback_leaves_scores_unchanged(seeded):
    conn = seeded
    conn.execute("BEGIN")
    assert compute_all(conn, SEED_TS, SEED_TS) == (121, 151)
    conn.rollback()
    # No internal commit: the caller's rollback erases the whole write.
    assert conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0] == 0


def test_insert_score_fk_enforced(seeded):
    conn = seeded
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            INSERT_SCORE,
            ("no-such-agent", 50, "C", "low", SCORE_VERSION, SEED_TS, SEED_TS, "{}"),
        )


# --- history counting: distinct capture times, never raw rows -----------------

def test_history_counts_distinct_captured_at_not_rows(seeded, records):
    conn = seeded
    rec = next(r for r in records if r.id == "3345")
    # Two MORE duplicate rows at the seed captured_at: 3 raw rows, 1 distinct.
    with conn:
        insert_snapshot(conn, rec, SEED_TS)
        insert_snapshot(conn, rec, SEED_TS)
        compute_all(conn, SEED_TS, SEED_TS)
    comps = json.loads(
        conn.execute(
            "SELECT components FROM scores WHERE agent_id = ?", ("3345",)
        ).fetchone()[0]
    )
    assert "single snapshot" in comps["sales_volume_velocity"]["reason"]
    assert "single snapshot" in comps["listing_age_consistency"]["reason"]

    # A second DISTINCT captured_at is real history: C5 flips to the
    # not-computed-in-this-version variant.
    with conn:
        insert_snapshot(conn, rec, NEXT_TS)
        compute_all(conn, SEED_TS, SEED_TS)
    comps = json.loads(
        conn.execute(
            "SELECT components FROM scores WHERE agent_id = ?", ("3345",)
        ).fetchone()[0]
    )
    assert "not computed in this score version" in comps["listing_age_consistency"]["reason"]


# --- persisted components JSON -------------------------------------------------

def test_components_json_valid_five_keys_banned_vocab_clean(computed):
    _, conn = computed
    rows = conn.execute("SELECT agent_id, components FROM scores").fetchall()
    assert len(rows) == 272
    for agent_id, blob in rows:
        comps = json.loads(blob)  # every persisted blob is valid JSON
        assert set(comps) == COMPONENT_KEYS, agent_id
        assert not BANNED.search(blob), agent_id
