"""SQLite persistence for the TrustLens indexer (INDX-03).

The SQLite FILE is the cross-phase interface: this module (the only writer)
populates it, Phase 2 scoring receives a connection from refresh.py, and the
Phase 3 server opens the file read-only. No other package imports indexer.db.

Locked semantics honored here:
- Timestamps are ISO-8601 TEXT strings supplied by callers. This module never
  reads the wall clock and never accepts datetime objects (implicit sqlite3
  adapters are deprecated since Python 3.12).
- Parameterized ``?`` placeholders exclusively — agent names and taglines
  carry quotes, SQL fragments, newlines, and CJK text.
- DDL is an additive tuple of CREATE ... IF NOT EXISTS statements; Phase 2
  appends its scores table to this tuple without migration machinery.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from indexer.models import AgentRecord

__all__ = ["connect", "init_db", "upsert_agent", "insert_snapshot"]

# Schema notes (locked/verified against the real 272-row census):
# - name_key deliberately has NO uniqueness constraint: the real census holds
#   2 collisions (链上任务助手 ids 2791+2662; 人生说明书 · life book ids
#   4517+4353) — enforcing uniqueness would crash refresh on real data.
# - category_source: 'derived' now; 'listed' once the Phase 5 scraper finds
#   the real listed category.
# - snapshots.source: 'census' now, 'scrape' in Phase 5 (the scraper seam).
# - price_usdt REAL NULL (28 real rows), rating REAL NULL (182 rows),
#   positive_pct REAL NULL (183 rows).
DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS agents (
        id              TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        name_key        TEXT NOT NULL,
        category        TEXT NOT NULL,
        category_source TEXT NOT NULL DEFAULT 'derived',
        tagline         TEXT,
        price_usdt      REAL,
        price_raw       TEXT,
        sold            INTEGER NOT NULL DEFAULT 0,
        rating          REAL,
        positive_pct    REAL,
        first_seen      TEXT NOT NULL,
        last_seen       TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_agents_name_key ON agents(name_key)",
    "CREATE INDEX IF NOT EXISTS idx_agents_category ON agents(category)",
    """
    CREATE TABLE IF NOT EXISTS snapshots (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id     TEXT NOT NULL REFERENCES agents(id),
        captured_at  TEXT NOT NULL,
        price_usdt   REAL,
        sold         INTEGER,
        rating       REAL,
        positive_pct REAL,
        source       TEXT NOT NULL DEFAULT 'census'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_snapshots_agent ON snapshots(agent_id, captured_at)",
    # scores: Phase 2 trust scores. one row per agent via primary key; score is
    # NULL for grade='NR' rows — insufficient evidence is a valid, successful state.
    """
    CREATE TABLE IF NOT EXISTS scores (
        agent_id      TEXT PRIMARY KEY REFERENCES agents(id),
        score         INTEGER,
        grade         TEXT NOT NULL,
        confidence    TEXT NOT NULL,
        score_version TEXT NOT NULL,
        generated_at  TEXT NOT NULL,
        data_as_of    TEXT NOT NULL,
        components    TEXT NOT NULL
    )
    """,
)

# first_seen is intentionally absent from the DO UPDATE SET list below — it
# is preserved on conflict while every other mutable field takes the new
# value (research-verified statement; SQLite >= 3.24 everywhere).
UPSERT_AGENT = """
INSERT INTO agents (id, name, name_key, category, category_source, tagline,
                    price_usdt, price_raw, sold, rating, positive_pct,
                    first_seen, last_seen)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    name=excluded.name, name_key=excluded.name_key,
    category=excluded.category, category_source=excluded.category_source,
    tagline=excluded.tagline, price_usdt=excluded.price_usdt,
    price_raw=excluded.price_raw, sold=excluded.sold,
    rating=excluded.rating, positive_pct=excluded.positive_pct,
    last_seen=excluded.last_seen
"""

_INSERT_SNAPSHOT = (
    "INSERT INTO snapshots (agent_id, captured_at, price_usdt, sold, rating,"
    " positive_pct, source) VALUES (?, ?, ?, ?, ?, ?, ?)"
)


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open the database, creating the parent directory and file if absent.

    Enables WAL journaling plus foreign-key enforcement (off by default in
    sqlite3), and installs sqlite3.Row so readers access columns by name.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Additive, idempotent: every DDL statement is CREATE ... IF NOT EXISTS."""
    for stmt in DDL:
        conn.execute(stmt)
    conn.commit()


def upsert_agent(
    conn: sqlite3.Connection, rec: AgentRecord, captured_at: str
) -> None:
    """Insert or update one agent; first_seen survives, last_seen refreshes.

    Does NOT commit — the caller (refresh.py, plan 04) wraps the whole load
    in one transaction via ``with conn:`` for atomicity.
    """
    conn.execute(
        UPSERT_AGENT,
        (rec.id, rec.name, rec.name_key, rec.category, rec.category_source,
         rec.tagline, rec.price_usdt, rec.price_raw, rec.sold, rec.rating,
         rec.positive_pct, captured_at, captured_at),
    )


def insert_snapshot(
    conn: sqlite3.Connection,
    rec: AgentRecord,
    captured_at: str,
    source: str = "census",
) -> None:
    """Append one time-series row. Always appends: rerunning a refresh with
    the same captured_at duplicates rows by design (locked behavior).

    Does NOT commit — see upsert_agent.
    """
    conn.execute(
        _INSERT_SNAPSHOT,
        (rec.id, captured_at, rec.price_usdt, rec.sold, rec.rating,
         rec.positive_pct, source),
    )
