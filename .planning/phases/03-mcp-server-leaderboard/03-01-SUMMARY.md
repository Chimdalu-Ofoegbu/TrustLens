---
phase: 03-mcp-server-leaderboard
plan: 01
subsystem: ui
tags: [leaderboard, badge, svg, html, sqlite, string-template, xss, stdlib]

# Dependency graph
requires:
  - phase: 02-scoring-engine
    provides: scores table (272 rows, 121 scored / 151 NR) + scoring constants (DISCLAIMER, GRADE_BANDS, GRADE_DESCRIPTIONS, SCORE_VERSION, WEIGHTS)
  - phase: 01-foundation-data-indexer
    provides: agents table, indexer.refresh seeding, indexer.category.CATEGORIES (9 buckets)
provides:
  - web/build.py — build(db_path, out_path, base_url) renders the full UI-SPEC leaderboard page from SQLite, byte-deterministic, returns bytes written
  - web/badge.py — badge_svg(grade, score) + GRADE_BADGE_COLORS, the shared 110x20 UI-SPEC badge (page example now, /badge/{id}.svg route in plan 03-04)
  - page contract test suite: 272-row ordering, verbatim copy strings, XSS hostile fixture, determinism, banned-vocab source scan over web/
affects: [03-03 refresh wiring, 03-04 server static mount + badge route, 05 demo recording]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "string.Template page + str.format row template; zero literal $ in template body (substitute doubles as the stray-$ gate)"
    - "html.escape on EVERY DB-sourced string, text nodes and attributes alike"
    - "read-only sqlite via Path.as_uri() + ?mode=ro (space-safe repo path)"
    - "sort values (data-v) formatted in Python — prices reuse fixed-decimal display strings so scientific notation never reaches the page"

key-files:
  created:
    - web/__init__.py
    - web/badge.py
    - web/build.py
    - tests/test_web_badge.py
    - tests/test_web_build.py
  modified: []

key-decisions:
  - "data-v price sort values reuse the fixed-decimal display formatting (never str(float)) so e-notation can never appear anywhere in the page"
  - "scope=col reserved to the 9 leaderboard columns; methodology mini-tables use plain th, keeping the pinned th-count contract meaningful"
  - "badge_svg falls back to the neutral N/A badge for ANY unrecognized grade — hostile grade values from a tampered DB cannot reach the SVG text"

patterns-established:
  - "Banned-vocab source scan now covers web/ (badge.py via test_web_badge, build.py via test_web_build), mirroring the scoring/ scan"
  - "Web builds in tests always target pytest tmp dirs — never the repo (research Pitfall 7)"

requirements-completed: [WEB-01, WEB-02]

# Metrics
duration: 11min
completed: 2026-07-11
---

# Phase 3 Plan 01: Leaderboard Builder & Badge SVG Summary

**Self-contained 175KB leaderboard page generator (272 ranked agents, stdlib string.Template, inline sort/filter/copy JS) plus the shared 110x20 TrustLens badge SVG, both pinned by 25 contract tests including an XSS hostile fixture**

## Performance

- **Duration:** 11 min
- **Started:** 2026-07-11T11:08:40Z
- **Completed:** 2026-07-11T11:19:30Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- `web/build.py` renders the entire approved 03-UI-SPEC.md contract from SQLite in one call: 272 rows ranked score-desc with NR after scored and id-asc ties, exact copywriting strings, grade chips, methodology section (`id="methodology"`), badge embed section (`id="badge"`) with live inline example + HTML/Markdown snippets, all in 175,185 bytes (budget 300KB) with zero external requests
- `web/badge.py` produces UI-SPEC-conformant, deterministic, 534-byte SVG badges for every grade, NR, and the neutral unknown-agent case
- Inline vanilla JS (~115 lines, no `$` characters, passes `node --check`): data-v-driven column sort with empty-always-last and original-order ties, category filter with live count + empty state, clipboard copy with select-text fallback
- Hostile marketplace text proven neutralized: script tags, attribute-breaking quotes, CJK, and multiline taglines render only as escaped text (STRIDE T-03-01)
- Full suite 200 passed (175 existing + 25 new); scoring/ coverage gate untouched at 100%

## Task Commits

Each task was committed atomically:

1. **Task 1: web/badge.py — shared TrustLens badge SVG generator** - `dcb689b` (feat)
2. **Task 2: web/build.py — full leaderboard page builder per UI-SPEC** - `f20c159` (feat)
3. **Task 3: tests/test_web_build.py — page contract, XSS fixture, determinism, banned vocab** - `ec0f40d` (test)

## Files Created/Modified

- `web/__init__.py` - package docstring (build-time, stdlib only)
- `web/badge.py` - pure `badge_svg(grade, score)` + `GRADE_BADGE_COLORS`; fixed 110x20 two-segment geometry, title-first accessibility, <1KB
- `web/build.py` - `build(db_path, out_path, base_url)`; read-only URI connection, ranked query, Python-side number formatting, UI-SPEC page template with inline CSS/JS
- `tests/test_web_badge.py` - 13 badge contract tests (geometry, colors, budget, determinism, banned-vocab scan)
- `tests/test_web_build.py` - 12 page contract tests (ordering, copy strings, DOM hooks, CJK/price edges, self-containment, determinism, XSS fixture, source scan, weight budget)

## Decisions Made

- `data-v` price sort values reuse the fixed-decimal display string instead of `str(float)` — guarantees the page-wide "no scientific notation" contract also holds for machine-readable sort attributes
- `scope="col"` kept exclusive to the 9 leaderboard columns (methodology mini-tables use plain `<th>`) so the pinned `th scope="col"` count == 9 test stays a meaningful contract
- `badge_svg` treats any grade outside `GRADE_BADGE_COLORS` as unknown → neutral "N/A" badge, so tampered DB grade values can never be interpolated into badge text

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Retry context: a previous executor attempt died on an API infrastructure error leaving untracked partial files (`web/__init__.py`, `web/badge.py`). Both were reviewed against the plan as the authority: `__init__.py` matched verbatim and was used as-is; `badge.py` was nearly conformant and received one hardening edit (explicit `grade == "NR"` branch so NR never renders with a score). No prior commits existed; all three task commits are from this run.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `web.build.build()` is ready for plan 03-03 to wire into `indexer.refresh` (import-based, `web_out` parameter pattern already proven by the tmp-dir tests)
- `web.badge.badge_svg()` is ready for plan 03-04's `/badge/{agent_id}.svg` route (unknown-agent case already returns the neutral badge the route needs)
- `web/dist/` output path is already covered by the existing `dist/` gitignore pattern

## Self-Check: PASSED

- All 5 created files exist on disk (verified with `[ -f ]`)
- All 3 task commits present in git log (dcb689b, f20c159, ec0f40d)
- All task acceptance criteria re-verified: badge tests 13 passed, page tests 12 passed, combined subset 25 passed, full suite 200 passed with scoring coverage 100%
- Plan verification commands: `python -m pytest tests/test_web_badge.py tests/test_web_build.py --no-cov -q` exit 0; `python -m pytest` exit 0

---
*Phase: 03-mcp-server-leaderboard*
*Completed: 2026-07-11*
