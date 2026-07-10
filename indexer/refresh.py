"""Refresh pipeline: census CSV -> SQLite. Entry point: python -m indexer.refresh

Offline by design: the pipeline reads a local CSV and writes a local SQLite
file with zero network access (INDX-01).

Determinism: captured_at is always injected. The CLI derives its default from
the YYYY-MM-DD date in the csv filename (seed baseline 2026-07-10T00:00:00Z);
tests pass it explicitly. Seed data never falls back to the wall clock.

Exit codes: 0 success, 1 missing/unreadable csv, 2 captured-at underivable.
"""
from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from indexer.census import load_census
from indexer.db import connect, init_db, insert_snapshot, upsert_agent
from indexer.models import AgentRecord

log = logging.getLogger("indexer.refresh")

__all__ = ["DEFAULT_CSV", "DEFAULT_DB", "RefreshSummary", "persist", "refresh", "main"]

DEFAULT_CSV = Path("data/okx-marketplace-census-2026-07-10.csv")
DEFAULT_DB = Path("data/trustlens.db")

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


def refresh(
    csv_path: str | Path,
    db_path: str | Path,
    captured_at: str,
    source: str = "census",
) -> RefreshSummary:
    """Load the census and persist agents + snapshots in one atomic transaction."""
    records, warnings = load_census(csv_path)
    conn = connect(db_path)
    try:
        init_db(conn)
        with conn:  # one atomic transaction for the whole load
            persist(conn, records, captured_at, source)
    finally:
        conn.close()  # clean close also removes the WAL sidecar files
    return RefreshSummary(
        agents=len(records),
        snapshots_appended=len(records),
        field_warnings=warnings,
        source=source,
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

    try:
        summary = refresh(csv_path, args.db, captured_at)
    except OSError as exc:
        log.error("failed to read census csv %s: %s", csv_path, exc)
        return 1

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
