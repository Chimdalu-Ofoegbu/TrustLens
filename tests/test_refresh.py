"""Full-census integration suite for indexer.refresh — the Phase 1 proof.

Runs the real committed census (272 rows) end-to-end through
load_census -> persist -> SQLite and pins every research-verified value
(.planning/phases/01-foundation-data-indexer/01-RESEARCH.md "Known fixture
rows" + "Rating & positive columns" cross-tabulation). Zero network access:
everything reads local files only.

Snapshot duplication on rerun (272 agents / 544 snapshots) is BY DESIGN
(locked) — do not "fix" it by deduplicating.
"""
import logging
import sqlite3
from pathlib import Path

import pytest

from indexer.census import load_census
from indexer.parse import name_key
from indexer.refresh import main, refresh

REPO_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = REPO_ROOT / "data" / "okx-marketplace-census-2026-07-10.csv"

SEED_TS = "2026-07-10T00:00:00Z"
NEXT_TS = "2026-07-11T00:00:00Z"

# Research-verified category distribution over all 272 real rows.
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


@pytest.fixture(scope="module")
def census_run(tmp_path_factory):
    """One full refresh of the real census; read-only for all dependent tests."""
    db_path = tmp_path_factory.mktemp("refresh") / "census.db"
    summary = refresh(CSV_PATH, db_path, SEED_TS)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    yield summary, conn
    conn.close()


def _agent(conn, agent_id):
    row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    assert row is not None, f"agent {agent_id} missing from db"
    return row


# --- 1. full load -----------------------------------------------------------

def test_full_census_loads_272(census_run):
    summary, conn = census_run
    assert summary.agents == 272
    assert summary.snapshots_appended == 272
    assert summary.field_warnings == 1        # exactly one: id 4137 prose sold
    assert summary.source == "census"
    assert conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0] == 272
    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 272


# --- 2. rerun idempotency ----------------------------------------------------

def test_rerun_is_idempotent_for_agents_appends_snapshots(tmp_path):
    db = tmp_path / "rerun.db"
    refresh(CSV_PATH, db, SEED_TS)
    refresh(CSV_PATH, db, NEXT_TS)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        # agents: no duplicates, no corruption; snapshots: 272 + 272 appended.
        assert conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0] == 272
        assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 544
        row = _agent(conn, "3345")
        assert row["first_seen"] == SEED_TS   # preserved across the rerun
        assert row["last_seen"] == NEXT_TS    # refreshed by the rerun
    finally:
        conn.close()


# --- 3. edge-case rows, exact verified values --------------------------------

def test_edge_case_rows_exact_values(census_run):
    _, conn = census_run

    # 3345 — CJK name with U+FF1F fullwidth question mark, NFKC-folded key.
    row = _agent(conn, "3345")
    assert row["name"] == "这个能吃吗？"
    assert row["name_key"] == "这个能吃吗?"
    assert row["rating"] == 5.0
    assert row["positive_pct"] == 100.0
    assert row["sold"] == 539
    assert row["price_usdt"] == 0.01
    assert row["price_raw"] == "0.01 USDT"

    # 3118 — K-suffixed sold count.
    row = _agent(conn, "3118")
    assert row["name"] == "CoinWM Open API"
    assert row["sold"] == 1550

    # 2023 — subscript-zero price (0.0₄15 = 0.000015, never the 10x off-by-one).
    row = _agent(conn, "2023")
    assert row["name"] == "Onchain Data Explorer"
    assert row["price_usdt"] == 0.000015
    assert row["price_raw"] == "0.0₄15 USDT"
    assert row["rating"] == 4.9
    assert row["positive_pct"] == 92.86
    assert row["sold"] == 547

    # 2013 — the shifted-column echo: rating cell copies the price number.
    row = _agent(conn, "2013")
    assert row["name"] == "CoinAnk OpenAPI"
    assert row["rating"] is None
    assert row["positive_pct"] is None
    assert row["sold"] == 1370
    assert row["price_usdt"] == 0.01

    # 4137 — prose in the sold column: stored 0 with the load's one warning.
    row = _agent(conn, "4137")
    assert row["sold"] == 0
    assert row["rating"] is None
    assert row["price_usdt"] == 0.5

    # 4489 — the echo that looks like a perfect 5-star rating.
    row = _agent(conn, "4489")
    assert row["name"] == "OK 飞行"
    assert row["rating"] is None
    assert row["price_usdt"] == 5.0
    assert row["sold"] == 0

    # 2169 — rating rule A keeps the paragraph-positive rating.
    row = _agent(conn, "2169")
    assert row["name"] == "FundingArb"
    assert row["rating"] == 5.0
    assert row["positive_pct"] is None
    assert row["sold"] == 6
    assert row["price_usdt"] == 1.0

    # 3091 — paragraph positive + echo '1': fully unrated.
    row = _agent(conn, "3091")
    assert row["rating"] is None
    assert row["positive_pct"] is None

    # 2791 — rated agent with an empty price cell.
    row = _agent(conn, "2791")
    assert row["rating"] == 5.0
    assert row["positive_pct"] == 100.0
    assert row["price_usdt"] is None
    assert row["price_raw"] == ""
    assert row["sold"] == 2

    # 1851 — the other subscript variant (0.0₅1 = 0.000001).
    row = _agent(conn, "1851")
    assert row["name"] == "Ethy AI"
    assert row["price_usdt"] == 0.000001
    assert row["sold"] == 34
    assert row["rating"] == 5.0

    # 1500 — multiline quoted tagline survives ingest intact.
    row = _agent(conn, "1500")
    assert row["name"] == "AlphaCopy"
    assert "\n\n" in row["tagline"]
    assert row["rating"] == 4.6
    assert row["positive_pct"] == 95.45
    assert row["sold"] == 175
    assert row["price_usdt"] == 0.1


# --- 4. aggregate invariants --------------------------------------------------

def test_aggregate_invariants(census_run):
    _, conn = census_run
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    assert q("SELECT COUNT(*) FROM agents WHERE price_usdt IS NULL") == 28
    assert q("SELECT COUNT(*) FROM agents WHERE rating IS NOT NULL") == 90
    assert q("SELECT COUNT(*) FROM agents WHERE positive_pct IS NOT NULL") == 89
    # 150 real "0 sold" rows + id 4137's prose-sold fallback.
    assert q("SELECT COUNT(*) FROM agents WHERE sold = 0") == 151
    assert q("SELECT MAX(sold) FROM agents") == 1550
    assert q("SELECT COUNT(*) FROM agents WHERE category_source != 'derived'") == 0
    assert q("SELECT COUNT(*) FROM snapshots WHERE source != 'census'") == 0
    distribution = dict(
        conn.execute("SELECT category, COUNT(*) FROM agents GROUP BY category")
    )
    assert distribution == EXPECTED_DISTRIBUTION


# --- 5. name_key collisions ---------------------------------------------------

def test_name_key_collisions_persist(census_run):
    _, conn = census_run
    key = name_key("链上任务助手")
    count = conn.execute(
        "SELECT COUNT(*) FROM agents WHERE name_key = ?", (key,)
    ).fetchone()[0]
    assert count == 2
    ids = {
        r["id"]
        for r in conn.execute("SELECT id FROM agents WHERE name_key = ?", (key,))
    }
    assert ids == {"2791", "2662"}


# --- 6. snapshot row content ---------------------------------------------------

def test_snapshot_row_content(census_run):
    _, conn = census_run
    rows = conn.execute(
        "SELECT * FROM snapshots WHERE agent_id = ?", ("3345",)
    ).fetchall()
    assert len(rows) == 1
    snap = rows[0]
    assert snap["captured_at"] == SEED_TS
    assert snap["price_usdt"] == 0.01
    assert snap["sold"] == 539
    assert snap["rating"] == 5.0
    assert snap["positive_pct"] == 100.0
    assert snap["source"] == "census"


# --- 7. warning hygiene ---------------------------------------------------------

def test_warning_references_row_and_id(caplog):
    with caplog.at_level(logging.WARNING, logger="indexer.census"):
        _, warnings = load_census(CSV_PATH)
    records = [
        r
        for r in caplog.records
        if r.name == "indexer.census" and r.levelno == logging.WARNING
    ]
    assert warnings == 1
    assert len(records) == 1
    message = records[0].getMessage()
    assert "4137" in message
    # Row/id only — raw cell text would carry newlines (log injection) and CJK.
    assert "\n" not in message


def test_warning_escapes_newline_embedded_in_id_cell(tmp_path, caplog):
    # WR-03 regression: the logged id is itself cell text, and a quoted id
    # cell can carry an internal newline (_cell strips ends only). Rendered
    # with %r the newline stays escaped — no forged log lines.
    crafted = tmp_path / "crafted.csv"
    crafted.write_text(
        "id,name,tagline,rating,positive,sold,price\n"
        '"9001\nERROR indexer.census: forged line",Evil,t,,,not a count,1 USDT\n',
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="indexer.census"):
        _, warnings = load_census(crafted)
    assert warnings == 1  # the unparseable sold cell
    [record] = [
        r
        for r in caplog.records
        if r.name == "indexer.census" and r.levelno == logging.WARNING
    ]
    message = record.getMessage()
    assert "9001" in message
    assert "\n" not in message   # nothing to forge a second line with
    assert "\\n" in message      # the newline survives only as an escape


# --- 8-10. CLI exit paths --------------------------------------------------------

def test_cli_main(tmp_path, monkeypatch):
    # DEFAULT_CSV is repo-relative; anchor cwd so the bare default resolves.
    monkeypatch.chdir(REPO_ROOT)
    db = tmp_path / "cli.db"
    assert main(
        ["--db", str(db), "--web-out", str(tmp_path / "index.html")]
    ) == 0
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        assert conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0] == 272
        # Filename-derived captured_at: 2026-07-10 -> the seed baseline.
        assert _agent(conn, "3345")["first_seen"] == SEED_TS
    finally:
        conn.close()


def test_cli_missing_csv_returns_1(tmp_path, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    db = tmp_path / "missing.db"
    assert main(["--csv", "data/does-not-exist.csv", "--db", str(db)]) == 1


def test_cli_dateless_filename_returns_2(tmp_path):
    mini = tmp_path / "census.csv"
    mini.write_text(
        "id,name,tagline,rating,positive,sold,price\n"
        "9001,Mini Agent,a plain tagline,5.0,100% positive,3 sold,0.01 USDT\n",
        encoding="utf-8",
    )
    db = tmp_path / "mini.db"
    # No date in the filename and no --captured-at: refuse (never wall clock).
    assert main(["--csv", str(mini), "--db", str(db)]) == 2
    # An explicit --captured-at unblocks the same invocation.
    assert main(
        ["--csv", str(mini), "--db", str(db), "--captured-at", SEED_TS,
         "--web-out", str(tmp_path / "index.html")]
    ) == 0


def test_cli_non_utf8_csv_returns_1(tmp_path):
    # WR-02 regression: an undecodable file IS an "unreadable csv" — exit 1
    # with a logged error, never a UnicodeDecodeError traceback.
    bad = tmp_path / "census-2026-07-10.csv"
    bad.write_bytes(
        b"id,name,tagline,rating,positive,sold,price\n"
        b"9001,Caf\xe9 Agent,t,,,0 sold,1 USDT\n"  # lone 0xE9 is invalid UTF-8
    )
    assert main(["--csv", str(bad), "--db", str(tmp_path / "bad.db")]) == 1


def test_cli_oversized_cell_returns_1(tmp_path):
    # WR-02 regression: csv.field_size_limit (128 KB) is the T-04-04 DoS
    # bound — exceeding it must exit 1, not crash with an unhandled csv.Error.
    huge = tmp_path / "census-2026-07-10.csv"
    huge.write_text(
        "id,name,tagline,rating,positive,sold,price\n"
        '9001,Big Agent,"' + "x" * 200_000 + '",,,0 sold,1 USDT\n',
        encoding="utf-8",
    )
    assert main(["--csv", str(huge), "--db", str(tmp_path / "huge.db")]) == 1


def test_cli_unopenable_db_returns_2(tmp_path):
    # WR-02 regression: a --db that cannot be opened (here: an existing
    # directory) is an environment failure — exit 2, distinct from csv's 1.
    assert main(["--csv", str(CSV_PATH), "--db", str(tmp_path)]) == 2
