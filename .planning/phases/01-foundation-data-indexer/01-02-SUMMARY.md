---
phase: 01-foundation-data-indexer
plan: 02
subsystem: indexer
tags: [python, regex, unicodedata, csv, pytest, category-derivation]

# Dependency graph
requires:
  - phase: 01-foundation-data-indexer (plan 01)
    provides: pyproject scaffold, indexer package, pytest 9.1.1 wiring
provides:
  - indexer/category.py — derive_category(name, tagline) -> one of 9 fixed buckets; first-match-wins over the locked research-verbatim ORDERED_RULES keyword table
  - CATEGORIES / ORDERED_RULES / FALLBACK exports for Phase 2 price-vs-category percentiles and Phase 3 category_leaderboard
  - tests/test_category.py — full-census 272-row distribution pin, exact Other Services membership, research spot checks, determinism sweeps
affects: [01-03, 01-04, scoring, category_leaderboard, methodology-page, scraper]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Mechanics-override sets (REGEX_KEYWORDS, SUBSTRING_KEYWORDS) keyed by keyword string: compile semantics can change without touching locked table content"
    - "Full-dataset snapshot pinning: dict-equality distribution test makes any keyword drift fail CI loudly (research Pitfall 7)"

key-files:
  created:
    - indexer/category.py
    - tests/test_category.py
  modified: []

key-decisions:
  - "Substring-match override for cafe/restaurant keywords (mechanics-level SUBSTRING_KEYWORDS; locked table untouched) — required to reproduce the research-verified distribution"
  - "Universal optional-plural matching rejected: it re-buckets XBubbleAI (2087) out of Social & News, breaking two verified counts"
  - "INDX-03 REQUIREMENTS.md checkbox deferred to plan 01-04 — the requirement is shared with 01-03/01-04 and SQLite persistence does not exist yet"

patterns-established:
  - "Locked-table + mechanics split: data (ORDERED_RULES) is immutable; matching semantics live only in _compile"
  - "Census-reading tests resolve the CSV path relative to the test file so pytest works from any cwd"

requirements-completed: [INDX-03]

# Metrics
duration: 15min
completed: 2026-07-10
---

# Phase 1 Plan 02: Category Derivation Summary

**9-bucket first-match-wins keyword categorizer (research-verbatim locked table over NFKC-casefolded name+tagline) reproducing the verified 272-row census distribution exactly, pinned by full-census snapshot tests**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-10T21:44:02Z
- **Completed:** 2026-07-10T21:59:14Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `derive_category(name, tagline)` returns one of exactly 9 fixed bucket names for any input — pure, deterministic, stdlib-only (`re`, `unicodedata`), never empty, never raises
- Full-census run reproduces the research-verified distribution EXACTLY: Market Data & Analytics 70, Security & Trust 45, Trading & DeFi 41, Lifestyle & Health 30, Social & News 27, Developer Tools & Infra 22, Sports & Prediction 17, Creative & Media 15, Other Services 5
- Other Services contains exactly the 5 researched ids {3723, 3932, 3700, 3701, 3746} — the fallback does not swallow the catalog
- Drift pin in place (Pitfall 7): any future keyword edit that re-buckets even one agent fails `test_full_census_distribution` loudly
- Module docstring carries the methodology disclosure "categories derived from listing text" for the Phase 3 methodology page

## Task Commits

Each task was committed atomically (Task 1 was TDD):

1. **Task 1 RED: failing behavior tests** - `93d52c1` (test)
2. **Task 1 GREEN: 9-bucket category derivation** - `cffab0c` (feat)
3. **Task 2 deviation fix: cafe/restaurant plural mechanics** - `af3feb8` (fix)
4. **Task 2: full-census distribution snapshot pins** - `33ffda4` (test)

**Plan metadata:** (this commit) (docs: complete plan)

## Files Created/Modified

- `indexer/category.py` - Locked ORDERED_RULES 9-bucket keyword table (verbatim from research), REGEX_KEYWORDS + SUBSTRING_KEYWORDS mechanics overrides, `_compile`, `derive_category`, `CATEGORIES`, `FALLBACK`
- `tests/test_category.py` - 14 tests: 8 behavior/mechanics pins + census row count, exact distribution, exact Other Services membership, 8 spot checks, no-empty sweep, determinism sweep

## Decisions Made

- **Substring override for `cafe`/`restaurant` (mechanics, not table):** the only way to reproduce the verified distribution without editing locked table content. Census scan proved locality (see Deviations).
- **INDX-03 checkbox deferred:** INDX-03 ("SQLite persists agents + snapshots") is claimed by plans 01-02, 01-03, AND 01-04. This plan delivers the category derivation that fills the `category` column, but no SQLite code exists until 01-03/01-04 land. Marking the REQUIREMENTS.md checkbox now would be a false claim; plan 01-04 (which also lists INDX-03) marks it at integration.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan-provided `_compile` mechanics missed plural-only keyword occurrences (census row 3509)**

- **Found during:** Task 2 (full-census distribution pin)
- **Issue:** First run produced Lifestyle & Health 29 / Developer Tools & Infra 23 vs the verified 30/22. Row 3509 "Crypto Shop Near Me" contains only the plural forms "cafes"/"restaurants"; word-bounded `\bcafe\b` / `\brestaurant\b` miss them, so the row fell through to Developer Tools & Infra (via `payments`). Research's iteration history explicitly records the plural "cafes" miss as found-and-fixed, but that fix did not survive transcription into the plan's `_compile` code.
- **Analysis:** A universal optional-plural rule (`\bkw s?\b`) was tested as a diagnostic and rejected — it wrongly moved row 2087 XBubbleAI (plurals "videos"/"stickers") from Social & News into Creative & Media, breaking two other verified counts. The verified counts therefore require plural matching for cafe/restaurant ONLY. Consistently, the locked table lists explicit plurals (audits, thumbnails, avatars, ...) exactly where plural matching was intended — confirming exact word-bounded semantics for all other single tokens.
- **Fix:** Added `SUBSTRING_KEYWORDS = {"cafe", "restaurant"}` mechanics override in `indexer/category.py` (structurally parallel to the existing `REGEX_KEYWORDS` override); `_compile` gives these two existing table keywords substring semantics. Both still pass through `re.escape` (threat model T-02-01 mitigation intact). Keyword contents, bucket names, and ordering untouched. A full-census scan proved only row 3509 contains either substring, so the fix provably affects exactly one row.
- **Files modified:** indexer/category.py
- **Verification:** `python -m pytest tests/test_category.py -q` → 14 passed, including exact distribution, exact Other Services membership, and all spot checks; whole suite 50 passed
- **Committed in:** af3feb8 (dedicated fix commit; 1 applied fix attempt, within the plan's 2-attempt budget)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Fix was mandatory to satisfy the plan's own must-have truth (exact verified distribution). Mechanics-only change; locked table verbatim. No scope creep.

## Issues Encountered

- A bare `gsd-sdk state record-session` probe (checking argument signature) wrote empty session values to STATE.md; immediately overwritten by the correct `record-session` call in the same step. Final state is correct.

## Known Stubs

None — no placeholders, TODOs, or unwired data paths. All tests run against the real committed census.

## TDD Gate Compliance

Task 1 (`tdd="true"`): RED `93d52c1` (tests failed: `ModuleNotFoundError: indexer.category`) → GREEN `cffab0c` (8/8 passed). No refactor commit needed — the implementation is the locked verbatim transcription. Gates present and in order.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Wave-2 sibling 01-03 (db.py) is independent and can execute next
- 01-04 (census loader + refresh wire-up) consumes `derive_category(name.strip(), tagline.strip())` exactly as pinned here, and should mark INDX-03 complete at integration
- Phase 2 percentiles and Phase 3 category_leaderboard get a stable, drift-protected `category` column with a meaningful Creative & Media peer group

## Self-Check: PASSED

- indexer/category.py exists: FOUND
- tests/test_category.py exists: FOUND
- Commits 93d52c1, cffab0c, af3feb8, 33ffda4 in log: FOUND
- `python -m pytest -q` → 50 passed, exit 0
- data/okx-marketplace-census-2026-07-10.csv byte-identical (never written)

---

*Phase: 01-foundation-data-indexer*
*Completed: 2026-07-10*
