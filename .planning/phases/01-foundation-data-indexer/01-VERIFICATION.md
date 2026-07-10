---
phase: 01-foundation-data-indexer
verified: 2026-07-10T23:59:00Z
status: passed
score: 22/22 must-haves verified
overrides_applied: 0
---

# Phase 1: Foundation & Data Indexer Verification Report

**Phase Goal:** The 272-agent census is reliably parsed into a queryable SQLite store on a pinned, test-ready scaffold — the data foundation every downstream feature reads
**Verified:** 2026-07-10T23:59:00Z
**Status:** passed
**Re-verification:** No — initial verification

All evidence below was gathered by running the actual code against a fresh scratch database and probing results directly with SQL — not by trusting SUMMARY.md claims. 73/73 independent DB probe checks passed; the full suite (71 tests) exits 0; the bare CLI run exits 0.

## Goal Achievement

### Observable Truths

**Roadmap Success Criteria (the phase contract):**

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1   | `python -m indexer.refresh` loads exactly 272 agents from the census CSV into SQLite with zero network access | ✓ VERIFIED | Bare run: exit 0, logs `refresh complete: 272 agents, 272 snapshots appended, 1 field warning(s), source=census`. Fresh-DB probe: `SELECT COUNT(*) FROM agents` = 272. Zero network: `grep -rE "^\s*(import|from)\s+(httpx|requests|urllib|socket)" indexer/*.py` = 0 matches; import graph is stdlib-only (csv, sqlite3, re, unicodedata, logging, argparse, pathlib) |
| 2   | All four observed census edge cases parse to correct values under fixture tests: "1.55K sold" → 1550; "0.0₄15 USDT" → 0.000015; shifted rating column → missing rating (never a false near-zero rating); multiline taglines and CJK names preserved with NFKC-normalized lookup | ✓ VERIFIED | Direct parser probes: `parse_sold('1.55K sold')`=1550, `parse_price('0.0₄15 USDT')`=1.5e-05, `parse_rating_positive('5','','5 USDT')`=(None,None), `name_key('这个能吃吗？')=='这个能吃吗?'`=True. End-to-end in DB: id 3118 sold=1550, id 2023 price_usdt=0.000015, ids 2013/4489/3091 rating=NULL (price echoes), id 3345 name preserved with U+FF1F + folded name_key, id 1500 tagline contains `\n`. 36 fixture tests in tests/test_parse.py pass |
| 3   | `agents` persists id, name, category (documented deterministic method), price, sold, rating, positive_pct, tagline, first_seen, last_seen; `snapshots` gains one row per refresh; rerun does not corrupt or duplicate agents | ✓ VERIFIED | PRAGMA table_info probe: all 13 agents columns + 8 snapshots columns present, WAL on, 3 indexes exist. Category method documented in indexer/category.py docstring (ordered table, first-match-wins, "categories derived from listing text" disclosure); full-census determinism sweep: two passes identical. Rerun probe: run1 (2026-07-10) then run2 (2026-07-11) → 272 agents / 544 snapshots, id 3345 first_seen=2026-07-10T00:00:00Z preserved, last_seen=2026-07-11T00:00:00Z updated |

**Plan-level truths (detail under the SCs):**

| #   | Truth (source) | Status | Evidence |
| --- | -------------- | ------ | -------- |
| 4   | pytest 9.1.1 runs from repo root and exits 0 (01-01) | ✓ VERIFIED | `python -m pytest --version` → pytest 9.1.1; `python -m pytest -q` → 71 passed, exit 0 |
| 5   | parse_sold: '1.55K sold'→1550, prose→None, ''→0 (01-01) | ✓ VERIFIED | Direct probe: 1550 / None / 0; also 3M→3000000, '2,500 sold'→2500 |
| 6   | parse_price subscript: 0.0₄15→0.000015, 0.0₅1→0.000001, never the 10x off-by-one (01-01) | ✓ VERIFIED | Direct probe: 1.5e-05 and 1e-06 exactly; id 1851 in DB = 1e-06 |
| 7   | parse_rating_positive('5','','5 USDT') → (None, None) — price echo never stored as rating (01-01) | ✓ VERIFIED | Direct probe returns (None, None); DB: id 4489 (the fake perfect 5) rating IS NULL |
| 8   | name_key NFKC-casefolds U+FF1F to ASCII '?' (01-01) | ✓ VERIFIED | Direct probe True; DB row 3345 name_key = '这个能吃吗?' |
| 9   | derive_category returns one of exactly 9 buckets for ANY input, never empty/raises (01-02) | ✓ VERIFIED | len(CATEGORIES)=9; fallback probe 'zzzz/qqqq'→Other Services; full-census sweep 0 empty categories |
| 10  | Full census yields the exact verified distribution 70/45/41/30/27/22/17/15/5 (01-02) | ✓ VERIFIED | DB GROUP BY probe equals the pinned dict exactly |
| 11  | Exactly ids {3723, 3932, 3700, 3701, 3746} land in Other Services (01-02) | ✓ VERIFIED | Live sweep over the real CSV: set equality True |
| 12  | 'not astrology' negation + 'trading volume' exclusion behave as researched (01-02) | ✓ VERIFIED | ChainAlmanac→Market Data & Analytics; VolumeBot ('tracks trading volume')→Market Data & Analytics |
| 13  | init_db creates agents+snapshots+indexes on fresh file, no-op on rerun (01-03) | ✓ VERIFIED | Fresh scratch DB probe: both tables + idx_agents_name_key/idx_agents_category/idx_snapshots_agent exist; second refresh (init_db reruns) succeeded unchanged |
| 14  | Database runs in WAL journal mode (01-03) | ✓ VERIFIED | `PRAGMA journal_mode` = 'wal' on the scratch DB |
| 15  | Upserting same id twice keeps 1 row, preserves first_seen, updates last_seen (01-03) | ✓ VERIFIED | Rerun probe on id 3345 (see truth 3); `first_seen=excluded` absent from db.py (grep 0) |
| 16  | Two agents with identical name_key both persist — no uniqueness constraint (01-03) | ✓ VERIFIED | DB probe: COUNT WHERE name_key = name_key of id 2791 → 2 (ids 2791+2662); `grep -cE "UNIQUE" indexer/db.py` = 0 |
| 17  | Hostile content (quotes, SQL fragments, newlines, CJK) round-trips inertly via parameterized queries (01-03) | ✓ VERIFIED | tests/test_db.py contains the `"Rob'); DROP TABLE agents;--"` round-trip test (passing); `grep -E "execute\(\s*f[\"']" indexer/*.py` = 0 matches (no f-string SQL); real CJK/multiline census content round-tripped byte-identical in DB probes |
| 18  | Snapshots always append — rerun duplication by design (01-03) | ✓ VERIFIED | 544 snapshots after two runs; test_db.py pins same-captured_at duplication; insert_snapshot docstring documents the locked behavior |
| 19  | data/trustlens.db holds 272 agents, one snapshot per agent per refresh (01-04) | ✓ VERIFIED | Bare-run DB and scratch DB both: 272 agents, 272 snapshots per run |
| 20  | Edge-case rows store exact verified values incl. 4137 sold=0 with logged warning (01-04) | ✓ VERIFIED | All 11 fixture rows probed exact (3345, 3118, 2023, 2013, 4137, 4489, 2169, 3091, 2791, 1851, 1500); CLI stderr shows exactly one warning `row 182 id=4137: sold unparseable, storing 0` — row+id only, no cell text |
| 21  | Every agent row has non-empty category with category_source='derived'; every snapshot source='census' (01-04) | ✓ VERIFIED | Probes: 0 empty categories, 0 rows with category_source != 'derived', 0 snapshots with source != 'census' |
| 22  | CLI exit-code contract 0/1/2 (01-04) | ✓ VERIFIED | Bare run → 0; `--csv data/does-not-exist.csv` → 1; dateless filename without --captured-at → 2 (and → 0 with explicit --captured-at) |

**Score:** 22/22 truths verified (plan-04's "bare run 272 agents offline" truth is deduplicated into roadmap SC1 — same evidence)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `pyproject.toml` | Pinned deps + dev extras + pytest config; contains `fastmcp>=3,<4` | ✓ VERIFIED | fastapi==0.139.0, fastmcp>=3,<4, beautifulsoup4==4.15.0, pytest==9.1.1 all present; `[tool.pytest.ini_options]` testpaths=["tests"] |
| `indexer/models.py` | `class AgentRecord` frozen dataclass contract | ✓ VERIFIED | 25 lines; frozen dataclass with all 11 fields, category_source default 'derived'; imported by db.py + census.py |
| `indexer/parse.py` | 4 pure parsers, min 60 lines | ✓ VERIFIED | 79 lines; exports parse_sold, parse_price, parse_rating_positive, name_key; stdlib only; strict fullmatch |
| `tests/test_parse.py` | Fixture tests, min 60 lines | ✓ VERIFIED | 193 lines; 36 tests passing; imports from indexer.parse |
| `indexer/category.py` | ORDERED_RULES 9-bucket table + derive_category, min 80 lines | ✓ VERIFIED | 136 lines; exports derive_category, ORDERED_RULES, FALLBACK, CATEGORIES; SUBSTRING_KEYWORDS mechanics override documented (01-02 deviation, distribution reproduces exactly) |
| `tests/test_category.py` | 272-row distribution pin + spot checks, min 60 lines | ✓ VERIFIED | 166 lines; 14 tests; literal `"Market Data & Analytics": 70` pin present; reads the real census CSV |
| `indexer/db.py` | DDL, WAL connect, idempotent upsert, snapshot append; contains `ON CONFLICT(id) DO UPDATE`, min 70 lines | ✓ VERIFIED | 145 lines; exports connect, init_db, upsert_agent, insert_snapshot; first_seen absent from DO UPDATE SET |
| `tests/test_db.py` | Schema/WAL/upsert/collision/FK/injection tests, min 70 lines | ✓ VERIFIED | 211 lines; 11 tests; DROP TABLE injection + IntegrityError FK tests present |
| `indexer/census.py` | load_census csv+parse+category wiring, min 50 lines | ✓ VERIFIED | 93 lines; exports load_census; utf-8-sig DictReader; warnings carry row+id only |
| `indexer/refresh.py` | persist() seam + refresh() + argparse main(); contains `def main`, min 70 lines | ✓ VERIFIED | 155 lines; exports persist, refresh, main; `if __name__ == "__main__"` entry; filename-derived captured_at, never wall clock |
| `tests/test_refresh.py` | Full-census integration suite, min 90 lines | ✓ VERIFIED | 284 lines; 10 tests; 544/0.000015/1550 pins all present (grep ≥2 each) |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| tests/test_parse.py | indexer/parse.py | direct import | ✓ WIRED | `from indexer.parse import name_key, parse_price, parse_rating_positive, parse_sold` (line 7) |
| pyproject.toml | pytest | dev extra + ini_options | ✓ WIRED | `pytest==9.1.1` pin + `[tool.pytest.ini_options]`; `python -m pytest --version` → 9.1.1 |
| tests/test_category.py | indexer/category.py | direct import | ✓ WIRED | line 16 |
| tests/test_category.py | census CSV | DictReader, path relative to test file | ✓ WIRED | `okx-marketplace-census-2026-07-10` referenced; suite passes from repo root |
| indexer/db.py | indexer/models.py | AgentRecord parameter type | ✓ WIRED | `from indexer.models import AgentRecord` (line 21) |
| tests/test_db.py | indexer/db.py | direct import | ✓ WIRED | line 13 |
| indexer/refresh.py | indexer/census.py | load_census call | ✓ WIRED | import line 23; called in refresh() line 69 |
| indexer/refresh.py | indexer/db.py | connect/init_db/upsert_agent/insert_snapshot | ✓ WIRED | import line 24; all four used in refresh()/persist() |
| indexer/census.py | indexer/parse.py + indexer/category.py | parser + derive_category calls | ✓ WIRED | imports lines 24-26; all five functions invoked per row |
| `python -m indexer.refresh` | data/trustlens.db | default CLI paths | ✓ WIRED | DEFAULT_CSV/DEFAULT_DB constants; bare run populated data/trustlens.db (272 agents probed) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| indexer/refresh.py CLI | records | load_census → real census CSV | Yes — 272 real AgentRecords with parsed values | ✓ FLOWING |
| data/trustlens.db agents | all columns | persist() → upsert_agent parameterized writes | Yes — probed real values (CJK names, subscript prices, K-suffix sold) | ✓ FLOWING |
| data/trustlens.db snapshots | time series | insert_snapshot per agent per refresh | Yes — 272/run, 544 after rerun, source='census' | ✓ FLOWING |

No hollow artifacts: every module in the chain transforms and persists real census data, verified end-to-end by SQL probes.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full suite green | `python -m pytest -q` | 71 passed, exit 0 | ✓ PASS |
| Bare CLI loads census | `python -m indexer.refresh` | exit 0, "272 agents", 1 field warning | ✓ PASS |
| Fresh DB load + schema + edge rows + aggregates | scratch-DB probe script (73 checks) | 73/73 passed | ✓ PASS |
| Idempotent rerun | refresh twice, different captured_at | 272 agents / 544 snapshots, first_seen preserved | ✓ PASS |
| Missing CSV | `--csv data/does-not-exist.csv` | exit 1, clean error, no traceback | ✓ PASS |
| Dateless filename | `--csv census.csv` (no date, no --captured-at) | exit 2; exit 0 with explicit --captured-at | ✓ PASS |
| Category determinism + membership | live sweep over real CSV | Other Services = exactly {3700,3701,3723,3746,3932}; two passes identical | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
| ----------- | -------------- | ----------- | ------ | -------- |
| INDX-01 | 01-04 | `python -m indexer.refresh` populates SQLite from census CSV with zero network access | ✓ SATISFIED | Bare run exit 0, 272 agents in data/trustlens.db, zero network imports in indexer/ |
| INDX-02 | 01-01, 01-04 | Edge cases: K-suffix sold, subscript-zero prices, missing ratings (price echo), multiline taglines, CJK names | ✓ SATISFIED | All parser probes + end-to-end DB values exact (truths 5-8, 20) |
| INDX-03 | 01-02, 01-03, 01-04 | SQLite persists agents (all spec columns) + snapshots time series | ✓ SATISFIED | Schema probe complete; category populated by documented deterministic method; snapshots append per refresh |

No orphaned requirements: REQUIREMENTS.md maps exactly INDX-01/02/03 to Phase 1; all three are claimed by plans and marked `[x]` Complete with traceability updated. INDX-04 (scraper) is Phase 5 by design — its seam (`persist()` with source tag, `category_source` update path) exists and is test-proven without any scraper code in this phase.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | none | — | — |

Scan results: zero TODO/FIXME/XXX/HACK/placeholder/not-implemented markers in indexer/ and tests/ (the two grep hits for "placeholder" are prose about SQL parameterized placeholders — the mitigation itself, not a stub). No f-string SQL, no wall-clock reads (`datetime.now|utcnow|time.time` grep = 0), no network imports, no empty-return stubs. All 12 commit hashes claimed across the four SUMMARYs exist in git log. Census CSV untouched (git porcelain clean); data/trustlens.db and WAL sidecars gitignored (`*.db`, `*.db-wal`, `*.db-shm`).

### Human Verification Required

None. Every phase success criterion is programmatically observable (CLI exit codes, SQL-probed values, static import analysis) and was observed directly.

### Gaps Summary

No gaps. The phase goal is achieved in the codebase, verified independently of SUMMARY claims:

- The bare `python -m indexer.refresh` command loads exactly 272 agents offline with a deterministic seed timestamp.
- Every empirically verified edge case ("1.55K"→1550, "0.0₄15"→0.000015, price-echo→NULL rating including the fake perfect '5', CJK/multiline preserved, NFKC name_key) stores its exact value end-to-end.
- The agents/snapshots schema matches the locked spec, category is populated by a documented deterministic 9-bucket method reproducing the verified distribution exactly, and rerun is idempotent (272/544, first_seen preserved).

Two informational notes (no action required from a code perspective):

1. ROADMAP.md Progress table still reads "1. Foundation & Data Indexer — 3/4 Plans Complete, In Progress" while all four plan checkboxes are `[x]` — stale bookkeeping row for the orchestrator to update at phase completion.
2. Plan 01-02 introduced a documented mechanics-level deviation (`SUBSTRING_KEYWORDS = {"cafe", "restaurant"}`) to reproduce the research-verified distribution without editing the locked keyword table; it is commented in code, pinned by the distribution test, and affects exactly one census row — an acceptable, well-evidenced fix, not a gap.

---

_Verified: 2026-07-10T23:59:00Z_
_Verifier: Claude (gsd-verifier)_
