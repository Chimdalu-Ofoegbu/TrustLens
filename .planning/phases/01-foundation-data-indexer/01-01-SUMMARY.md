---
phase: 01-foundation-data-indexer
plan: 01
subsystem: indexer
tags: [python, pyproject, pytest, dataclass, csv-parsing, unicode, nfkc, tdd]

# Dependency graph
requires: []
provides:
  - pyproject.toml with locked pins (fastapi 0.139.0, fastmcp>=3,<4, uvicorn 0.51.0, httpx 0.28.1, beautifulsoup4 4.15.0; dev pytest 9.1.1 + pytest-cov 7.1.0) and pytest config
  - indexer package importable everywhere via editable install; pytest 9.1.1 invocable from repo root
  - AgentRecord frozen dataclass — the loader/db contract for plans 01-02..01-04 and the Phase 5 scraper seam
  - Four pure census field parsers (parse_sold, parse_price, parse_rating_positive, name_key) with 36 verified fixture tests
affects: [01-02, 01-03, 01-04, scoring, server, scraper]

# Tech tracking
tech-stack:
  added: [fastapi 0.139.0, fastmcp 3.4.4, uvicorn 0.51.0, httpx 0.28.1, beautifulsoup4 4.15.0, pytest 9.1.1, pytest-cov 7.1.0]
  patterns: [pure stdlib parsers with strict re.fullmatch, frozen dataclass cross-plan contracts, TDD fixtures pinned to real census row values]

key-files:
  created:
    - pyproject.toml
    - indexer/__init__.py
    - indexer/models.py
    - indexer/parse.py
    - tests/test_parse.py
  modified: []

key-decisions:
  - "Rating rule A implemented as pinned: rating valid iff positive non-empty AND rating string != price token AND 0-5 (90 rated / 182 unrated on the real file)"
  - "parse_sold blank -> 0 encodes the locked missing/blank semantics directly; prose -> None so the caller stores 0 and warns (id 4137)"

patterns-established:
  - "Strict fullmatch parsing: no digit-grabbing fallbacks; unparseable input -> None, never coerced"
  - "Fixture tests cite the real census row ids they encode, so any parser edit re-verifies against the source data"

requirements-completed: [INDX-02]

# Metrics
duration: 11min
completed: 2026-07-10
---

# Phase 01 Plan 01: Python Scaffold & Census Field Parsers Summary

**Pinned pyproject scaffold (fastapi/fastmcp/uvicorn/httpx/bs4 + pytest 9.1.1), AgentRecord frozen-dataclass contract, and four stdlib census parsers that defuse the price-echo, subscript-zero, and K-suffix corruption traps — 36 fixture tests green**

## Performance

- **Duration:** 11 min
- **Started:** 2026-07-10T21:26:26Z
- **Completed:** 2026-07-10T21:37:32Z
- **Tasks:** 2 (Task 2 TDD: RED + GREEN)
- **Files modified:** 5 created

## Accomplishments

- `python -m pip install -e ".[dev]"` succeeded on Python 3.14.2 with every locked pin resolving exactly (fastapi 0.139.0, fastmcp 3.4.4, uvicorn 0.51.0, httpx 0.28.1, beautifulsoup4 4.15.0, pytest 9.1.1, pytest-cov 7.1.0, starlette 1.3.1) — no fallback path needed
- `AgentRecord` frozen dataclass lands as the cross-plan contract (`category_source` defaults to `'derived'` for the Phase 5 scraper seam)
- The four risk-pocket parsers reproduce every research-verified fixture value: `1.55K sold` → 1550, `0.0₄15 USDT` → 0.000015 (never the 10x off-by-one), `('5','','5 USDT')` → `(None, None)` (the echo that looks like a perfect rating), NFKC folds U+FF1F → `?`
- Whole suite green: 36 passed, exit 0, stdlib-only imports in `indexer/parse.py` (zero network modules)

## Task Commits

Each task was committed atomically:

1. **Task 1: Bootstrap pyproject scaffold, package skeleton, and AgentRecord contract** - `4243f59` (feat)
2. **Task 2 RED: Field parser fixture tests (failing)** - `2e15194` (test)
3. **Task 2 GREEN: Field parser implementation** - `00c0820` (feat)

_TDD gate compliance: `test(01-01)` commit precedes `feat(01-01)` parser commit; RED failed with `ModuleNotFoundError` (correct reason); no REFACTOR needed — implementation is the research-verified code verbatim._

## Files Created/Modified

- `pyproject.toml` - Locked runtime pins + dev extras + `[tool.pytest.ini_options]` (testpaths=tests); packages list ready for Phase 2 "scoring" / Phase 3 "server" additions
- `indexer/__init__.py` - Docstring-only package init (no submodule imports, keeps import graph light)
- `indexer/models.py` - `AgentRecord` frozen dataclass: id, name, name_key, category, tagline, price_usdt/price_raw, sold, rating, positive_pct, category_source
- `indexer/parse.py` - `parse_sold`, `parse_price`, `parse_rating_positive` (rule A echo gate), `name_key` (NFKC casefold) — pure, never raise on malformed input
- `tests/test_parse.py` - 36 fixture tests, each citing the real census row id it encodes (3345, 3118, 2023, 2013, 4489, 4137, 2169, 3091, 2791, 1500, 1851)

## Decisions Made

None - followed plan as specified (rating rule A, pin set, and parser semantics were all pre-decided and pinned by the plan).

## Deviations from Plan

None - plan executed exactly as written. The editable install resolved all runtime deps on local Python 3.14.2, so the pytest-only fallback path was not needed.

## Authentication Gates

None - fully offline plan (pip package installs only).

## Known Stubs

None - all four parsers are fully implemented and wired to tests; no placeholder values or unwired components.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Wave 2 unblocked: pytest runs from the repo root and `AgentRecord` is importable — plans 01-02 (category) and 01-03 (db) can build against the contract
- `indexer/parse.py` is ready for 01-04's census loader to consume; the caller-side warning behavior (prose sold → store 0 + log) is documented in the parser docstrings
- Threat register T-01-01 mitigation applied: strict `re.fullmatch` only, no eval/exec/dynamic parsing, unparseable input returns None

## Self-Check: PASSED

- All 5 key files exist on disk (verified with `[ -f ]`)
- All 3 task commits present in git log (4243f59, 2e15194, 00c0820)
- TDD gates: test commit before feat commit, both present
- `python -m pytest -q` → 36 passed, exit 0
- min_lines: indexer/parse.py 79 (≥60), tests/test_parse.py 193 (≥60)

---
*Phase: 01-foundation-data-indexer*
*Completed: 2026-07-10*
