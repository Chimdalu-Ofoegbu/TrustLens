"""Score persistence: compute every currently-listed agent's card and rewrite the scores table.

The only scoring module that touches sqlite3. Never commits — the caller
(indexer.refresh) wraps agents+snapshots+scores in one atomic transaction.
"""
from __future__ import annotations

import sqlite3

from scoring.engine import SCORE_VERSION, score_agent, serialize_components
from scoring.stats import build_stats

__all__ = ["compute_all"]

INSERT_SCORE = (
    "INSERT INTO scores (agent_id, score, grade, confidence, score_version,"
    " generated_at, data_as_of, components) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)


def compute_all(
    conn: sqlite3.Connection, generated_at: str, data_as_of: str
) -> tuple[int, int]:
    """Score agents observed in the current capture; rewrite the scores table.

    Returns (scored, not_rated).

    Only rows with last_seen = data_as_of are scored: agents are never
    deleted (the pipeline only upserts), so an agent absent from the
    current census keeps a stale agents row — re-scoring it would stamp a
    data_as_of from a snapshot in which the agent was never observed.
    The filter also makes DELETE+INSERT genuinely self-cleaning: delisted
    agents leave no score rows at all, and benchmark stats are built from
    the current capture only.

    History = distinct capture times: the real DB holds duplicate snapshot
    rows per capture time by design — raw row counts would fabricate history.
    """
    rows = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM agents WHERE last_seen = ? ORDER BY id", (data_as_of,)
        )
    ]
    snap = dict(conn.execute(
        "SELECT agent_id, COUNT(DISTINCT captured_at) FROM snapshots GROUP BY agent_id"
    ))
    stats = build_stats(rows)
    conn.execute("DELETE FROM scores")
    scored = not_rated = 0
    for row in rows:
        card = score_agent(row, stats, snap.get(row["id"], 0))
        if card["grade"] == "NR":
            not_rated += 1
        else:
            scored += 1
        conn.execute(
            INSERT_SCORE,
            (row["id"], card["score"], card["grade"], card["confidence"],
             SCORE_VERSION, generated_at, data_as_of,
             serialize_components(card["components"])),
        )
    return scored, not_rated
