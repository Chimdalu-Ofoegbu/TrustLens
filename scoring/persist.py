"""Score persistence: compute every agent's card and rewrite the scores table.

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
    """Score every agent and rewrite the scores table. Returns (scored, not_rated).

    History = distinct capture times: the real DB holds duplicate snapshot
    rows per capture time by design — raw row counts would fabricate history.
    DELETE+INSERT is self-cleaning: agents absent from a future census leave
    no stale score rows.
    """
    rows = [dict(r) for r in conn.execute("SELECT * FROM agents ORDER BY id")]
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
