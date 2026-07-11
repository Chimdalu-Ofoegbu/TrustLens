---
phase: 03-mcp-server-leaderboard
plan: 03
subsystem: web
tags: [sqlite, argparse, leaderboard, cli, pytest, setuptools]

# Dependency graph
requires:
  - phase: 03-01
    provides: "web/build.py build(db_path, out_path, base_url) -> int leaderboard builder"
  - phase: 02-scoring-engine
    provides: "refresh pipeline with compute_all in the persist transaction + 0/1/2 exit taxonomy"
provides:
  - "python -m indexer.refresh regenerates web/dist/index.html from SQLite in the same run that indexes and scores (WEB-03)"
  - "web_out: Path | None = None threading through refresh/_persist_records — None (library default) skips the page build"
  - "--web-out CLI flag defaulting to DEFAULT_WEB_OUT = web/dist/index.html"
  - "pyproject packages = indexer, scoring, server, web (editable install refreshed; unblocks uvicorn server.main:app and Docker pip install .)"
  - "web/dist/ gitignored; staged artifacts data/trustlens.db + web/dist/index.html for 03-04 smoke and 03-05 Inspector run"
affects: [03-04, 03-05, docker, server, phase-04-payments]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "web_out=None skip-sentinel: output side-effects are parameters; defaults only apply at the CLI boundary (Pitfall 7 isolation)"
    - "Page build runs AFTER the persist transaction commits and conn.close() — builder reads committed rows via its own read-only connection"
    - "Build failures reuse the existing (OSError, sqlite3.Error) -> exit 2 environment-problem class; no new except clauses"

key-files:
  created:
    - tests/test_refresh_web.py
  modified:
    - indexer/refresh.py
    - pyproject.toml
    - .gitignore
    - tests/test_refresh_scores.py
    - tests/test_refresh.py

key-decisions:
  - "Locked planner decision honored: web_out=None means SKIP for library calls; main() always passes --web-out (default web/dist/index.html) so the CLI is the only always-build surface"
  - "base_url for the built page comes from TRUSTLENS_BASE_URL env with the safe http://localhost:8000 default (T-03-12 accepted)"

patterns-established:
  - "leaderboard built: log line at INFO on logger indexer.refresh (path, agent count, bytes) — pinned by test"

requirements-completed: [WEB-03]

# Metrics
duration: 10min
completed: 2026-07-11
---

# Phase 3 Plan 03: Refresh Wiring Summary

**`python -m indexer.refresh` now indexes, scores, AND regenerates web/dist/index.html (175,113 bytes, byte-identical on rerun) in one command, with build failures mapped into the existing exit-2 environment class**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-11T11:41:18Z
- **Completed:** 2026-07-11T11:51:14Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- WEB-03 shipped: the single refresh CLI regenerates the leaderboard from SQLite every run; `--web-out` defaults to `web/dist/index.html` and reruns produce sha256-identical HTML
- Exit-code taxonomy preserved and extended in meaning only: a failed page build (e.g. output parent is a file) exits 2 through the existing `(OSError, sqlite3.Error)` catch — db work still committed, no new except clauses
- Library isolation pinned (research Pitfall 7): `refresh(csv, db, ts)` without `web_out` writes zero HTML anywhere; full 221-test suite leaves `web/dist/` untouched (`ls web/dist/index.html` fails after the run; artifact only appears via the real CLI)
- RefreshSummary frozen contract untouched (agents, snapshots_appended, field_warnings, source) — the build reports via its own `leaderboard built:` INFO line
- Packaging extended to `["indexer", "scoring", "server", "web"]` and editable install refreshed — prerequisite for `uvicorn server.main:app` (03-04) and the Docker `pip install .` (03-05)

## Task Commits

Each task was committed atomically:

1. **Task 1: Thread web_out through refresh + extend packaging and gitignore** - `b3813a6` (feat)
2. **Task 2: Regression tests — regeneration, HTML byte-determinism, exit 2, isolation** - `5bd0c73` (test)

## Files Created/Modified

- `indexer/refresh.py` - `DEFAULT_WEB_OUT` constant; `web_out: Path | None = None` on `refresh`/`_persist_records`; build invoked after commit+close; `--web-out` argparse flag; docstring exit-code line extended
- `pyproject.toml` - `[tool.setuptools] packages = ["indexer", "scoring", "server", "web"]`
- `.gitignore` - `web/dist/` under runtime artifacts
- `tests/test_refresh_web.py` - 5 new CLI-level tests: regeneration (272 `<tr id="agent-` rows, methodology + badge anchors, >50 KiB), sha256 rerun identity, build-failure exit 2 with db intact, library no-page isolation, `leaderboard built:` log line
- `tests/test_refresh_scores.py` - `_run` helper routes `--web-out` into the db's tmp dir (only edit; all 6 tests unmodified)
- `tests/test_refresh.py` - exactly the two exit-0 CLI call sites (`test_cli_main`, second invocation in `test_cli_dateless_filename_returns_2`) gained `--web-out` into tmp_path; zero assertion changes

## Decisions Made

None beyond the plan - the locked planner decision (None-skip sentinel, CLI-only default) was implemented as specified.

## Deviations from Plan

None - plan executed exactly as written. (Environment note: `pip` is not on PATH in this shell; `python -m pip install -e .` used for the editable reinstall — same effect.)

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `data/trustlens.db` and `web/dist/index.html` staged at repo defaults — plan 03-04's manual smoke (server composition) and 03-05's Inspector/Docker runs can start immediately
- All four packages installed editable; `server.main:app` importable for uvicorn
- Full suite: 221 passed, scoring coverage gate at 100%

## Self-Check: PASSED

All created/modified files exist on disk; task commits b3813a6 and 5bd0c73 present in git log.

---
*Phase: 03-mcp-server-leaderboard*
*Completed: 2026-07-11*
