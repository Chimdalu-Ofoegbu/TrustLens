---
phase: 05-scraper-hardening-submission-kit
plan: 01
subsystem: indexer
tags: [httpx, beautifulsoup, scraper, appState, graceful-degradation, pytest, MockTransport, offline-determinism]

# Dependency graph
requires:
  - phase: 01-foundation-data-indexer
    provides: "AgentRecord contract, load_census, derive_category, name_key, and the persist(source=...) seam the scraper reuses verbatim"
  - phase: 02-scoring-engine
    provides: "CANONICAL_CATEGORIES gate in scoring/components.py that refuses non-canonical category text (why Option B keeps category derived)"
provides:
  - "indexer/scraper.py — polite okx.ai fetch (httpx sync, UA TrustLens/1.0, 1.1s sleep-between, sha256-URL disk cache under data/cache/, 15s timeout, single attempt) + appState JSON parser + scrape_agents() that returns [] on any failure"
  - "--scrape CLI flag on indexer.refresh + merge() (census floor, scrape wins per-id) feeding the unchanged persist path"
  - "tests/test_scraper.py (18 offline canned-fixture tests) + 4 HTML fixtures proving success parse and six graceful-degradation modes"
  - "A test-mapped STRIDE register (T-05-01..09) with every 'mitigate' disposition exercised by a test"
affects: [05-02 README (documents --scrape + the --no-cov footgun), 05-03 submission kit, INDX-05 recurring re-scrapes v2]

# Tech tracking
tech-stack:
  added: []  # zero new deps — httpx 0.28.1 + beautifulsoup4 4.15.0 already pinned
  patterns:
    - "JSON-island-first parsing: BeautifulSoup(html.parser).find(id='appState') + json.loads over stable JSON keys, never hashed DOM class selectors"
    - "Graceful-degradation source: every failure path (fetch + parse) returns None/[] + exactly one WARNING; scrape_agents is the belt that guarantees a scrape can never reach refresh's exit-code contract"
    - "Mutable _pacer list threads sleep-between-network state so the first fetch of a run never sleeps and a cache hit never sleeps"

key-files:
  created:
    - "indexer/scraper.py"
    - "tests/test_scraper.py"
    - "tests/fixtures/okx_detail_3345.html"
    - "tests/fixtures/okx_detail_empty_spa.html"
    - "tests/fixtures/okx_detail_changed_markup.html"
    - "tests/fixtures/okx_detail_missing_keys.html"
  modified:
    - "indexer/refresh.py"

key-decisions:
  - "Option B locked: the scraper enriches only sold/rating/price/positive_pct and leaves category DERIVED (category_source unchanged) — a raw okx.ai code can never reach a reason string, and Phase 2 percentiles never shift"
  - "Merged --scrape batch persists as one source='census' snapshot (per-record scrape provenance deferred to v2/INDX-05) to preserve the determinism contract and the existing test_refresh aggregate invariants"
  - "Scraper imported locally inside refresh.main() only when --scrape is passed, so the default offline path never loads the httpx-heavy module"
  - "Success fixture synthesized as a structurally-faithful appState island with the verified real values for agent 3345 (no saved probe HTML was present in the repo); CJK name round-trips through UTF-8"

patterns-established:
  - "Offline scraper tests: httpx.MockTransport for fetch/degradation control flow + saved HTML files for the parser; monkeypatch scraper.CACHE_DIR to tmp_path so a test never writes the repo cache; NEVER a real Client against okx.ai"
  - "Pitfall-1 exit-code guard: patch indexer.scraper.scrape_agents to [] to simulate total scrape failure and assert refresh --scrape still exits 0 with 272 census rows"

requirements-completed: [INDX-04, OPS-03]

# Metrics
duration: 20min
completed: 2026-07-11
---

# Phase 5 Plan 01: Polite okx.ai Scraper + Canned-Response Tests Summary

**A `--scrape`-gated okx.ai appState-JSON scraper whose sole guaranteed behavior is graceful degradation to the census on every failure path — proven by 18 offline canned-fixture tests, with the default refresh still exiting 0 on 272 census rows and the full suite green at 314.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-11T15:30:00Z
- **Completed:** 2026-07-11T15:49:32Z
- **Tasks:** 2
- **Files created:** 6 (scraper module, test file, 4 fixtures)
- **Files modified:** 1 (indexer/refresh.py)

## Accomplishments
- `indexer/scraper.py`: cache-first polite fetch (UA `TrustLens/1.0`, 1.1s sleep-between, sha256-URL cache, 15s timeout, single attempt) + `parse_appstate` (JSON-island-first) + `scrape_agents` that swallows every failure and returns `[]`.
- Wired `--scrape` into `indexer.refresh` with a `merge()` step (census is the floor, scrape wins per-id) feeding the unchanged `persist` seam — the 0/1/2 exit contract and the default `source="census"` batch are untouched.
- 18 offline tests + 4 fixtures covering the real-shape success parse and all six degradation modes (empty-SPA, changed-markup, missing-keys, truncated-JSON, 403, timeout), plus zero-score-unrated, cache-hit-no-network, merge semantics, the Pitfall-1 exit-0/272 invariant, and the no-server-imports-scraper rule.
- Full suite: **314 passed** (296 baseline + 18 new), scoring coverage 100%, gate ≥90% intact — offline determinism preserved.

## Task Commits

Each task was committed atomically (TDD: RED demonstrated, GREEN committed):

1. **Task 1: Build indexer/scraper.py — polite fetch + appState parse + graceful scrape_agents** - `833c6f9` (feat)
2. **Task 2: Wire --scrape into refresh.py (merge, census-floor) + canned-fixture test suite** - `5af755b` (feat)

_Note: Task 2 was developed test-first — the RED run showed 3 failing tests (two `merge` ImportErrors + one `unrecognized arguments: --scrape`), 15 passing; the refresh wiring turned them GREEN (18/18). Committed at GREEN._

## Files Created/Modified
- `indexer/scraper.py` - Polite okx.ai fetch + appState JSON parser + `scrape_agents` orchestrator; every failure returns None/[] + one WARNING, never raises. Category stays derived (Option B).
- `indexer/refresh.py` - Added `merge()`, the `--scrape` flag, and an 8-line merge step in `main()` (local scraper import; no exit-code or default-source change).
- `tests/test_scraper.py` - 18 offline canned-fixture tests (success + 6 degradation modes + merge + exit-code invariant + no-server-import rule).
- `tests/fixtures/okx_detail_3345.html` - Structurally-faithful success fixture (verified real values for agent 3345; CJK name round-trips in UTF-8).
- `tests/fixtures/okx_detail_empty_spa.html` - Empty-SPA shell, no appState script.
- `tests/fixtures/okx_detail_changed_markup.html` - Success doc with the script id renamed to `appStateXYZ`.
- `tests/fixtures/okx_detail_missing_keys.html` - Valid appState JSON but `appContext.initialProps` is `{}`.

## Decisions Made
- **Option B (category stays derived):** the scraper enriches sold/rating/price/positive_pct only; `category_source` remains "derived" so scraped codes never break neutral language or shift Phase 2 percentiles (locked in plan + 05-RESEARCH).
- **Merged batch persists as `source="census"`:** per-record scrape provenance is a documented v2/INDX-05 seam; keeping source tagging out of `main()` preserves the `test_refresh` aggregate invariant `snapshots.source != 'census' == 0`.
- **Local scraper import under `--scrape`:** the default offline path never imports the scraper module, so import cost and offline guarantees are unchanged.
- **Import style follows census.py:** full module paths (`from indexer.models import AgentRecord`, `from indexer.parse import name_key`, `from indexer.category import derive_category`) rather than package-level re-exports (indexer/__init__.py is minimal and was left untouched).
- **Synthetic success fixture:** no saved okx.ai probe HTML existed in the repo (the research probe bodies were session scratchpad, not committed), so the plan's documented fallback was used — a full HTML doc whose only load-bearing element is the appState island with the verified 3345 values.

## Deviations from Plan

None - plan executed exactly as written.

Both tasks matched their acceptance criteria on the first implementation pass; the only iteration was the intended TDD RED→GREEN transition for Task 2. No deviation rules (1-4) were triggered — no bugs, missing-critical functionality, blocking issues, or architectural changes surfaced. Zero auto-fix attempts consumed.

## Threat Model Compliance

All `mitigate` dispositions in the plan's STRIDE register are implemented and test-covered:

| Threat ID | Mitigation | Where proven |
|-----------|-----------|--------------|
| T-05-01 (field-cast tampering) | every cast in a try/except → None+WARNING | `test_parse_zero_score_is_unrated`, `test_parse_truncated_json_returns_none` |
| T-05-02 (scraped category → reason text) | Option B: category never overwritten | `test_parse_success_real_page` asserts `category_source=="derived"` |
| T-05-03 (cache-filename traversal) | filename = `sha256(url)` only | `test_fetch_200_writes_cache` / `_cache_path` |
| T-05-04 (CJK/newline log injection) | `%r` logging; no raw body | degradation tests assert `"\n" not in message` |
| T-05-05 (impoliteness DoS) | 1.1s sleep-between + single attempt + cache | `test_fetch_cache_hit_no_network` (no sleep on cache hit) |
| T-05-06 (scrape breaks determinism) | `scrape_agents` → []; exit driven by csv/db | `test_refresh_scrape_all_403_still_exits_0_with_census` |
| T-05-07 (SSRF via detail URL) | ids constrained to `^\d+$` | `test_detail_url_rejects_non_numeric_id` |
| T-05-08 (scraper reachable from request path) | offline-only | `test_no_server_module_imports_scraper` |
| T-05-09 (giant-response exhaustion) | accepted; 15s timeout + single attempt bound it | documented (no streaming cap, out of timebox) |

No new security-relevant surface was introduced beyond the plan's threat_model.

## Known Stubs

None. The scraper is a real working fetch+parse path (JSON extraction verified against the real-shape fixture), the fixtures carry real verified values, and the `--scrape` wiring is fully functional. `DEMO_AGENT_IDS = ("3345",)` is a deliberately bounded demo set (full-marketplace enrichment is the documented v2/INDX-05 deferral), not a stub.

## Issues Encountered
None. The environment note said "Is directory a git repo: No", but the working tree is in fact a git repo on `main` (confirmed via `git rev-parse`/`git log`); normal commits with hooks succeeded as intended.

## User Setup Required
None - no external service configuration required. The `--scrape` path is optional, off by default, and requires no secrets; `data/cache/` is already gitignored.

## Next Phase Readiness
- OPS-03 (scraper portion) satisfied: canned tests added, full suite green (314), no coverage-gate change.
- 05-02 (README) can now document the verified `--scrape` flag and the `--no-cov` subset footgun.
- Carried forward: 05-02 README + 05-03 submission kit remain; the Docker-engine demo rehearsal stays a human-only final-checklist item (unchanged Phase 3/4 carry).

## Self-Check: PASSED

---
*Phase: 05-scraper-hardening-submission-kit*
*Completed: 2026-07-11*
