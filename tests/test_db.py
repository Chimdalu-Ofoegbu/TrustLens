"""Behavior tests for indexer.db — the SQLite persistence layer (INDX-03).

Schema semantics are locked (.planning/phases/01-foundation-data-indexer/
01-CONTEXT.md "Schema (locked semantics)"); the upsert follows 01-RESEARCH.md
"Architecture Patterns" Pattern 2 (ON CONFLICT preserves first_seen).
Timestamps are ISO-8601 TEXT strings injected by the tests — indexer.db never
reads the wall clock.
"""
import pytest

from indexer.db import connect, init_db, insert_snapshot, upsert_agent
from indexer.models import AgentRecord


def make_record(**overrides) -> AgentRecord:
    """Synthetic AgentRecord; override any field per test."""
    base = dict(
        id="9001",
        name="Test Agent",
        name_key="test agent",
        category="Market Data & Analytics",
        tagline="a synthetic listing",
        price_usdt=0.01,
        price_raw="0.01 USDT",
        sold=5,
        rating=4.5,
        positive_pct=95.0,
        category_source="derived",
    )
    base.update(overrides)
    return AgentRecord(**base)


@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    init_db(c)
    yield c
    c.close()


# --- schema -------------------------------------------------------------

def test_init_creates_schema(tmp_path):
    c = connect(tmp_path / "fresh.db")
    init_db(c)
    tables = {
        r["name"]
        for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"agents", "snapshots"} <= tables
    indexes = {
        r["name"]
        for r in c.execute("SELECT name FROM sqlite_master WHERE type='index'")
    }
    assert {
        "idx_agents_name_key",
        "idx_agents_category",
        "idx_snapshots_agent",
    } <= indexes
    c.close()


def test_init_idempotent(tmp_path):
    c = connect(tmp_path / "twice.db")
    init_db(c)
    init_db(c)  # every statement is CREATE ... IF NOT EXISTS -> no exception
    c.close()


def test_wal_mode(tmp_path):
    c = connect(tmp_path / "wal.db")
    mode = c.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
    c.close()


# --- upsert -------------------------------------------------------------

def test_upsert_preserves_first_seen(conn):
    upsert_agent(conn, make_record(sold=5), captured_at="2026-07-10T00:00:00Z")
    upsert_agent(conn, make_record(sold=9), captured_at="2026-07-11T00:00:00Z")
    rows = conn.execute("SELECT * FROM agents WHERE id = ?", ("9001",)).fetchall()
    assert len(rows) == 1  # rerun keeps exactly one row per id
    row = rows[0]
    assert row["first_seen"] == "2026-07-10T00:00:00Z"  # preserved on conflict
    assert row["last_seen"] == "2026-07-11T00:00:00Z"   # refreshed on conflict
    assert row["sold"] == 9


# --- snapshots ----------------------------------------------------------

def test_snapshot_appends(conn):
    rec = make_record()
    upsert_agent(conn, rec, captured_at="2026-07-10T00:00:00Z")  # FK target
    insert_snapshot(conn, rec, captured_at="2026-07-10T00:00:00Z")
    insert_snapshot(conn, rec, captured_at="2026-07-10T00:00:00Z")
    rows = conn.execute(
        "SELECT source FROM snapshots WHERE agent_id = ?", ("9001",)
    ).fetchall()
    assert len(rows) == 2  # always append, even for identical captured_at
    assert all(r["source"] == "census" for r in rows)
