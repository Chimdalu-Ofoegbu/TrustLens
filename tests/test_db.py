"""Behavior tests for indexer.db — the SQLite persistence layer (INDX-03).

Schema semantics are locked (.planning/phases/01-foundation-data-indexer/
01-CONTEXT.md "Schema (locked semantics)"); the upsert follows 01-RESEARCH.md
"Architecture Patterns" Pattern 2 (ON CONFLICT preserves first_seen).
Timestamps are ISO-8601 TEXT strings injected by the tests — indexer.db never
reads the wall clock.
"""
import sqlite3

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


# --- hardening: collisions, FK enforcement, hostile content --------------

def test_name_key_collision_allowed(conn):
    # Mirrors the REAL census collision: 链上任务助手 is TWO different agents
    # (ids 2791 and 2662). A uniqueness constraint on name_key would crash
    # refresh on real data — both rows must persist.
    upsert_agent(
        conn,
        make_record(id="2791", name="链上任务助手", name_key="链上任务助手"),
        captured_at="2026-07-10T00:00:00Z",
    )
    upsert_agent(
        conn,
        make_record(id="2662", name="链上任务助手", name_key="链上任务助手"),
        captured_at="2026-07-10T00:00:00Z",
    )
    count = conn.execute(
        "SELECT COUNT(*) FROM agents WHERE name_key = ?", ("链上任务助手",)
    ).fetchone()[0]
    assert count == 2


def test_foreign_key_enforced(conn):
    # PRAGMA foreign_keys=ON must be active on the connection (sqlite3 ships
    # with it OFF) — snapshots pointing at unknown agents are rejected.
    with pytest.raises(sqlite3.IntegrityError):
        insert_snapshot(
            conn,
            make_record(id="does-not-exist"),
            captured_at="2026-07-10T00:00:00Z",
        )


def test_hostile_content_roundtrip(conn):
    # T-03-01 mitigation proof: untrusted census text (quotes, SQL fragments,
    # newlines, CJK) flows through parameterized placeholders inertly and can
    # never alter the schema.
    evil_name = "Rob'); DROP TABLE agents;--"
    evil_tagline = 'line1\nline2 with "double quotes", commas, and CJK: 这个能吃吗？'
    rec = make_record(
        id="6666", name=evil_name, name_key=evil_name, tagline=evil_tagline
    )
    upsert_agent(conn, rec, captured_at="2026-07-10T00:00:00Z")

    # (a) the agents table survived the "injection"
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "agents" in tables

    # (b) byte-identical round-trip of both hostile fields
    row = conn.execute(
        "SELECT name, tagline FROM agents WHERE id = ?", ("6666",)
    ).fetchone()
    assert row["name"] == evil_name
    assert row["tagline"] == evil_tagline

    # (c) a second unrelated upsert still works afterwards
    upsert_agent(conn, make_record(id="7777"), captured_at="2026-07-10T00:00:00Z")
    assert conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0] == 2


def test_snapshot_rerun_duplicates_by_design(conn):
    # locked behavior — rerunning refresh duplicates snapshots on purpose;
    # do NOT "fix" by deduplicating (research Open Question 3).
    rec = make_record(id="8888")
    upsert_agent(conn, rec, captured_at="2026-07-10T00:00:00Z")
    insert_snapshot(conn, rec, captured_at="2026-07-10T00:00:00Z")
    insert_snapshot(conn, rec, captured_at="2026-07-10T00:00:00Z")
    count = conn.execute(
        "SELECT COUNT(*) FROM snapshots WHERE agent_id = ?", ("8888",)
    ).fetchone()[0]
    assert count == 2


def test_upsert_updates_all_mutable_fields(conn):
    upsert_agent(
        conn,
        make_record(id="5555", category="Trading & DeFi", rating=None),
        captured_at="2026-07-10T00:00:00Z",
    )
    upsert_agent(
        conn,
        make_record(
            id="5555",
            category="Security & Trust",
            category_source="listed",
            rating=4.5,
        ),
        captured_at="2026-07-11T00:00:00Z",
    )
    row = conn.execute("SELECT * FROM agents WHERE id = ?", ("5555",)).fetchone()
    assert row["category"] == "Security & Trust"
    assert row["category_source"] == "listed"
    assert row["rating"] == 4.5
    assert row["first_seen"] == "2026-07-10T00:00:00Z"  # never overwritten


def test_connect_creates_missing_parent_dir(tmp_path):
    db_file = tmp_path / "nested" / "dir" / "t.db"
    c = connect(db_file)
    init_db(c)
    assert db_file.exists()
    c.close()
