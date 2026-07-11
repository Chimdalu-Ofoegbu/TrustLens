"""Read-only DB access for the MCP tools. Connection-per-call; never writes.

Locked rules honored here (03-CONTEXT "App composition"):

- This module NEVER writes and NEVER recomputes scores — every value is
  SELECTed from the agents/scores tables that indexer.refresh populated.
- Timestamps (generated_at / data_as_of) are SERVED from storage, never the
  wall clock — the MCPS-02 determinism guarantee rides on this.
- Every query is parameterized with ``?`` placeholders; no f-string SQL ever
  (repo-locked convention; STRIDE T-03-05).
"""
from __future__ import annotations

import sqlite3
import statistics
from pathlib import Path

from indexer.parse import name_key

__all__ = [
    "DEFAULT_DB",
    "CARD_SELECT",
    "connect_ro",
    "lookup_agent",
    "closest_candidates",
    "category_slice",
    "category_total",
    "stats",
    "envelope_values",
]

DEFAULT_DB = Path("data/trustlens.db")

CARD_SELECT = (
    "SELECT a.id, a.name, a.category, a.tagline, a.price_usdt, a.sold, a.rating,"
    " a.positive_pct, s.score, s.grade, s.confidence, s.score_version,"
    " s.generated_at, s.data_as_of, s.components"
    " FROM agents a JOIN scores s ON s.agent_id = a.id"
)


def connect_ro(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    """Open ``db_path`` read-only via a mode=ro URI.

    Research-verbatim: ``as_uri()`` percent-encodes the spaces in this
    repo's absolute path, so the URI form is safe on this machine.
    """
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def lookup_agent(
    conn: sqlite3.Connection, query: str
) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    """The locked lookup ladder: id exact -> name exact -> NFKC name_key.

    Returns ``(row, ambiguous)``. When 2+ rows share the matched name or
    name_key, the LOWEST id wins deterministically and ALL matches come
    back in ``ambiguous`` for disclosure (the real census holds exactly 2
    name_key collisions; name_key has NO uniqueness constraint by design).
    """
    row = conn.execute(CARD_SELECT + " WHERE a.id = ?", (query,)).fetchone()
    if row is not None:
        return row, []

    rows = conn.execute(
        CARD_SELECT + " WHERE a.name = ? ORDER BY a.id", (query,)
    ).fetchall()
    if len(rows) == 1:
        return rows[0], []
    if len(rows) >= 2:  # defensive; raw names collide for the same 2 pairs
        return rows[0], rows

    rows = conn.execute(
        CARD_SELECT + " WHERE a.name_key = ? ORDER BY a.id", (name_key(query),)
    ).fetchall()
    if len(rows) == 1:
        return rows[0], []
    if len(rows) >= 2:
        return rows[0], rows
    return None, []


def closest_candidates(
    conn: sqlite3.Connection, query: str, limit: int = 3
) -> list[sqlite3.Row]:
    """Deterministic not-found suggestions: name_key prefix matches.

    LIKE wildcards in the user input are escaped so ``%``/``_`` probe as
    literals (STRIDE T-03-05). Returns ``(id, name)`` rows; may be empty.
    """
    q = (
        name_key(query)
        .replace("\\", "\\\\")
        .replace("%", r"\%")
        .replace("_", r"\_")
    )
    return conn.execute(
        "SELECT id, name FROM agents WHERE name_key LIKE ? ESCAPE '\\'"
        " ORDER BY id LIMIT ?",
        (q + "%", limit),
    ).fetchall()


def category_slice(
    conn: sqlite3.Connection, category: str, limit: int
) -> list[sqlite3.Row]:
    """Scored agents in one category, best score first (NR rows excluded)."""
    return conn.execute(
        "SELECT a.id, a.name, s.score, s.grade, s.confidence"
        " FROM agents a JOIN scores s ON s.agent_id = a.id"
        " WHERE a.category = ? AND s.score IS NOT NULL"
        " ORDER BY s.score DESC, a.id LIMIT ?",
        (category, limit),
    ).fetchall()


def category_total(conn: sqlite3.Connection, category: str) -> int:
    """All agents in the category, scored and not-rated alike."""
    return conn.execute(
        "SELECT COUNT(*) FROM agents WHERE category = ?", (category,)
    ).fetchone()[0]


def stats(conn: sqlite3.Connection) -> dict:
    """Aggregate marketplace numbers, computed via SQL over agents+scores."""
    agents_total = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    scored = conn.execute(
        "SELECT COUNT(*) FROM scores WHERE score IS NOT NULL"
    ).fetchone()[0]
    not_rated = conn.execute(
        "SELECT COUNT(*) FROM scores WHERE score IS NULL"
    ).fetchone()[0]
    grade_distribution = {
        r["grade"]: r["n"]
        for r in conn.execute(
            "SELECT grade, COUNT(*) AS n FROM scores GROUP BY grade ORDER BY grade"
        )
    }
    category_counts = {
        r["category"]: r["n"]
        for r in conn.execute(
            "SELECT category, COUNT(*) AS n FROM agents"
            " GROUP BY category ORDER BY category"
        )
    }
    prices = [
        r[0]
        for r in conn.execute(
            "SELECT price_usdt FROM agents WHERE price_usdt IS NOT NULL"
            " ORDER BY price_usdt"
        )
    ]
    median_price = float(statistics.median(prices)) if prices else None
    return {
        "agents_total": agents_total,
        "scored": scored,
        "not_rated": not_rated,
        "grade_distribution": grade_distribution,
        "category_counts": category_counts,
        "median_price_usdt": median_price,
    }


def envelope_values(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """One (score_version, generated_at, data_as_of) row for tools 2-4.

    All score rows share a single version/timestamp pair (verified against
    the refresh pipeline); returns None when the scores table is empty.
    """
    return conn.execute(
        "SELECT score_version, MAX(generated_at) AS generated_at,"
        " MAX(data_as_of) AS data_as_of FROM scores"
        " GROUP BY score_version LIMIT 1"
    ).fetchone()
