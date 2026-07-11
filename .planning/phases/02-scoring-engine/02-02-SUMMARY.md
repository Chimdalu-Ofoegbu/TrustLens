---
phase: 02-scoring-engine
plan: 02
subsystem: scoring
tags: [python, sqlite, pytest, persistence, trustscore, deterministic]

# Dependency graph
requires:
  - phase: 02-scoring-engine (plan 02-01)
    provides: SCORE_VERSION 1.0.0, score_agent, build_stats, serialize_components, golden-pinned distributions
  - phase: 01-foundation-data-indexer
    provides: additive DDL tuple in indexer/db.py, refresh pipeline with exit-code contract, load_census, real 272-agent census
provides:
  - scores table (agent_id PK, score NULL-able, grade, confidence, score_version, generated_at, data_as_of, components JSON) created by the additive DDL tuple
  - scoring/persist.py compute_all(conn, generated_at, data_as_of) — the only sqlite3-touching scoring module; no commits; DELETE+INSERT self-cleaning
  - python -m indexer.refresh indexes AND scores all 272 agents in ONE atomic transaction (121 scored / 151 NR, pinned A:12/B:9/C:19/D:54/F:27/NR:151)
  - generated_at defaults to captured_at (zero wall clock) — rerun-byte-identical scores table; --generated-at CLI override for provenance
  - Phase 3 handoff: score cards servable straight from SQLite without recomputation
affects: [03-mcp-server, leaderboard, methodology-page]

# Tech tracking
tech-stack:
  added: []  # zero new dependencies — stdlib sqlite3 only
  patterns:
    - compute_all never commits — caller owns the transaction (same contract as upsert_agent/insert_snapshot)
    - history = COUNT(DISTINCT captured_at), never raw snapshot rows (real DB holds duplicates by design)
    - DELETE+INSERT full rewrite per refresh — self-cleaning, no staleness tracking
    - injected timestamps only; generated_at defaults to captured_at for byte-identical reruns

key-files:
  created:
    - scoring/persist.py
    - tests/test_scoring_persist.py
    - tests/test_refresh_scores.py
  modified:
    - indexer/db.py
    - indexer/refresh.py
    - scoring/__init__.py

key-decisions:
  - "Census path in persist tests anchored via Path(__file__).parents[1] (tests/test_category.py pattern, same call as 02-01's recorded decision) instead of the plan sketch's CWD-relative path"
  - "refresh()'s one-line docstring updated to name scores alongside agents+snapshots — keeping docs truthful about the extended transaction"

patterns-established:
  - "scores rows persist NR as score NULL + grade 'NR' — a successful state Phase 3 must serve, never an error"
  - "scores summary is a separate INFO log line on indexer.refresh; RefreshSummary stays frozen (regression-guarded by test)"

requirements-completed: [SCOR-01, SCOR-04]

# Metrics
duration: 13min
completed: 2026-07-11
---

# Phase 2 Plan 02: Score Persistence + Refresh Wiring Summary

**`python -m indexer.refresh` now indexes AND scores all 272 agents in one atomic transaction — scores table rewritten deterministically (121 scored / 151 NR, rerun-byte-identical SHA256-verified) with compute_all as the sole sqlite3-touching scoring module**

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-11T00:16:33Z
- **Completed:** 2026-07-11T00:29:24Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 6

## Accomplishments

- scores DDL appended to indexer/db.py's additive tuple: one row per agent via primary key, score column nullable for grade='NR' rows, FK to agents enforced by connect()'s PRAGMA
- scoring/persist.py compute_all: reads agents ORDER BY id + COUNT(DISTINCT captured_at) per agent, DELETE+INSERT rewrites all 272 rows inside the caller's transaction — rollback test proves zero internal commits
- indexer/refresh.py wiring: compute_all runs inside _persist_records' existing `with conn:` block after persist() — agents+snapshots+scores commit or roll back together; sqlite errors still route to the pre-existing exit-2 path with no new exit codes
- Determinism proven end-to-end: two real CLI runs produce identical SHA256 over the full scores dump (f62aa164…); generated_at defaults to captured_at, --generated-at overrides provenance while data_as_of stays pinned
- Persisted distribution matches the research dry-run exactly: A:12/B:9/C:19/D:54/F:27/NR:151; goldens 3118→(95,A,high), 2013→(73,B,medium), 3152→(32,F,low), 2662→(NULL,NR,low)
- All 272 persisted components blobs: valid JSON, exactly 5 component keys, zero banned-vocabulary hits; suite grew 154→170 with scoring coverage still 100% (167/167 statements) under the ≥90% gate

## Task Commits

Each task was committed atomically (TDD tasks produce test + feat commits):

1. **Task 1 RED: failing persistence tests** - `8bff39d` (test)
2. **Task 1 GREEN: scores DDL + scoring/persist.py** - `88ecb23` (feat)
3. **Task 2 RED: failing refresh-wiring tests** - `ece7cac` (test)
4. **Task 2 GREEN: refresh transaction wiring + --generated-at** - `3e3b884` (feat)

## Files Created/Modified

- `scoring/persist.py` - compute_all: the only scoring module importing sqlite3; parameterized INSERT_SCORE; no commits
- `indexer/db.py` - scores table appended to the DDL tuple (comment phrased to keep the inherited grep gate clean)
- `indexer/refresh.py` - scoring import, generated_at plumbing through _persist_records/refresh/main, --generated-at flag, separate scores INFO line, module docstring sentence
- `scoring/__init__.py` - compute_all re-export added to the frozen 02-01 surface
- `tests/test_scoring_persist.py` - 10 tests: exact schema columns, counts+distribution, NR round-trip, goldens, envelope stamps, recompute byte-identity, rollback, FK, DISTINCT-captured_at proof, components JSON/banned-vocab scan
- `tests/test_refresh_scores.py` - 6 tests: CLI end-to-end 272 rows + default timestamps, exact log line, CLI rerun byte-identity, --generated-at override, grade distribution, RefreshSummary frozen-fields guard

## Decisions Made

- Census path anchored from `__file__` in both new test files (existing tests/test_category.py and test_refresh.py pattern; 02-01 recorded the same decision) — robust to pytest invocation directory, same data
- refresh()'s one-line docstring updated to "agents + snapshots + scores" so the doc matches the extended transaction (module docstring change was plan-mandated; this one-liner would otherwise go stale)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Unclosed sqlite3 connection in new CLI test**
- **Found during:** Task 2 (full-suite verification run)
- **Issue:** test_persisted_grade_distribution opened `sqlite3.connect(db)` without closing it, emitting a ResourceWarning attributed by GC to an unrelated pre-existing test — the previously warning-free suite gained a warning
- **Fix:** wrapped the query in try/finally with conn.close(), matching every other connection in the file
- **Files modified:** tests/test_refresh_scores.py
- **Verification:** `python -m pytest -q` → 170 passed, zero warnings
- **Committed in:** 3e3b884 (part of Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug, test hygiene)
**Impact on plan:** None on behavior — fix kept the suite warning-clean. No scope creep; all DDL/SQL/module content transcribed verbatim as mandated.

## Authentication Gates

None - fully offline plan.

## Known Stubs

None. C5 (`listing_age_consistency`) and the C1 velocity note persisting "insufficient history"/"not computed in this score version" reasons are the plan-mandated honest degradation for single-snapshot data — inherited 02-01 design seams, test-pinned at the persistence layer here.

## Threat Model Coverage

All five register entries mitigated and test-enforced: T-02-05 (parameterized-only SQL — f-string grep gate exit 1, hostile-name FK/round-trip inherited from Phase 1 suite), T-02-06 (generated_at = captured_at default, wall-clock grep exit 1, CLI rerun SHA256 identical), T-02-07 (compute_all inside the same `with conn:` block; rollback test proves no partial writes; errors route to exit 2), T-02-08 (banned regex scans all 272 persisted blobs — 0 hits), T-02-09 (COUNT(DISTINCT captured_at) grep + 3-duplicate-rows test stays "single snapshot"). No new threat surface introduced beyond the plan's model.

## Issues Encountered

None beyond the auto-fixed ResourceWarning above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 2 complete (2/2 plans): scoring core + persistence both shipped; SCOR-01..04 all satisfied and gate-enforced
- Phase 3 can serve score cards (score, grade, confidence, score_version, generated_at, data_as_of, components JSON) straight from data/trustlens.db's scores table — zero recomputation, NR rows are valid successful responses
- Rebuild command for any environment: `python -m indexer.refresh` (deterministic; rerun-safe)

## Self-Check: PASSED

- All 3 created files exist on disk (scoring/persist.py 50 lines, tests/test_scoring_persist.py 212, tests/test_refresh_scores.py 119 — min_lines met)
- All 4 task commits in git log (8bff39d, 88ecb23, ece7cac, 3e3b884); no file deletions across the range
- `python -m pytest -q` exit 0: 170 passed, scoring coverage 100.00% with persist.py measured
- `python -m indexer.refresh` exit 0 twice; scores dump SHA256 identical both runs; GROUP BY grade == [('A',12),('B',9),('C',19),('D',54),('F',27),('NR',151)]; exact INFO line "scores computed: 121 scored, 151 not rated, version=1.0.0" observed
- Grep gates: "IF NOT EXISTS scores" ×1 in db.py; "COUNT(DISTINCT captured_at)" ×1 in persist.py; UNIQUE / f-string-SQL / .commit( / wall-clock greps all exit 1

---
*Phase: 02-scoring-engine*
*Completed: 2026-07-11*
