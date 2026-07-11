---
phase: 02-scoring-engine
reviewed: 2026-07-11T00:43:37Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - scoring/__init__.py
  - scoring/stats.py
  - scoring/components.py
  - scoring/engine.py
  - scoring/persist.py
  - indexer/db.py
  - indexer/refresh.py
  - pyproject.toml
  - tests/test_scoring_components.py
  - tests/test_scoring_engine.py
  - tests/test_scoring_golden.py
  - tests/test_scoring_persist.py
  - tests/test_refresh_scores.py
findings:
  critical: 0
  warning: 3
  info: 6
  total: 9
status: clean
fixed_at: 2026-07-11
fix_commits: [86840eb, bd8d922, 05b4f86]
---

# Phase 2: Code Review Report

**Reviewed:** 2026-07-11T00:43:37Z
**Depth:** standard
**Files Reviewed:** 13
**Status:** clean — all 3 Warnings fixed (2026-07-11); 6 Info findings remain open, documented for the Phase 5 hardening sweep

**Fix pass (2026-07-11):** WR-01, WR-02, WR-03 fixed in commits `86840eb`, `bd8d922`, `05b4f86` (one atomic commit per finding, each with regression tests). Full suite after each fix: 175 passed, scoring/ at 100% coverage. Rendered outputs for all 272 census agents are byte-identical — scores-dump SHA256 `f62aa164c3cc36a1…` matches the 02-VERIFICATION.md pin before and after — so the pinned distribution (A:12/B:9/C:19/D:54/F:27/NR:151), golden values, and SCORE_VERSION "1.0.0" are all unchanged. Per-finding resolutions inline below.

## Summary

Reviewed the Phase 2 scoring engine (pure scoring core, persistence, refresh wiring, coverage gate, five test files) against the locked decisions in 02-CONTEXT.md and the STRIDE registers in 02-01-PLAN.md / 02-02-PLAN.md. Review included executing the full suite and adversarial probe scripts against the installed package (read-only with respect to the repo).

**Verified by execution:**
- `python -m pytest -q`: 170 passed, coverage gate active, scoring/ at 100% (gate requires >= 90%).
- Grep gates all clean by direct run: banned vocabulary in `scoring/` (exit 1), uppercase constraint literal in `indexer/db.py`, `indexer/refresh.py`, `scoring/`, `pyproject.toml` (exit 1), wall-clock reads in `indexer/` + `scoring/` (exit 1), forbidden I/O imports in `scoring/` including indented ones (exit 1).
- Determinism posture is strong: no wall clock or randomness anywhere in scoring, `generated_at` defaults to `captured_at`, serialization uses sorted keys + fixed separators, all output orderings come from literal dict construction or `ORDER BY id`. Cross-platform `round()` fragility from libm `log10` variance was measured, not assumed: minimum distance to a .5 rounding boundary is 1.42e-3 for C1 (sold 0..100000) and 1.68e-4 for C3 (rating tenths x sold 0..20000) — a 1-ulp libm difference (~1e-13 relative) cannot flip any score, so byte-identity holds across machines.
- DELETE+INSERT under WAL is safe for Phase 3 concurrent readers: the whole rewrite (persist + compute_all) runs inside one `with conn:` transaction in `_persist_records`, compute_all never commits (rollback test proves it), so a WAL reader sees the old table or the new table, never an empty or partial one.
- SQL is parameterized throughout; no listing name/tagline reaches any reason template; the thin-perfect case is flagged with the "not an assessment of conduct" wording; NR is a successful row (score NULL, all five components rendered).
- Threat mitigations T-02-02, T-02-05, T-02-06, T-02-07, T-02-08, T-02-09 are present in code and test-enforced. T-02-01/T-02-03 and T-02-04 each have one residual gap (WR-02, WR-03 below).

No Critical findings. The three Warnings are all latent — none is reachable with the current single-census data — but each sits on a path the project's own documents say will be exercised (a second census / Phase 5 scraper, Phase 3 consumption of the public API), and one is contradicted by its own docstring today.

## Warnings

### WR-01: Delisted agents get fresh `data_as_of` provenance from data they were never observed in; "self-cleaning" docstring claim is false

**File:** `scoring/persist.py:26-31` (docstring claim), `scoring/persist.py:44-49` (stamping)
**Issue:** `compute_all` scores every row in the `agents` table and stamps every score row with the caller's single `data_as_of`. Agents are never deleted (the pipeline only upserts), so an agent absent from a later census keeps its stale `agents` row, gets re-scored from that stale data, and receives `data_as_of` = the new capture time. Proven empirically: seeding A+B at `2026-07-10`, then refreshing with only B at `2026-07-15`, leaves A with `data_as_of='2026-07-15T00:00:00Z'` while `agents.last_seen='2026-07-10T00:00:00Z'`. The score row asserts the data is "as of" a snapshot in which the agent was never observed — the locked credibility-envelope definition is "data_as_of (snapshot captured_at)", and the DISCLAIMER leans on "as of the stated snapshot". The docstring's mitigation claim ("DELETE+INSERT is self-cleaning: agents absent from a future census leave no stale score rows") is incorrect: a stale-data score row is regenerated every refresh, with fresh provenance. Unreachable in v1's single-census reality; becomes live the first time a differing census/scrape lands (Phase 5, inside the hackathon window).
**Fix:** Stamp provenance per agent from its own observation time, and correct the docstring:
```python
conn.execute(
    INSERT_SCORE,
    (row["id"], card["score"], card["grade"], card["confidence"],
     SCORE_VERSION, generated_at, row["last_seen"],  # data_as_of = when THIS agent was last observed
     serialize_components(card["components"])),
)
```
(Alternative, if "score only currently-listed agents" is preferred: `SELECT * FROM agents WHERE last_seen = ? ORDER BY id` with `data_as_of` bound — that makes the self-cleaning claim true instead. Either way, this is a persisted-shape semantics decision: settle it before Phase 3 serves the column, and fix the docstring in the same commit.)

**Resolution: FIXED** in `86840eb` (2026-07-11). Took the "score only currently-listed agents" alternative: `compute_all` now selects `WHERE last_seen = ?` bound to `data_as_of`, so a delisted agent is never re-scored, benchmark stats are built from the current capture only, and the self-cleaning claim is now true (docstring corrected in the same commit). Regression test `test_delisted_agent_is_not_rescored_with_false_provenance` seeds A+B-style history (full census at the seed capture, one agent absent from the next) and proves: stale agents row survives with old `last_seen`, no score row for the delisted agent, all 271 remaining rows carry the new `data_as_of` truthfully. Every current call path passes the `captured_at` of the batch just persisted, so all 272 census agents still qualify — outputs byte-identical.

### WR-02: `category` is interpolated into outward reason strings with no allowlist — the "9 fixed category names" mitigation is assumed, not enforced

**File:** `scoring/components.py:199` (`label = category`), `scoring/components.py:211-221` (rendered)
**Issue:** Threat T-02-01/T-02-03's stated mitigation is "templates interpolate only numbers + the 9 fixed category names". The code enforces no such set: `c_price_vs_category` renders whatever `category` string it is handed, verbatim, into paid-product reason text whenever that category has >= MIN_CATEGORY_PRICED priced rows. Proven: a stats object keyed by `"totally-a-scam-category"` renders `"price 4 USDT within totally-a-scam-category norm (...)"` — banned vocabulary in an outward reason. Today the invariant holds only because Phase 1's derivation is the sole writer of `category`; `indexer/db.py:30-31` explicitly plans `category_source='listed'` from scraped marketplace pages in Phase 5, at which point listing-controlled text flows into reasons. The banned-vocab rendered-layer test only covers whatever data is in the census fixture, so it cannot catch this at runtime.
**Fix:** Pin the label to a frozen allowlist inside scoring (scoring must not import indexer, so mirror the 9 bucket names and add a cross-package equality test in `tests/`):
```python
CATEGORY_LABELS = frozenset({...the 9 bucket names...})  # mirrored from indexer.category; test-pinned equal

pool = stats.category_pools.get(category, ())
label = category
if category not in CATEGORY_LABELS or len(pool) < MIN_CATEGORY_PRICED:
    pool = stats.market_pool
    label = "marketplace"   # never render text outside the fixed vocabulary
```
Add a unit test rendering a non-bucket category and asserting the label falls back.

**Resolution: FIXED** in `bd8d922` (2026-07-11). `c_price_vs_category` now falls back to the marketplace pool AND the fixed `"marketplace"` label whenever `category not in CANONICAL_CATEGORIES` (or the pool is under `MIN_CATEGORY_PRICED`). One deviation from the fix hint, per project direction: instead of mirroring the 9 names, `CANONICAL_CATEGORIES = frozenset(CATEGORIES)` imports the authoritative list directly from `indexer.category` — single source of truth, no drift possible. This is safe: `indexer/__init__.py` is docstring-only (no import cycle through `indexer.refresh`) and `indexer.category` is pure (`re` + `unicodedata` only), so no I/O or wall clock enters scoring; the no-I/O source guard stays green. Tests: `test_c4_non_canonical_category_never_renders_into_reason` (the hostile probe string from this finding, given a pool clearing `MIN_CATEGORY_PRICED`, never reaches the reason — label, pool, and benchmark all fall back) and `test_c4_canonical_set_is_the_nine_derived_buckets` (pins the set to exactly the 9 buckets). All 272 census categories are canonical, so outputs are byte-identical.

### WR-03: `c_price_vs_category` raises ZeroDivisionError when both pools are empty and a price is present

**File:** `scoring/components.py:198-207` (unguarded pool), `scoring/components.py:50-54` (`percentile` divides by `len(pool)`)
**Issue:** With `price_usdt` not None, an empty category pool falls back to `stats.market_pool`; if that is also empty, `percentile(pool, price)` divides by zero (and `_median` would raise IndexError). Proven: `score_agent` on a priced row with stats built from unpriced rows crashes with `ZeroDivisionError`. Unreachable through `compute_all` — stats are built from the same rows being scored, so any priced agent implies a non-empty market pool — but `score_agent`/`c_price_vs_category` are exported public API with no documented "stats must include at least one priced row" precondition. This is the residual of T-02-04 (formula crash on sparse rows aborts refresh): a future caller scoring one row against externally built stats hits it immediately.
**Fix:** Guard after the fallback, degrading to the explicit insufficient state (neutral vocabulary):
```python
if not pool:
    return {
        "score": None,
        "weight": WEIGHTS["price_vs_category"],
        "observed": price_usdt,
        "benchmark": None,
        "flagged": False,
        "reason": "insufficient data — no priced agents available for comparison",
    }
```

**Resolution: FIXED** in `05b4f86` (2026-07-11). Guard added exactly as suggested, after the marketplace fallback (so it also covers the WR-02 non-canonical path): empty pool with a present price returns the explicit insufficient-data state — score `None`, observed price preserved, neutral vocabulary — never `ZeroDivisionError`/`IndexError`. Regression tests: `test_c4_priced_agent_with_no_priced_pools_is_insufficient_not_crash` (component level, stats built from unpriced rows) and `test_score_agent_priced_row_against_priceless_stats_does_not_crash` (public API — the exact probe from this finding; other components still aggregate). The branch is unreachable for the 272-agent census (any priced agent implies a non-empty market pool), so outputs are byte-identical.

## Info

_All six Info findings remain OPEN — documented here for the Phase 5 hardening sweep; none is reachable with current data or blocks Phase 3._

### IN-01: `--generated-at` (and inherited `--captured-at`) accepted with zero format validation into served provenance columns

**File:** `indexer/refresh.py:147-151` (flag), `indexer/refresh.py:80` (used verbatim)
**Issue:** The 02-02 threat model names the boundary "operator-supplied --generated-at lands in the paid product's provenance fields", but no shape check exists: `--generated-at ""` or `--generated-at garbage` persists as-is into a NOT NULL column that Phase 3 will serve. A malformed `--captured-at` additionally reaches `first_seen`, whose first 10 chars render into C5's reason string (`first_seen[:10]`). Operator-trusted offline tool, so Info.
**Fix:** Validate both flags with a strict fullmatch, e.g. an argparse `type` raising on `not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", v)` (routes to the existing argparse error path).

### IN-02: No-I/O import guard only matches column-0 imports — indented imports evade the enforcement test

**File:** `tests/test_scoring_golden.py:168-179`
**Issue:** `FORBIDDEN_IMPORT`/`SQLITE_IMPORT` are anchored with `^` and applied per line via `.match`, so `def f(): import time` or any function-body `import datetime` inside `scoring/` passes the guard while violating the no-wall-clock invariant the test exists to enforce (flagged because it weakens an enforcement test, not as style).
**Fix:** Parse instead of grep — walk `ast.parse(path.read_text())` for `ast.Import`/`ast.ImportFrom` nodes and assert module names against the forbidden set; catches any nesting.

### IN-03: `fmt_price` renders nonzero prices below 1e-8 as "0" (and -0.0 as "-0") in outward text

**File:** `scoring/components.py:57-59`
**Issue:** `f"{p:.8f}"` truncates at 8 decimals, so `fmt_price(4e-9) == "0"` — a reason would state "price 0 USDT" for a nonzero price, a factual-accuracy defect in a defamation-sensitive surface. Unreachable today (smallest real price is 1.5e-05) and deterministic, so Info.
**Fix:** Widen precision when the 8-decimal form collapses: `s = f"{p:.8f}".rstrip("0").rstrip("."); return s if (p == 0 or s not in ("0", "-0")) else f"{p:.12f}".rstrip("0").rstrip(".")` — or document the supported price range at the parse boundary.

### IN-04: `grade_for` raises StopIteration for scores below 0

**File:** `scoring/engine.py:43-44`
**Issue:** `next(g for g, lo in GRADE_BANDS if score >= lo)` has no default; `grade_for(-1)` raises StopIteration (which becomes RuntimeError inside any generator). Unreachable via `score_agent` (all component scores are >= 0 by construction), so Info-level robustness on an exported function.
**Fix:** `return next((g for g, lo in GRADE_BANDS if score >= lo), "F")` or validate the 0..100 contract with an explicit `ValueError`.

### IN-05: WEIGHTS is a mutable module-level dict; mutation would silently change scores without a version bump

**File:** `scoring/components.py:36-42` (also `scoring/stats.py:21` — frozen `Stats` holds a mutable dict field)
**Issue:** Every component and the engine read `WEIGHTS` at call time; any consumer mutating it changes persisted scores while `SCORE_VERSION` stays "1.0.0", breaking the versioned-scoring guarantee. `Stats(frozen=True)` similarly does not freeze its `category_pools` dict (and makes the generated `__hash__` raise if ever used).
**Fix:** `WEIGHTS = types.MappingProxyType({...})` (stdlib `types` is not in the forbidden-import list; serialization output is unchanged since components copy the float values), and note the dict-field mutability in the `Stats` docstring.

### IN-06: scores table carries no CHECK constraints on grade/confidence vocabulary or the NR-score coupling

**File:** `indexer/db.py:69-80`
**Issue:** `grade`/`confidence` accept any text and nothing enforces `(score IS NULL) = (grade = 'NR')` at the storage layer; the invariants live only in `compute_all`. A future writer bug (or Phase 5 change) could persist inconsistent rows that Phase 3 serves. Application invariants are test-pinned today, so Info.
**Fix:** If adopted, add to the DDL before first production DB ships (CREATE IF NOT EXISTS will not retrofit existing files): `grade TEXT NOT NULL CHECK (grade IN ('A','B','C','D','F','NR'))`, `confidence TEXT NOT NULL CHECK (confidence IN ('low','medium','high'))`, and a table-level `CHECK ((score IS NULL) = (grade = 'NR'))`.

---

_Reviewed: 2026-07-11T00:43:37Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Fix pass: 2026-07-11 — WR-01..03 fixed (commits 86840eb, bd8d922, 05b4f86); IN-01..06 open for Phase 5_
