"""Refresh pipeline: census CSV -> SQLite. Entry point: python -m indexer.refresh

Offline by design: the pipeline reads a local CSV and writes a local SQLite
file with zero network access (INDX-01). Each load also computes trust
scores for every agent and persists them in the same atomic transaction as
agents and snapshots (Phase 2 precompute-on-refresh).

Determinism: captured_at is always injected. The CLI derives its default from
the YYYY-MM-DD date in the csv filename (seed baseline 2026-07-10T00:00:00Z);
tests pass it explicitly. Seed data never falls back to the wall clock.

Exit codes: 0 success; 1 missing/unreadable/undecodable csv (data problem);
2 captured-at underivable, database failure, or leaderboard build failure
(environment problem).
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sqlite3
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from indexer.census import load_census
from indexer.db import connect, init_db, insert_snapshot, upsert_agent
from indexer.models import AgentRecord
from scoring import SCORE_VERSION, compute_all
from web.build import build as web_build

log = logging.getLogger("indexer.refresh")

__all__ = [
    "DEFAULT_CSV",
    "DEFAULT_DB",
    "DEFAULT_WEB_OUT",
    "RefreshSummary",
    "persist",
    "merge",
    "refresh",
    "main",
]

DEFAULT_CSV = Path("data/okx-marketplace-census-2026-07-10.csv")
DEFAULT_DB = Path("data/trustlens.db")
DEFAULT_WEB_OUT = Path("web/dist/index.html")

_FILENAME_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class RefreshSummary:
    """What one refresh run did, for the summary log line and tests."""

    agents: int
    snapshots_appended: int
    field_warnings: int
    source: str


def persist(
    conn: sqlite3.Connection,
    records: Iterable[AgentRecord],
    captured_at: str,
    source: str = "census",
) -> None:
    """THE Phase 5 scraper seam: any loader producing AgentRecords calls this
    same path with its own source tag (source="scrape" later). Caller manages
    the transaction — nothing here commits.
    """
    for rec in records:
        upsert_agent(conn, rec, captured_at)
        insert_snapshot(conn, rec, captured_at, source)


def merge(
    census: list[AgentRecord], scraped: list[AgentRecord]
) -> list[AgentRecord]:
    """Census is the floor; a scraped record wins only for an id it parsed.

    Ids present only in the census stand unchanged; the (bounded, possibly
    empty) scraped list overrides matching ids and appends any new ones. When
    the scraper yields nothing (every failure path -> []), the census records
    flow through byte-identically — the offline-determinism guarantee.
    """
    by_id = {r.id: r for r in census}
    for s in scraped:
        by_id[s.id] = s
    return list(by_id.values())


def _persist_records(
    db_path: str | Path,
    records: list[AgentRecord],
    field_warnings: int,
    captured_at: str,
    source: str = "census",
    generated_at: str | None = None,
    web_out: Path | None = None,
) -> RefreshSummary:
    """DB stage of a refresh: open, init, persist atomically, summarize.

    Split from the CSV stage so main() can attribute a failure to its side
    of the pipeline unambiguously: csv-side -> exit 1, db-side -> exit 2.
    """
    gen_at = captured_at if generated_at is None else generated_at
    conn = connect(db_path)
    try:
        init_db(conn)
        with conn:  # one atomic transaction for the whole load
            persist(conn, records, captured_at, source)
            scored, not_rated = compute_all(conn, gen_at, captured_at)
    finally:
        conn.close()  # clean close also removes the WAL sidecar files
    log.info(
        "scores computed: %d scored, %d not rated, version=%s",
        scored, not_rated, SCORE_VERSION,
    )
    if web_out is not None:
        size = web_build(
            db_path, web_out,
            base_url=os.environ.get("TRUSTLENS_BASE_URL", "http://localhost:8000"),
        )
        log.info(
            "leaderboard built: %s (%d agents, %d bytes)", web_out, len(records), size
        )
    return RefreshSummary(
        agents=len(records),
        snapshots_appended=len(records),
        field_warnings=field_warnings,
        source=source,
    )


def refresh(
    csv_path: str | Path,
    db_path: str | Path,
    captured_at: str,
    source: str = "census",
    generated_at: str | None = None,
    web_out: Path | None = None,
) -> RefreshSummary:
    """Load the census; persist agents + snapshots + scores in one atomic transaction."""
    records, warnings = load_census(csv_path)
    return _persist_records(
        db_path, records, warnings, captured_at, source,
        generated_at=generated_at, web_out=web_out,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI: resolve paths and captured_at, run the refresh, log one summary line."""
    try:
        # cp1252 consoles crash on CJK ids/names (research Pitfall 6); console
        # setup must never take down the refresh itself.
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        prog="python -m indexer.refresh",
        description="Populate the TrustLens SQLite database from the census "
        "CSV (offline: zero network access).",
    )
    parser.add_argument(
        "--csv", type=Path, default=DEFAULT_CSV,
        help=f"census csv path (default: {DEFAULT_CSV})",
    )
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB,
        help=f"sqlite database path (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--captured-at", default=None,
        help="ISO-8601 UTC timestamp for this load "
        "(default: derived from the YYYY-MM-DD date in the csv filename)",
    )
    parser.add_argument(
        "--generated-at", default=None,
        help="ISO-8601 UTC timestamp stamped on score rows as generated_at "
        "(default: same as captured-at, keeping reruns byte-identical)",
    )
    parser.add_argument(
        "--web-out", type=Path, default=DEFAULT_WEB_OUT,
        help=f"leaderboard html output path (default: {DEFAULT_WEB_OUT})",
    )
    parser.add_argument(
        "--scrape", action="store_true",
        help="also enrich from okx.ai detail pages (bounded demo set; politely, "
        "cached; falls back to census on any failure)",
    )
    args = parser.parse_args(argv)

    csv_path: Path = args.csv
    if not csv_path.is_file():
        log.error("census csv not found: %s", csv_path)
        return 1

    captured_at: str | None = args.captured_at
    if captured_at is None:
        m = _FILENAME_DATE.search(csv_path.name)
        if m is None:
            log.error(
                "cannot derive captured-at: filename %r carries no YYYY-MM-DD "
                "date — pass --captured-at explicitly (seed data never falls "
                "back to the wall clock)",
                csv_path.name,
            )
            return 2
        captured_at = f"{m.group(0)}T00:00:00Z"

    # Two stages, two exit codes: csv-side failures are data problems (1),
    # db-side failures are environment problems (2) — see module docstring.
    # An undecodable file or an over-limit cell (csv.field_size_limit,
    # T-04-04) is an unreadable csv by the same definition as a missing one.
    try:
        records, field_warnings = load_census(csv_path)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        log.error("failed to read census csv %s: %s", csv_path, exc)
        return 1

    if args.scrape:
        # Import locally so the default (offline) path never loads the scraper.
        # scrape_agents swallows every failure and returns [] -> no try/except
        # needed here and the 0/1/2 exit contract stays driven by csv/db only.
        from indexer.scraper import DEMO_AGENT_IDS, detail_url, scrape_agents

        scraped = scrape_agents([detail_url(i) for i in DEMO_AGENT_IDS])
        records = merge(records, scraped)
        log.info("scrape enrichment: %d record(s) merged", len(scraped))

    try:
        summary = _persist_records(
            args.db, records, field_warnings, captured_at,
            generated_at=args.generated_at, web_out=args.web_out,
        )
    except (OSError, sqlite3.Error) as exc:
        log.error("database error at %s: %s", args.db, exc)
        return 2

    log.info(
        "refresh complete: %d agents, %d snapshots appended, "
        "%d field warning(s), source=%s",
        summary.agents,
        summary.snapshots_appended,
        summary.field_warnings,
        summary.source,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
