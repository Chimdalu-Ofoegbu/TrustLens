---
phase: 02-scoring-engine
plan: 01
subsystem: scoring
tags: [python, pytest, pytest-cov, trustscore, deterministic, golden-tests]

# Dependency graph
requires:
  - phase: 01-foundation-data-indexer
    provides: AgentRecord model, load_census loader, derived 9-bucket categories, parse rules (None vs 0.0 semantics)
provides:
  - scoring/ package - pure, deterministic TrustScore core (no I/O, no wall clock)
  - five component functions with frozen constants and neutral reason templates (stats.py, components.py)
  - score_agent engine - 0-100 int + A-F grade + NR rule + confidence rubric + weight renormalization (engine.py)
  - deterministic serialize_components (sorted keys, fixed separators, ensure_ascii=False)
  - golden pins + grade/confidence distribution pins over all 272 real census agents
  - dual-layer banned-vocabulary enforcement (source scan + rendered cards) and no-I/O import guard
  - pytest coverage gate --cov=scoring --cov-fail-under=90 active on plain `python -m pytest`
affects: [02-02 persistence, 03-mcp-server, leaderboard, methodology-page]

# Tech tracking
tech-stack:
  added: []  # zero new dependencies - stdlib math/json only; pytest-cov gate activated (already pinned)
  patterns:
    - pure component signature - plain values in, frozen dict shape out ({score, weight, observed, benchmark, flagged, reason})
    - Stats precomputed once per snapshot and passed in (benchmarks are explicit inputs)
    - score None as the explicit insufficient-data state; weights renormalize over scored components
    - reason templates interpolate only numbers + category bucket names (defamation-surface rule)
    - golden pinning - regenerate from implementation, verify against research, never hand-compute (half-even round)

key-files:
  created:
    - scoring/__init__.py
    - scoring/stats.py
    - scoring/components.py
    - scoring/engine.py
    - tests/test_scoring_components.py
    - tests/test_scoring_engine.py
    - tests/test_scoring_golden.py
  modified:
    - pyproject.toml

key-decisions:
  - "scoring/ public surface frozen at SCORE_VERSION 1.0.0; goldens + distributions pinned over the real census - formula changes require version bump + re-pin"
  - "Golden-test census path anchored via Path(__file__).parents[1] following the existing tests/test_category.py pattern (plan sketch showed a CWD-relative path)"

patterns-established:
  - "C2 branch order frozen: rated-with-null-pct check precedes the thin-sales check"
  - "sqlite3 import allowed ONLY in a future scoring/persist.py (test-enforced); all other I/O imports banned in scoring/"
  - "Coverage-gate footgun documented: subset runs need --no-cov"

requirements-completed: [SCOR-01, SCOR-02, SCOR-03, SCOR-04]

# Metrics
duration: 17min
completed: 2026-07-11
---

# Phase 2 Plan 01: Deterministic Scoring Core Summary

**Pure deterministic TrustScore core: five research-locked component functions + NR-aware aggregation engine, golden-pinned over all 272 real agents (A:12/B:9/C:19/D:54/F:27/NR:151) with a 100%-measured >=90% coverage gate**

## Performance

- **Duration:** 17 min
- **Started:** 2026-07-10T23:53:13Z
- **Completed:** 2026-07-11T00:10:20Z
- **Tasks:** 3 (2 TDD, 1 auto)
- **Files modified:** 8

## Accomplishments

- `scoring/` package: stats.py (benchmark pools + rating-display base rate), components.py (five pure functions, frozen constants, neutral templates), engine.py (NR rule, grade bands, confidence rubric, deterministic serialization), `__init__.py` re-exports
- All 10 research golden values reproduce exactly on first run (3118 -> 95/A/high, 3345 -> 94/A/high, 2013 -> 73/B/medium, ..., 2662/4137 -> NR) - the formula transcription matched the dry-run with zero adjustment
- Grade distribution A:12/B:9/C:19/D:54/F:27/NR:151 and confidence high:14/medium:26/low:232 pinned; 42-agent thin-perfect cohort (5.0 rating, <5 sales) is 100% flagged + low-confidence, grades D:34/F:8 - flagged, never accused, never top-ranked
- Dual-layer SCOR-03 enforcement green: `(?i)(fraud|scam|fake|manipulat)` finds zero matches in scoring/ source and in all 272 rendered score cards (plus DISCLAIMER and grade descriptions)
- Byte-identity proven: two fresh builds over the census produce byte-equal serialized components and identical (score, grade, confidence) for every agent
- Coverage gate live: plain `python -m pytest` enforces `--cov=scoring --cov-fail-under=90`; measured coverage is 100% (147/147 statements); 154 tests pass (78 pre-existing + 76 new)

## Task Commits

Each task was committed atomically (TDD tasks produce test + feat commits):

1. **Task 1 RED: failing component tests** - `f89c3dc` (test)
2. **Task 1 GREEN: stats.py + components.py** - `bd5f34a` (feat)
3. **Task 2 RED: failing engine tests** - `2c7c68b` (test)
4. **Task 2 GREEN: engine.py + __init__ exports** - `267d358` (feat)
5. **Task 3: golden pins + vocab enforcement + coverage gate** - `4038c66` (test)

## Files Created/Modified

- `scoring/__init__.py` - package docstring + public re-exports (score_agent, build_stats, Stats, WEIGHTS, grade_for, serialize_components, envelope constants)
- `scoring/stats.py` - Stats dataclass + build_stats: category/market price pools (identity check on price - 0.0 is real), rating-display base rate at 20+ sales with total_hi==0 guard
- `scoring/components.py` - SOLD_REF/SUPPORT_REF/THIN_SALES/CRED_FLOOR/MIN_CATEGORY_PRICED/PRICE_DEV_SPAN/WEIGHTS verbatim; log_scale/percentile/fmt_price/_median; the five component functions with frozen reason templates
- `scoring/engine.py` - SCORE_VERSION 1.0.0, GRADE_BANDS, DISCLAIMER, GRADE_DESCRIPTIONS, grade_for, serialize_components, score_agent (verbatim NR rule + renormalization + confidence)
- `tests/test_scoring_components.py` - 52 tests: anchors for all five components, branch tables, helper edges, build_stats guards
- `tests/test_scoring_engine.py` - 14 tests: NR rule, band edges, confidence branches, renormalization over 0.90, serialization identity
- `tests/test_scoring_golden.py` - 10 tests over the real census: goldens, distributions, thin-perfect cohort, exact reason pin, dual-layer vocab, import guard, byte-identity
- `pyproject.toml` - scoring package registered; pytest addopts coverage gate (last file touched, per the sequencing constraint)

## Decisions Made

- Golden-test census path anchored from `__file__` (existing test_category.py pattern referenced by the task's read_first) instead of the plan sketch's CWD-relative path - same data, robust to invocation directory
- C2 branch-4 template keeps the literal "20+ sales" wording exactly as the plan freezes it (renders identically to interpolating RATING_EXPECTED_SALES)
- No REFACTOR commits: both TDD implementations are direct transcriptions of the research spec with nothing to clean up

## Deviations from Plan

None - plan executed exactly as written. All 10 golden pins, both distribution pins, the 42-member cohort pin, and the exact reason pin matched the research dry-run on the first implementation run (verified via a scratchpad dry-run before pinning).

## Authentication Gates

None - fully offline plan.

## Known Stubs

None. `listing_age_consistency` always returning `score: None` and C1's velocity note are NOT stubs - they are the plan-mandated honest insufficient-history degradation for single-snapshot data (all 272 agents), documented as v2 design seams in docstrings and pinned by tests.

## Threat Model Coverage

All four register entries mitigated and test-enforced: T-02-01/T-02-03 (no listing text in templates - source scan + 272 rendered cards), T-02-02 (no clock/randomness, byte-identity test), T-02-04 (`is None` identity checks; all 272 real rows incl. 0.0 prices and 0% positive score without raising). No new threat surface introduced beyond the plan's model.

## Issues Encountered

None. Console output mangled em-dashes during the dry-run (cp1252 display artifact only - verified the underlying strings are correct via the exact-reason test).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 02-02: persistence (scores DDL appended to indexer/db.py's tuple, scoring/persist.py compute_all, refresh wiring with injected generated_at)
- Contracts 02-02 must honor (test-enforced here): sqlite3 import allowed only in scoring/persist.py; no uppercase U-word literal in scoring/ or DDL; score_agent row contract is `dict(sqlite3.Row)` with keys category/sold/rating/positive_pct/price_usdt/first_seen; distinct_snapshots = COUNT(DISTINCT captured_at)
- Coverage note for 02-02: the gate measures all of scoring/ - persist.py needs its own tests to keep >=90%

## Self-Check: PASSED

- All 7 created files verified on disk; pyproject.toml gate line present (exactly one `cov-fail-under=90`)
- All 5 task commits found in git log (f89c3dc, bd5f34a, 2c7c68b, 267d358, 4038c66)
- `python -m pytest -q` exit 0 with gate active: 154 passed, scoring coverage 100.00%
- `python -m pytest tests/test_scoring_golden.py --no-cov -q` exit 0 (escape hatch works)
- `grep -rniE "fraud|scam|fake|manipulat" scoring/` exit 1; `grep -rn "UNIQUE" scoring/ pyproject.toml` exit 1; forbidden-import grep exit 1

---
*Phase: 02-scoring-engine*
*Completed: 2026-07-11*
