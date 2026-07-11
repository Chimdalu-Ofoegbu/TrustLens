---
phase: 02-scoring-engine
verified: 2026-07-11T00:41:35Z
status: passed
score: 10/10 must-haves verified
overrides_applied: 0
---

# Phase 2: Scoring Engine Verification Report

**Phase Goal:** Every indexed agent gets a deterministic, explainable, neutrally-worded 0-100 TrustScore with A-F grade — pure functions with no I/O and no wall clock
**Verified:** 2026-07-11T00:41:35Z
**Status:** passed
**Re-verification:** No — initial verification

All commands below were executed against the live codebase during this verification (not taken from SUMMARY claims). Environment: Python 3.14.2, Windows.

## Goal Achievement

### Observable Truths

Merged from ROADMAP Success Criteria (SC1-SC4, the contract) plus plan-specific truths from 02-01-PLAN.md and 02-02-PLAN.md frontmatter (deduplicated).

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | SC1: Same row + same stats + injected as_of scored twice yields byte-identical output (0-100 int, A-F grade, full component breakdown) | ✓ VERIFIED | Independent script: two fresh `build_cards()` runs over all 272 agents — serialized components byte-equal and (score, grade, confidence) tuples equal for every agent; canonical JSON round-trip holds; `test_byte_identity_across_fresh_builds` passes |
| 2 | SC2: All five components return a factual reason string; thin data (5.0 rating, <5 sales) produces flagged low-confidence, never an accusation, never a crash | ✓ VERIFIED | All 272 cards render exactly 5 components; 1360/1360 reasons non-empty; thin-perfect cohort = exactly 42 members, 100% `flagged=True` + `confidence="low"`, grades D:34/F:8, zero in top 20; flagged reason reads "...flagged for thin data (not an assessment of conduct)"; hostile edge rows (0-evidence, 1550-sold unknown category, subscript price) score without raising |
| 3 | SC3: Banned-word test passes over all scoring output — no fraud/scam/fake/manipulat anywhere | ✓ VERIFIED | Independent regex scan `(?i)(fraud\|scam\|fake\|manipulat)`: 0 hits over 272 rendered cards, 272 persisted DB blobs, DISCLAIMER, and all GRADE_DESCRIPTIONS; `grep -rniE` over scoring/ source exit 1 (no matches); dual-layer tests 7+8 in test_scoring_golden.py pass |
| 4 | SC4: `--cov=scoring --cov-fail-under=90` passes including edge cases (0 sales, missing rating, "1.55K"-sold) | ✓ VERIFIED | `python -m pytest -q` exit 0: 170 passed, scoring coverage 100% (167/167 stmts), "Required test coverage of 90% reached"; edge tests present: sold=0 anchor, rating=None (components.py None branches), 1550-sold anchors + golden 3118 (the 1.55K parse case); `--no-cov` escape hatch exits 0 |
| 5 | Golden values + distributions match the research dry-run | ✓ VERIFIED | All 10 goldens reproduce in-process AND from the persisted DB: 3118→(95,A,high), 3345→(94,A,high), 2013→(73,B,medium), 1965→(82,B,high), 2169→(56,C,medium), 2177→(46,D,low), 2791→(41,D,low), 3152→(32,F,low), 2662→(NULL,NR,low), 4137→(NULL,NR,low); grade dist A:12/B:9/C:19/D:54/F:27/NR:151; confidence dist high:14/medium:26/low:232; exact base-rate reason pin for 2013 ("87% of agents with 20+ sales display one (20 of 23)") passes |
| 6 | `python -m indexer.refresh` exits 0 and persists exactly 272 score rows in the same atomic transaction | ✓ VERIFIED | Ran CLI against a fresh DB: exit 0; scores table holds 272 rows; INFO line "scores computed: 121 scored, 151 not rated, version=1.0.0" observed; `compute_all(conn, ...)` sits inside `_persist_records`'s existing `with conn:` block (refresh.py:84-86); rollback test proves no internal commit |
| 7 | NR agents persist score=NULL with grade='NR' — a successful row | ✓ VERIFIED | SQL: 151/151 grade='NR' rows have score IS NULL; 0 non-NR rows have NULL score; NR cards still render all five components |
| 8 | Running refresh twice produces a byte-identical scores table (generated_at defaults to captured_at) | ✓ VERIFIED | Two CLI runs on the same DB: SHA256 over full `SELECT * FROM scores ORDER BY agent_id` dump identical both times (f62aa164c3cc36a1...); stamps generated_at == data_as_of == "2026-07-10T00:00:00Z"; `--generated-at 2026-07-11T09:00:00Z` override stamps generated_at only while data_as_of stays pinned |
| 9 | Persisted grade distribution matches A:12/B:9/C:19/D:54/F:27/NR:151 | ✓ VERIFIED | GROUP BY grade on fresh verification DB and on repo data/trustlens.db both return [('A',12),('B',9),('C',19),('D',54),('F',27),('NR',151)] |
| 10 | All pre-existing tests stay green and the >=90% gate still passes with persist.py included | ✓ VERIFIED | 170 passed (78 pre-existing + Phase 2 additions) exit 0; persist.py measured at 100% (19/19 stmts) under the active gate |

**Score:** 10/10 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `scoring/stats.py` | Stats dataclass + build_stats, min 30 lines | ✓ VERIFIED | 56 lines; category/market pools with `is not None` identity checks (0.0 real price), rated_hi/total_hi/rating_display_pct with total_hi==0 guard |
| `scoring/components.py` | Five pure component functions, WEIGHTS, helpers, constants; min 100 lines | ✓ VERIFIED | 257 lines; SOLD_REF/SUPPORT_REF/THIN_SALES/CRED_FLOOR/MIN_CATEGORY_PRICED/PRICE_DEV_SPAN/WEIGHTS verbatim; log_scale/percentile/fmt_price/_median; all five c_* functions return the frozen dict shape with frozen templates |
| `scoring/engine.py` | score_agent, grade_for, serialize_components, SCORE_VERSION, DISCLAIMER, GRADE_BANDS, GRADE_DESCRIPTIONS; min 60 lines | ✓ VERIFIED | 77 lines; NR rule verbatim, weight renormalization, confidence rubric, sorted-key fixed-separator serialization |
| `scoring/persist.py` | compute_all; the only sqlite3-touching scoring module; no commits; min 30 lines | ✓ VERIFIED | 50 lines; parameterized INSERT only; `COUNT(DISTINCT captured_at)`; DELETE+INSERT self-cleaning; grep confirms no `.commit(` and no f-string SQL |
| `scoring/__init__.py` | Public re-exports | ✓ VERIFIED | Exports WEIGHTS, engine surface, compute_all, Stats/build_stats |
| `tests/test_scoring_golden.py` | Golden pins, distribution pin, dual-layer vocab test, byte-identity over 272 agents; min 80 lines | ✓ VERIFIED | 196 lines; all 10 plan-specified tests present and passing |
| `tests/test_scoring_persist.py` | Persistence proofs; min lines n/a (plan 02-02) | ✓ VERIFIED | 212 lines, 10 tests: exact schema columns, counts/distribution, NR roundtrip, goldens, envelope stamps, recompute byte-identity, rollback, FK IntegrityError, DISTINCT-captured_at, JSON/vocab scan |
| `tests/test_refresh_scores.py` | End-to-end CLI proof; min 50 lines | ✓ VERIFIED | 119 lines, 6 tests: 272 rows + default stamps, exact log line, CLI rerun byte-identity, --generated-at override, grade distribution, RefreshSummary frozen-fields guard |
| `pyproject.toml` | contains `--cov=scoring --cov-fail-under=90` | ✓ VERIFIED | addopts line present exactly once; `packages = ["indexer", "scoring"]` |
| `indexer/db.py` | contains `CREATE TABLE IF NOT EXISTS scores` | ✓ VERIFIED | DDL at db.py:70 with exactly the 8 locked columns (agent_id PK REFERENCES agents(id), score nullable, grade/confidence/score_version/generated_at/data_as_of/components NOT NULL) |
| `indexer/refresh.py` | contains `compute_all` wiring | ✓ VERIFIED | Import at line 30; call inside the atomic transaction at line 86; --generated-at flag at 148; scores INFO log line at 89-92; RefreshSummary untouched |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| scoring/engine.py | scoring/components.py | score_agent builds the five-component dict | ✓ WIRED | engine.py:14-21 imports all five c_* functions; :55-61 builds the dict with all five |
| tests/test_scoring_golden.py | indexer/census.py | load_census over the real census | ✓ WIRED | Import line 17, used in build_rows() line 41; path anchored from `__file__` |
| pyproject.toml | scoring/ | pytest addopts coverage gate | ✓ WIRED | Gate demonstrably active: pytest output prints per-module scoring coverage + "Required test coverage of 90% reached" |
| indexer/refresh.py | scoring/persist.py | compute_all inside `with conn:` after persist() | ✓ WIRED | refresh.py:84-86 — `persist(...)` then `scored, not_rated = compute_all(conn, gen_at, captured_at)` in the same transaction block |
| scoring/persist.py | snapshots table | COUNT(DISTINCT captured_at), never raw rows | ✓ WIRED | persist.py:33, exactly one occurrence; duplicate-rows test proves 3 same-time rows stay "single snapshot" |
| indexer/db.py | scores table | additive CREATE IF NOT EXISTS in DDL tuple | ✓ WIRED | Appended to the DDL tuple; init_db on a fresh DB creates it (proven by fresh-DB CLI run + schema test) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| scoring/persist.py compute_all | rows / snap | `SELECT * FROM agents ORDER BY id` + snapshots GROUP BY | Yes — 272 real rows scored | ✓ FLOWING |
| scores table | score/grade/confidence/components | score_agent over real census data | Yes — pinned distribution + goldens reproduce from persisted rows; components blobs are valid JSON with 5 keys | ✓ FLOWING |
| indexer/refresh.py CLI | scored/not_rated log line | compute_all return | Yes — "121 scored, 151 not rated" observed on live run | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full suite + coverage gate | `python -m pytest -q` | 170 passed, scoring 100%, gate reached, exit 0 | ✓ PASS |
| Subset escape hatch | `python -m pytest tests/test_scoring_golden.py --no-cov -q` | 10 passed, exit 0 | ✓ PASS |
| Refresh end-to-end (fresh DB) | `python -m indexer.refresh --db <fresh>` | exit 0; 272 score rows; exact scores INFO line | ✓ PASS |
| Rerun byte-identity | refresh twice + SHA256 of full scores dump | identical hash f62aa164c3cc36a1... both runs | ✓ PASS |
| --generated-at override | `--generated-at 2026-07-11T09:00:00Z` | generated_at overridden, data_as_of stays 2026-07-10T00:00:00Z | ✓ PASS |
| Golden/NR spot checks via SQL | SELECT on scores table | all 10 goldens match; 151 NULL-score NR rows | ✓ PASS |
| Banned vocab (independent rerun) | regex over 272 rendered cards + 272 DB blobs + source | 0 hits everywhere | ✓ PASS |
| Grep gates | UNIQUE literal, forbidden imports, wall clock, f-string SQL, .commit( | all exit 1 (no matches) | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| SCOR-01 | 02-01, 02-02 | Pure deterministic scoring: 0-100 + A-F + component breakdown | ✓ SATISFIED | Truths 1, 5, 6, 8 — byte-identity proven in-process and across CLI runs; persisted for all 272 agents |
| SCOR-02 | 02-01 | Five locked components, each with a reason string; 5.0-with-<5-sales flagged not accused | ✓ SATISFIED | Truth 2 — all five components implemented with frozen neutral templates; 42-member cohort 100% flagged + low confidence |
| SCOR-03 | 02-01 | Neutral factual wording; never fraud/scam/fake/manipulat | ✓ SATISFIED | Truth 3 — dual-layer test + independent scan, 0 hits across source, rendered cards, and persisted blobs |
| SCOR-04 | 02-01, 02-02 | pytest coverage >=90% on scoring/ incl. edge cases | ✓ SATISFIED | Truths 4, 10 — 100% coverage under the active gate; 0-sales/missing-rating/1550-sold/NR/single-snapshot all test-pinned |

No orphaned requirements: REQUIREMENTS.md maps exactly SCOR-01..04 to Phase 2, and the two plans jointly claim exactly those IDs. Traceability table already marks all four Complete.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| indexer/db.py | 11 | "placeholders" grep hit | ℹ️ Info | False positive — docstring describing parameterized SQL `?` placeholders, not a stub marker |

No TODO/FIXME/stub patterns in any phase file. Note: `listing_age_consistency` always returning `score: None` and the C1 velocity note are NOT stubs — they are the CONTEXT.md-locked honest "insufficient history" degradation for single-snapshot data (never fabricate history), documented as v2 seams in docstrings and pinned by tests.

### Human Verification Required

None. This phase is fully deterministic and offline: pure functions, CLI behavior, and DB state — every success criterion was verified by executing the actual commands (pytest, refresh CLI runs, SQL queries, independent byte-identity and banned-vocabulary scripts). No UI, real-time, or external-service surface exists in this phase.

### Commit Verification

All 9 task commits claimed across both SUMMARYs exist in git history with matching types: f89c3dc, bd5f34a, 2c7c68b, 267d358, 4038c66 (02-01); 8bff39d, 88ecb23, ece7cac, 3e3b884 (02-02).

### Gaps Summary

No gaps. The phase goal is achieved: every indexed agent has a deterministic, explainable, neutrally-worded score persisted to the scores table by `python -m indexer.refresh`, with byte-identical reruns, the banned-vocabulary contract enforced at source/render/persistence layers, and a live 90% coverage gate measuring 100%.

---

_Verified: 2026-07-11T00:41:35Z_
_Verifier: Claude (gsd-verifier)_
