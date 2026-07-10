---
phase: 01-foundation-data-indexer
plan: 03
subsystem: database
tags: [sqlite, wal, upsert, on-conflict, stdlib, python]

# Dependency graph
requires:
  - phase: 01-foundation-data-indexer (plan 01)
    provides: AgentRecord frozen dataclass contract (indexer/models.py)
provides:
  - indexer/db.py — additive DDL tuple (agents + snapshots + 3 indexes), connect() with WAL + foreign_keys + Row factory, idempotent init_db, first_seen-preserving upsert_agent, source-tagged insert_snapshot
  - tests/test_db.py — 11 tests covering schema, WAL, upsert idempotency, name_key collision, FK enforcement, hostile-content injection round-trip, by-design snapshot duplication
affects: [01-04 refresh pipeline, phase-2 scoring (appends scores table to DDL, receives connection), phase-3 server (opens DB read-only), phase-5 scraper (source='scrape' seam)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive DDL tuple of CREATE ... IF NOT EXISTS — later phases append statements, no migration machinery"
    - "connect() enables WAL + foreign_keys per connection; sqlite3.Row factory for name-based column access"
    - "Write helpers never commit — caller owns the transaction (with conn:) for whole-load atomicity"
    - "ISO-8601 TEXT timestamps injected by callers; no wall-clock reads, no datetime objects into sqlite3"
    - "Parameterized ? placeholders exclusively; grep gates forbid f-string SQL"

key-files:
  created: [indexer/db.py, tests/test_db.py]
  modified: []

key-decisions:
  - "db.py comments spell 'unique/uniqueness' in lowercase: the plan's acceptance gate (grep -cE 'UNIQUE' = 0) outranked its suggested comment phrasing 'NO UNIQUE constraint' — collision rationale stays documented, gate stays green (Phase 2 DDL edits must keep this)"
  - "test_upsert_updates_all_mutable_fields flips category_source 'derived'->'listed' on the second upsert — proves the Phase 5 scraper's field actually updates on conflict"

patterns-established:
  - "Additive DDL: Phase 2 appends its scores CREATE TABLE to the DDL tuple in db.py"
  - "Caller-owned transactions: refresh.py (plan 04) wraps upserts + snapshots in one `with conn:` block"
  - "Snapshot reruns duplicate rows by design — pinned by test comment so nobody 'fixes' it"

requirements-completed: [INDX-03]

# Metrics
duration: 7min
completed: 2026-07-10
---

# Phase 1 Plan 03: SQLite Persistence Layer Summary

**SQLite persistence with WAL + FK enforcement and an ON CONFLICT(id) upsert that preserves first_seen — injection round-trip proven byte-identical against hostile census content (quotes, SQL fragments, newlines, CJK)**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-10T22:05:28Z
- **Completed:** 2026-07-10T22:12:54Z
- **Tasks:** 2 (task 1 executed as TDD: RED -> GREEN)
- **Files modified:** 2

## Accomplishments

- Locked schema landed exactly: agents (13 columns incl. name_key with NO uniqueness constraint, category_source, price_raw) + snapshots (source-tagged time series) + idx_agents_name_key / idx_agents_category / idx_snapshots_agent
- Idempotent upsert proven: rerun keeps exactly 1 row per id, first_seen survives, last_seen and every mutable field refresh (`first_seen` intentionally absent from DO UPDATE SET)
- T-03-01 mitigated and proven: `"Rob'); DROP TABLE agents;--"` and a multiline CJK tagline round-trip byte-identical through parameterized placeholders; schema intact; connection reusable afterwards
- Real-data safety pinned: name_key collision (census ids 2791/2662, 链上任务助手) persists both rows; FK violation raises IntegrityError; snapshot rerun duplication locked as by-design
- Whole suite green: 61 tests (50 from plans 01/02 + 11 new)

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): failing persistence tests** - `7325cec` (test)
2. **Task 1 (GREEN): implement sqlite persistence** - `d774c1f` (feat)
3. **Task 2: hardening tests (collisions, FK, hostile content)** - `b90d672` (test)

**Plan metadata:** see final docs commit

## Files Created/Modified

- `indexer/db.py` - DDL tuple, connect() (parent-dir creation, WAL, foreign_keys, Row factory), init_db, UPSERT_AGENT statement, upsert_agent, insert_snapshot; 145 lines, stdlib only
- `tests/test_db.py` - 11 behavior + hardening tests using pytest tmp_path; synthetic AgentRecord factory with per-test overrides

## Decisions Made

- Lowercase "unique/uniqueness" wording in db.py comments: the plan's own acceptance criterion `grep -cE "UNIQUE" indexer/db.py` = 0 conflicted with its suggested comment text "NO UNIQUE constraint"; the gate won. The collision rationale (census ids 2791+2662, 4517+4353) remains fully documented in the schema notes. Phase 2 must not introduce the uppercase literal when appending the scores table.
- `category_source="listed"` used in the mutable-fields test's second upsert to prove category_source updates on conflict (plan required "row shows the new category, category_source, rating" — changing the value is the only way to prove the update).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Authentication Gates

None - fully offline, stdlib-only work.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Persistence contract complete for plan 01-04 (refresh.py): connect -> init_db -> `with conn:` -> upsert_agent + insert_snapshot per row
- Phase 2 seam ready: scoring appends its scores CREATE TABLE to the DDL tuple and receives a live connection
- Phase 5 seam ready: insert_snapshot(source="scrape") and category_source='listed' both proven to work
- No blockers

## Self-Check: PASSED

- FOUND: indexer/db.py (145 lines >= 70)
- FOUND: tests/test_db.py (211 lines >= 70)
- FOUND: commit 7325cec (test - RED)
- FOUND: commit d774c1f (feat - GREEN)
- FOUND: commit b90d672 (test - hardening)
- All 8 Task-1 and all 4 Task-2 acceptance criteria re-verified PASS
- Plan verification re-run: suite exit 0 (61 passed), sqlite 3.50.4 >= 3.24, wall-clock grep = 0

---
*Phase: 01-foundation-data-indexer*
*Completed: 2026-07-10*
