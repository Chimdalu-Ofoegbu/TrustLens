"""End-to-end CLI proof for scoring wired into indexer.refresh (02-02).

`python -m indexer.refresh` is THE single command that indexes AND scores:
compute_all runs inside the same atomic transaction as agents+snapshots.
Determinism gate: generated_at defaults to captured_at — zero wall clock —
so reruns over the seed census are byte-identical. Every pinned count is a
research-locked dry-run value (02-RESEARCH.md "Dry-Run Results").
"""
import dataclasses
import logging
import sqlite3
from pathlib import Path

from indexer.refresh import RefreshSummary, main

REPO_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = REPO_ROOT / "data" / "okx-marketplace-census-2026-07-10.csv"

SEED_TS = "2026-07-10T00:00:00Z"     # filename-derived captured_at
OVERRIDE_TS = "2026-07-11T09:00:00Z"

EXPECTED_GRADE_ROWS = [
    ("A", 12), ("B", 9), ("C", 19), ("D", 54), ("F", 27), ("NR", 151),
]


def _run(db_path, *extra):
    """In-process CLI call over the real census (mirrors test_refresh.py)."""
    return main(["--csv", str(CSV_PATH), "--db", str(db_path),
                 "--web-out", str(Path(db_path).parent / "index.html"), *extra])


def _dump(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT * FROM scores ORDER BY agent_id").fetchall()
    finally:
        conn.close()


# --- 1. one command indexes AND scores ---------------------------------------

def test_cli_scores_272_rows_with_default_timestamps(tmp_path):
    db = tmp_path / "cli.db"
    assert _run(db) == 0
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0] == 272
        # Locked default: generated_at = captured_at — no wall clock anywhere.
        off = conn.execute(
            "SELECT COUNT(*) FROM scores WHERE generated_at != ? OR data_as_of != ?",
            (SEED_TS, SEED_TS),
        ).fetchone()[0]
        assert off == 0
    finally:
        conn.close()


# --- 2. scores summary is its own INFO line ----------------------------------

def test_cli_logs_scores_summary_line(tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="indexer.refresh"):
        assert _run(tmp_path / "log.db") == 0
    messages = [
        r.getMessage()
        for r in caplog.records
        if r.name == "indexer.refresh" and r.levelno == logging.INFO
    ]
    assert "scores computed: 121 scored, 151 not rated, version=1.0.0" in messages


# --- 3. cross-run determinism through the CLI ---------------------------------

def test_cli_rerun_is_byte_identical(tmp_path):
    db = tmp_path / "rerun.db"
    assert _run(db) == 0
    first = _dump(db)
    assert _run(db) == 0
    second = _dump(db)
    assert len(second) == 272
    assert first == second


# --- 4. --generated-at stamps provenance without touching data_as_of ----------

def test_generated_at_override_stamps_generated_only(tmp_path):
    db = tmp_path / "override.db"
    assert _run(db, "--generated-at", OVERRIDE_TS) == 0
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT DISTINCT generated_at, data_as_of FROM scores"
        ).fetchall()
        assert rows == [(OVERRIDE_TS, SEED_TS)]
    finally:
        conn.close()


# --- 5. persisted grade distribution -------------------------------------------

def test_persisted_grade_distribution(tmp_path):
    db = tmp_path / "grades.db"
    assert _run(db) == 0
    conn = sqlite3.connect(db)
    try:
        dist = conn.execute(
            "SELECT grade, COUNT(*) FROM scores GROUP BY grade ORDER BY grade"
        ).fetchall()
    finally:
        conn.close()
    assert dist == EXPECTED_GRADE_ROWS


# --- 6. regression guard: RefreshSummary stays frozen ---------------------------

def test_refresh_summary_fields_unchanged():
    # Locked orchestrator decision: the scores summary is a separate log
    # line — RefreshSummary never grows fields for it.
    names = [f.name for f in dataclasses.fields(RefreshSummary)]
    assert names == ["agents", "snapshots_appended", "field_warnings", "source"]
