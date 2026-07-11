"""CLI-level proof for the leaderboard wired into indexer.refresh (03-03, WEB-03).

One command — python -m indexer.refresh — indexes, scores, AND regenerates
the leaderboard page from SQLite in the same run. Pinned contracts: the page
is rebuilt on every CLI refresh, reruns are HTML byte-identical (Phase 2
determinism extended to the artifact), a failed page build is an environment
problem (exit 2, same class as a db failure), and library refresh() calls
without web_out never write a page (research Pitfall 7 isolation).
"""
import hashlib
import logging
import sqlite3
from pathlib import Path

from indexer.refresh import main, refresh

REPO_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = REPO_ROOT / "data" / "okx-marketplace-census-2026-07-10.csv"

SEED_TS = "2026-07-10T00:00:00Z"


def _run(db_path, web_out, *extra):
    """In-process CLI call over the real census (mirrors test_refresh_scores)."""
    return main(["--csv", str(CSV_PATH), "--db", str(db_path),
                 "--web-out", str(web_out), *extra])


# --- 1. one command indexes, scores, AND regenerates the page -----------------

def test_cli_regenerates_page(tmp_path):
    out = tmp_path / "index.html"
    assert _run(tmp_path / "t.db", out) == 0
    assert out.is_file()
    assert out.stat().st_size > 50 * 1024
    html = out.read_text(encoding="utf-8")
    assert html.count('<tr id="agent-') == 272
    assert 'id="methodology"' in html
    assert 'id="badge"' in html


# --- 2. rerun determinism reaches the HTML artifact ----------------------------

def test_cli_rerun_html_byte_identical(tmp_path):
    db = tmp_path / "rerun.db"
    out = tmp_path / "index.html"
    assert _run(db, out) == 0
    first = hashlib.sha256(out.read_bytes()).hexdigest()
    assert _run(db, out) == 0
    second = hashlib.sha256(out.read_bytes()).hexdigest()
    assert first == second


# --- 3. build failure is an environment problem: exit 2 ------------------------

def test_page_build_failure_exits_2(tmp_path):
    # A FILE where the output parent dir should be: mkdir/open raises OSError
    # on every platform — same failure class as an unopenable db.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    db = tmp_path / "t.db"
    assert _run(db, blocker / "index.html") == 2
    # The db stage committed before the build attempt — taxonomy preserved.
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0] == 272
    finally:
        conn.close()


# --- 4. library calls write NO page (Pitfall 7 isolation) ----------------------

def test_library_refresh_writes_no_page(tmp_path):
    summary = refresh(CSV_PATH, tmp_path / "t.db", SEED_TS)
    assert summary.agents == 272
    assert list(tmp_path.glob("**/*.html")) == []


# --- 5. wiring leaves the summary path intact; build logs its own line ---------

def test_refresh_summary_unchanged_by_wiring(tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="indexer.refresh"):
        assert _run(tmp_path / "t.db", tmp_path / "index.html") == 0
    messages = [
        r.getMessage()
        for r in caplog.records
        if r.name == "indexer.refresh" and r.levelno == logging.INFO
    ]
    assert any(m.startswith("leaderboard built:") for m in messages)
