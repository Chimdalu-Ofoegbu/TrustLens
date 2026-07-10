---
phase: 01-foundation-data-indexer
plan: 04
subsystem: indexer
tags: [python, csv, sqlite, argparse, logging, cli, integration-tests]

# Dependency graph
requires:
  - phase: 01-foundation-data-indexer (plan 01)
    provides: AgentRecord contract + the four census field parsers (parse_sold, parse_price, parse_rating_positive, name_key)
  - phase: 01-foundation-data-indexer (plan 02)
    provides: derive_category 9-bucket first-match-wins table with pinned 272-row distribution
  - phase: 01-foundation-data-indexer (plan 03)
    provides: connect/init_db/upsert_agent/insert_snapshot (write helpers never commit; caller owns transaction)
provides:
  - indexer/census.py — load_census(csv_path) -> (list[AgentRecord], warning_count); csv + parse + category wiring with row-number+id-only warnings
  - indexer/refresh.py — persist() source-tagged Phase 5 seam, one-transaction refresh(), argparse main() with filename-derived captured_at and 0/1/2 exit codes
  - tests/test_refresh.py — 10-test full-census integration proof (272 offline, 272/544 rerun, 11 exact fixture rows, aggregates, distribution, CLI paths)
  - Working `python -m indexer.refresh` entry point populating data/trustlens.db (INDX-01 verbatim)
affects: [scoring, server, scraper, verification, 02-phase, 03-phase, 05-phase]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Source-tagged persist() seam: any loader producing AgentRecords calls the same upsert+snapshot path with its own source tag (Phase 5 scraper passes source='scrape')"
    - "Filename-derived captured_at default: seed data never reads the wall clock; dateless filename without --captured-at is a hard exit 2"
    - "CLI exit-code contract: 0 success, 1 missing/unreadable csv, 2 captured-at underivable — missing-csv check runs first"

key-files:
  created:
    - indexer/census.py
    - indexer/refresh.py
    - tests/test_refresh.py
  modified:
    - .gitignore

key-decisions:
  - "Explicit logger names ('indexer.census', 'indexer.refresh') instead of __name__ — under `python -m indexer.refresh` __name__ is '__main__', which would destabilize the summary-line format and the caplog assertions"
  - "Missing-CSV check ordered before the dateless-filename check so `--csv data/does-not-exist.csv` exits 1, not 2 (the plan's own test expectations imply this precedence)"

patterns-established:
  - "persist() is THE cross-source persistence path: Phase 5 adds a scrape loader, not a second writer"
  - "Integration tests share one module-scoped refresh of the real census and treat the connection as read-only"

requirements-completed: [INDX-01, INDX-02, INDX-03]

# Metrics
duration: 10min
completed: 2026-07-10
---

# Phase 1 Plan 04: Census Loader & Refresh CLI Summary

**Bare `python -m indexer.refresh` loads all 272 census agents into SQLite offline with the deterministic 2026-07-10T00:00:00Z seed timestamp, proven by a 10-test full-census integration suite pinning every research-verified edge value and the 272-agents/544-snapshots rerun contract**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-10T22:17:23Z
- **Completed:** 2026-07-10T22:29:01Z
- **Tasks:** 2
- **Files modified:** 4 (3 created + .gitignore)

## Accomplishments

- INDX-01 verbatim: `python -m indexer.refresh` exits 0 with zero network access and logs `refresh complete: 272 agents, 272 snapshots appended, 1 field warning(s), source=census`; data/trustlens.db holds exactly 272 agents, every one with a non-empty derived category
- Rerun proven idempotent for agents and append-only for snapshots: second run keeps exactly 272 agents (no dupes/corruption), preserves first_seen, updates last_seen, and appends 272 more snapshots (544 total) — pinned so nobody "fixes" the by-design duplication
- All 11 edge-case fixture rows store their exact verified values end-to-end: 3118 sold=1550 (K-suffix), 2023 price=0.000015 (subscript, never the 10x off-by-one), 2013/4489/3091 rating NULL (price echoes incl. the fake perfect '5'), 4137 sold=0 with the load's single warning, 2169 rating 5.0 with pct NULL (rule A), 2791 rated with empty price, 3345 CJK name + folded name_key, 1500 multiline tagline intact
- Aggregate invariants locked: 28 price NULLs, 90 rated, 89 with positive_pct, 151 zero-sold, MAX(sold)=1550, all category_source='derived', all snapshot source='census', full 9-bucket distribution equality
- persist() ships as the documented Phase 5 scraper seam (source-tagged, caller-owned transaction) with zero scraper code in this phase
- Warning hygiene proven: exactly 1 warning on the census load, message carries row number + id 4137 only, no cell text (log-injection + cp1252 safe)
- Full phase suite green: 71 passed (36 parse + 14 category + 11 db + 10 refresh)

## Task Commits

Each task was committed atomically:

1. **Task 1: census.py loader + refresh.py orchestrator/CLI (with the Phase 5 seam)** - `a8fb201` (feat)
2. **Task 2: Full-census integration suite — the phase proof** - `895d2a5` (test)

**Plan metadata:** docs commit (this summary + state/roadmap/requirements)

## Files Created/Modified

- `indexer/census.py` - load_census: DictReader over utf-8-sig, per-field strip (internal newlines preserved), sold-prose -> 0 + warning, defensive price warning path, rating rule A, category derivation; warnings carry row+id only
- `indexer/refresh.py` - RefreshSummary, persist() seam, refresh() with one atomic transaction and clean close (WAL sidecars removed), argparse main() with filename-derived captured_at, exact summary log line, exit codes 0/1/2
- `tests/test_refresh.py` - 10 integration tests against the real census: full load, rerun 272/544, 11 exact fixture rows, aggregates + distribution, name_key collision persistence (2791/2662), snapshot content, warning hygiene, CLI exit paths
- `.gitignore` - appended `*.db-wal` / `*.db-shm` under Runtime artifacts (sidecars survive abnormal exits; `*.db` does not match them)

## Decisions Made

- Explicit logger names (`indexer.census`, `indexer.refresh`) instead of `__name__`: running as `python -m indexer.refresh` makes `__name__` = `__main__`, which would change the logged summary line's logger field and break the "indexer.census" caplog contract. Explicit names keep both stable under every invocation style.
- Missing-CSV check precedes the dateless-filename check in main(): `--csv data/does-not-exist.csv` (dateless AND missing) must exit 1 per the plan's test 9, so file existence is validated before captured-at derivation.
- `_cell()` helper returns `""` for missing/short-row fields: honors the locked "never raise on field content" rule even for hypothetical malformed rows; behavior on the real file is identical to direct access.

## Deviations from Plan

None - plan executed exactly as written.

## Authentication Gates

None - fully offline plan (local CSV -> local SQLite).

## Known Stubs

None - no placeholders, TODOs, or unwired paths; every code path is exercised by the suite.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 1 complete: 4/4 plans done, INDX-01/02/03 all marked complete — ready for `/gsd-verify-work 1` and Phase 2 planning
- Phase 2 scoring receives its inputs exactly as designed: refresh.py can hand scoring a connection; the additive DDL tuple in db.py takes the scores table without migrations (keep the uppercase constraint-literal out of new SQL comments — the 01-03 grep gate wording rule still applies)
- Phase 5 scraper seam is live and documented: a scrape loader produces AgentRecords and calls persist(conn, records, captured_at, source="scrape"); category_source='listed' update already proven in 01-03 tests
- data/trustlens.db regenerates from the bare command on any checkout; census CSV remains byte-identical (read-only input)

## Self-Check: PASSED

- FOUND: indexer/census.py (93 lines >= 50), indexer/refresh.py (155 lines >= 70), tests/test_refresh.py (284 lines >= 90)
- FOUND: commit a8fb201 (feat, Task 1), commit 895d2a5 (test, Task 2)
- All 9 Task-1 and all 6 Task-2 acceptance criteria re-verified PASS (bare run "272 agents" x1 exit 0; 272 agents / 0 empty categories in db; exit=1 missing csv; network-import grep 0; wall-clock grep 0; persist def x1; db-wal x1; data/ porcelain clean; suite exit 0; 544/0.000015/1550 pins present)
- Plan-level verification re-run: `python -m pip install -e ".[dev]"` exit 0, `python -m pytest -q` -> 71 passed exit 0, bare refresh reports 272 agents, zero network imports in indexer/
- data/okx-marketplace-census-2026-07-10.csv byte-identical (git porcelain clean)

---
*Phase: 01-foundation-data-indexer*
*Completed: 2026-07-10*
