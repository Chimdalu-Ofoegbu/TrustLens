---
phase: 05-scraper-hardening-submission-kit
verified: 2026-07-11T17:40:00Z
status: human_needed
score: 16/16 must-haves verified
overrides_applied: 0
re_verification:
human_verification:
  - test: "Demo-script end-to-end rehearsal against a clean-clone `docker compose up`"
    expected: "Start the Docker Desktop engine, run `docker compose up` on a clean clone, confirm `curl -s http://localhost:8000/healthz` is healthy, then run the demo's five beats live: score_agent(\"这个能吃吗？\") -> A/94/high, score_agent(\"GlassDesk\") -> D/45/low with the verbatim reason string, the leaderboard at / shows 272 agents, and the 402->paid 0.01 USDT flow. Every number is already DB-verified; this step is the recorded run-through."
    why_human: "The Docker Desktop engine will not start in the build environment (`docker info` fails — a carried Phase-3/4 blocker). The phase goal explicitly folds this rehearsal into the final human checklist ('This phase PREPARES materials — the Docker rehearsal folds into the human checklist (engine down)'). The demo script IS proven executable (all data verified real against the built DB; the identical app is proven in-process and against live uvicorn in Phases 3/4; Dockerfile + docker-compose.yml exist and are runnable once the engine is up) — only the physical engine-up run remains."
---

# Phase 5: Scraper, Hardening & Submission Kit Verification Report

**Phase Goal:** The service is submission-ready — refresh path proven with graceful fallback, full test suite green, README and demo materials complete and rehearsed against the container.
**Verified:** 2026-07-11T17:40:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

Every must-have across all three plans was verified EMPIRICALLY against the actual codebase (commands run, DB queried, tests executed) — SUMMARY claims were used only as a map, then independently proven. All 16 must-have truths are VERIFIED. The single reason the phase is `human_needed` rather than `passed` is the tail clause of ROADMAP Success Criterion #4 ("…and the demo script has been executed once end-to-end against a clean-clone `docker compose up`") — a physical Docker-engine run that the phase design (goal statement, CONTEXT, Plan 03) explicitly defers to the final human checklist because the engine is down in the build environment (carried Phase-3/4 blocker). The demo script itself is proven executable and grounded in DB-verified real data.

### Observable Truths

| #  | Truth | Status | Evidence |
| -- | ----- | ------ | -------- |
| 1  | Default `python -m indexer.refresh` (no flag) loads exactly 272 census agents, exits 0, full suite stays green | ✓ VERIFIED | Ran refresh -> "272 agents, 272 snapshots, source=census"; real exit code captured = 0; DB query: agents=272, census snapshots=272, non-census=0. Full suite 317 passed. |
| 2  | `--scrape` with every request 403'd exits 0 with 272 census rows + a WARNING (scrape failure never changes exit code) | ✓ VERIFIED | Ran `main(["--scrape",…])` with a 403 MockTransport injected + empty temp CACHE_DIR: EXIT_CODE=0, AGENTS=272, NON_CENSUS_SNAPSHOTS=0, WARNINGS=1 ("fetch non-200 … status=403"). Pitfall-1 empirically proven. |
| 3  | parse_appstate returns source='scrape' AgentRecord (id 3345, sold 539, rating 5.0, price 0.01, positive_pct 100.0) from the saved 200 HTML | ✓ VERIFIED | Ran parse_appstate on tests/fixtures/okx_detail_3345.html: id='3345', sold=539, rating=5.0, price_usdt=0.01, positive_pct=100.0, category_source='derived'; CJK name round-trips ('这个能吃吗？', 6 chars). |
| 4  | Every scraper failure mode (403/5xx, timeout/network, no appState, JSON error, missing keys, field cast miss) returns None/[] + one WARNING, never raises | ✓ VERIFIED | 18 offline canned tests pass; code review of scraper.py confirms every path guarded (try/except httpx.HTTPError, non-200 branch, appState-missing branch, json/KeyError/TypeError branch, field-cast branch, scrape_agents belt). test names cover each mode. |
| 5  | No module under server/ imports indexer.scraper (scraping is offline-only, never request-path) | ✓ VERIFIED | Grep for `indexer.scraper|import scraper|from scraper` across entire server/ tree: zero matches. test_no_server_module_imports_scraper passes. |
| 6  | README.md exists at repo root covering, in order, all 11 required sections incl. the exact OKX ASP steps | ✓ VERIFIED | README.md (148 lines). Section-heading scan confirms locked order: what-it-is → Local run → Tests → Docker → --scrape → MCP Inspector → x402 → Configuration → Mock→SDK → Deploy → Register on OKX.AI (ASP). |
| 7  | README quotes both OKX ASP prompts VERBATIM ("Help me register an A2MCP ASP on OKX.AI using Onchain OS" + "Help me list my ASP on OKX.AI using Onchain OS") | ✓ VERIFIED | Both exact strings present in README.md (substring assertion passed). |
| 8  | README contains the verified Inspector command, verbatim curl pre-registration check, pip/uvicorn/docker-compose commands, and the Onchain OS install command | ✓ VERIFIED | All present: `npx --yes @modelcontextprotocol/inspector`, `curl -i -X POST`, `pip install -e .[dev]`, `uvicorn server.main:app`, `docker compose up`, `npx skills add okx/onchainos-skills --yes -g`. |
| 9  | Every human-only step (deploy, wallet login, ASP registration/listing submission, real creds, Docker engine start) explicitly marked HUMAN-ONLY | ✓ VERIFIED | 6 HUMAN-ONLY marks; context lines cover Docker engine (L52), real creds (L114), deploy (L118), wallet login (L130), review email (L146), and a closing stop-conditions summary (L148) covering deploy/wallet/registration/listing/creds. |
| 10 | No banned vocabulary (fraud/scam/fake/manipulat) anywhere in README.md | ✓ VERIFIED | Regex `(?i)(fraud|scam|fake|manipulat)` -> 0 hits in README.md (independent scan). |
| 11 | submission/demo-script.md is a 90s storyboard: problem → live MCP call → anomaly flag (GlassDesk 3465 D/45/low vs 3345 A/94/high) → agent-calling-agent → leaderboard + on-chain revenue, executable against clean-clone docker compose up (Docker start HUMAN-ONLY) | ✓ VERIFIED | 5-beat table present; contains "GlassDesk", verbatim reason fragment "not an assessment of conduct", "docker compose up", HUMAN-ONLY Docker marker. DATA VERIFIED against built DB (see Data-Flow Trace). |
| 12 | submission/x-post-draft.md is a launch thread tagged #OKXAI: neutral, factual, no accusations, one-call verdict + determinism + on-chain pay-per-call | ✓ VERIFIED | 6-tweet thread; #OKXAI on tweets 1 and 6; covers determinism (score_version + data_as_of + pure functions), 0.01 USDT on X Layer, Factor/TO1/Internet Court differentiation; 0 banned hits. |
| 13 | submission/listing-copy.md has name TrustLens, tagline ≤80 chars, description, category "Software Services", price 0.01 USDT, + endpoint + methodology URL placeholders | ✓ VERIFIED | Name TrustLens; primary tagline 66 chars (≤80); "Software Services"; "0.01 USDT"; `https://<host>/mcp` + `<base>/#methodology` placeholders; 4 alternate taglines all ≤80. |
| 14 | A language-gate test asserts the banned regex matches nowhere in submission/*.md OR README.md, and asserts the tagline ≤80 chars | ✓ VERIFIED | tests/test_submission_language.py: 3 tests pass. Reviewed source — scans sorted(submission/*.md) + README (asserts README in scope), enforces `**Tagline:**` line ≤80. Independent scan: 0 banned hits across all 4 outward files. |
| 15 | Full pytest suite stays green with the new language-gate test added (no coverage-gate change) | ✓ VERIFIED | `python -m pytest -q` -> 317 passed, scoring coverage 100% (gate ≥90% intact). |
| 16 | Full suite green including scraper canned tests + e2e x402-mocked call (OPS-03) | ✓ VERIFIED | 317 passed total; tests/test_scraper.py 18 passed (--no-cov); e2e x402 tests carried from Phase 4 present in the green suite. |

**Score:** 16/16 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `indexer/scraper.py` | Polite fetch + appState parser + graceful scrape_agents (min 90) | ✓ VERIFIED | 213 lines. UA TrustLens/1.0, sha256 cache, RATE_S sleep-between, 15s timeout, single attempt, Option-B derived category. Imports clean, zero new deps. WIRED into refresh.py; data FLOWING (parse produces correct 3345 record). |
| `indexer/refresh.py` | --scrape flag + merge (census floor) feeding unchanged persist | ✓ VERIFIED | 262 lines. `merge()`, `--scrape` (store_true), local scraper import under flag, exit-code/default-source untouched. `--scrape` in --help. |
| `tests/test_scraper.py` | Canned tests: success + 6 degradation + merge + exit-0 (min 120) | ✓ VERIFIED | 295 lines, 16 functions = 18 collected (parametrized), all pass offline. No skips/xfails. |
| `tests/fixtures/okx_detail_3345.html` | Real-shape 200 detail HTML (success fixture) | ✓ VERIFIED | 20 lines; appState island with verified 3345 values; CJK round-trips through parse. |
| 3 degradation fixtures (empty_spa, changed_markup, missing_keys) | Trigger each None+WARNING path | ✓ VERIFIED | All exist (15/18/15 lines); exercised by parametrized degradation test. |
| `README.md` | OPS-02 operator + registration guide (min 120, verbatim prompts) | ✓ VERIFIED | 148 lines; 11 sections in locked order; both ASP prompts verbatim; all commands; 5 env vars; seam named. |
| `submission/demo-script.md` | SUBM-01 90s storyboard w/ GlassDesk anomaly (min 40, contains GlassDesk) | ✓ VERIFIED | 67 lines; contains GlassDesk; DB-verified numbers + verbatim reason string. |
| `submission/x-post-draft.md` | SUBM-02 #OKXAI thread (contains #OKXAI) | ✓ VERIFIED | 68 lines; #OKXAI present; neutral/factual. |
| `submission/listing-copy.md` | SUBM-03 fields incl. ≤80 tagline + Software Services @ 0.01 USDT | ✓ VERIFIED | 49 lines; contains "Software Services"; 66-char primary tagline. |
| `tests/test_submission_language.py` | Banned-vocab scan + ≤80 tagline (min 30) | ✓ VERIFIED | 60 lines; 3 real assertions, no skips. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| scraper.py :: scrape_agents | refresh.py :: persist(source='scrape') | merge() then _persist_records | ✓ WIRED | main() calls `scrape_agents(...)` under `--scrape`, then `merge(records, scraped)` -> `_persist_records`. Merged batch persists (source-tagging of scraped provenance is a documented v2 deferral; census-floor invariant holds — verified 0 non-census snapshots). |
| scraper.py :: parse_appstate | data['appContext']['initialProps']['AgentDetailPage']['overview'] | BeautifulSoup find(id='appState') + json.loads | ✓ WIRED | Confirmed in code + proven by successful parse of the real fixture returning all correct field values. |
| README.md env-var table | .env.example (TRUSTLENS_PAY_TO) | documents all 5 vars w/ placeholders | ✓ WIRED | All 5 vars present in README table; placeholder-only. |
| README.md mock→SDK section | server/payments.py :: make_verifier / UnconfiguredVerifier | names okxweb3-app-x402 swap seam | ✓ WIRED | README names okxweb3-app-x402, make_verifier, PaymentVerifier, UnconfiguredVerifier as the swap point. |
| test_submission_language.py | submission/*.md + README.md | reads each, asserts banned regex absent | ✓ WIRED | README asserted in scope; test passes; independent scan 0 hits. |
| listing-copy.md tagline | ≤80-char limit | test asserts len(tagline) ≤ 80 | ✓ WIRED | Primary tagline 66 chars; test enforces the `**Tagline:**` line. |

### Data-Flow Trace (Level 4)

The demo money-shot claims specific real numbers ("every number is real, taken from the built database"). Traced each claim to the actual scoring output in a freshly built DB.

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| demo-script.md Beat 2 | 3345 grade/score/conf | scores table (built via refresh) | grade=A, score=94, conf=high, 5.0 on 539 — MATCH | ✓ FLOWING |
| demo-script.md Beat 3 | GlassDesk 3465 grade/score/conf | scores table | grade=D, score=45, conf=low, 5.0 on 1 — MATCH | ✓ FLOWING |
| demo-script.md Beat 3 | GlassDesk rating_credibility.reason | scores.components JSON | Reason string matches demo VERBATIM (incl. "1 sale(s)", em-dash, "not an assessment of conduct") | ✓ FLOWING |
| demo-script.md backups | Token Radar 2991 / Thumbnail Maker 4511 | scores table | 2991 D/52/low 5.0-on-3; 4511 D/45/low 5.0-on-1 — MATCH | ✓ FLOWING |
| parse_appstate output | AgentRecord(3345) | real fixture appState island | id/sold/rating/price/positive_pct all correct | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full suite green + coverage gate | `python -m pytest -q` | 317 passed, coverage 100% (≥90% gate) | ✓ PASS |
| Scraper canned tests offline | `python -m pytest tests/test_scraper.py --no-cov -q` | 18 passed | ✓ PASS |
| Language gate | `python -m pytest tests/test_submission_language.py --no-cov -q` | 3 passed | ✓ PASS |
| Default refresh exit 0 + 272 | `python -m indexer.refresh --db … --captured-at …` | exit 0; agents=272; census=272; non-census=0 | ✓ PASS |
| --scrape all-403 exit 0 + 272 + WARNING | `main(["--scrape",…])` w/ 403 MockTransport | exit 0; 272; 1 WARNING (status=403) | ✓ PASS |
| --scrape flag present | `python -m indexer.refresh --help` | `--scrape` listed with help text | ✓ PASS |
| parse_appstate success | parse real fixture | 3345/539/5.0/0.01/100.0/derived; CJK round-trips | ✓ PASS |
| No server imports scraper | grep server/ for indexer.scraper | 0 matches | ✓ PASS |
| Docker rehearsal end-to-end | `docker compose up` (clean clone) | Engine DOWN — deferred to human checklist | ? SKIP (human) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| INDX-04 | 05-01 | Polite scraper (≤1 req/s, UA TrustLens/1.0, on-disk cache, graceful CSV fallback) | ✓ SATISFIED | scraper.py implements all politeness rules; every failure degrades to census with WARNING; proven by 18 canned tests + the empirical 403 run. |
| OPS-02 | 05-02 | README: local run, deploy, Inspector, exact ASP prompts + manual steps | ✓ SATISFIED | README.md 11 sections, verbatim prompts, all verified commands, HUMAN-ONLY marks. |
| OPS-03 | 05-01, 05-03 | Full pytest suite passes (scoring, MCP schemas, e2e x402-mocked) + canned scraper tests + language gate, no gate change | ✓ SATISFIED | 317 passed, coverage 100%; scraper + language-gate tests added; gate unchanged at ≥90%. |
| SUBM-01 | 05-03 | demo-script.md 90s storyboard (problem→call→anomaly→A2MCP→leaderboard+revenue) | ✓ SATISFIED | 5-beat storyboard; anomaly beat on DB-verified real data; docker-compose-executable; Docker start HUMAN-ONLY. |
| SUBM-02 | 05-03 | x-post-draft.md launch thread with #OKXAI | ✓ SATISFIED | 6-tweet neutral thread; #OKXAI present. |
| SUBM-03 | 05-03 | listing-copy.md: name, tagline ≤80, description, category Software Services, 0.01 USDT | ✓ SATISFIED | All fields present; 66-char primary tagline; Software Services; 0.01 USDT; URL placeholders. |

No orphaned requirements — REQUIREMENTS.md maps exactly INDX-04, OPS-02, OPS-03, SUBM-01..03 to Phase 5, all claimed by the three plans.

### Anti-Patterns Found

None. Scans for TODO/FIXME/XXX/HACK/PLACEHOLDER/"not implemented"/skip/xfail across scraper.py, test_scraper.py, and test_submission_language.py returned zero matches. The `DEMO_AGENT_IDS = ("3345",)` bounded set is a deliberate, documented v2/INDX-05 deferral (not a stub — the fetch+parse+merge path is fully functional). No banned vocabulary anywhere in the outward surface (README + all 3 submission files = 0 hits).

### Human Verification Required

**1. Demo-script end-to-end rehearsal against a clean-clone `docker compose up`**

- **Test:** Start the Docker Desktop engine, run `docker compose up` on a clean clone, confirm `curl -s http://localhost:8000/healthz` is healthy, then walk the demo's five beats live: `score_agent("这个能吃吗？")` → A/94/high; `score_agent("GlassDesk")` (3465) → D/45/low with the verbatim `rating_credibility.reason`; the leaderboard at `/` shows 272 agents; and the 402→paid 0.01 USDT flow.
- **Expected:** Container self-seeds and serves `/`, `/healthz`, `/mcp` on one port; the beat numbers reproduce (they are already DB-verified) and the recording captures cleanly.
- **Why human:** The Docker Desktop engine will not start in the build environment (`docker info` fails — a carried Phase-3/4 blocker). The phase goal explicitly states "the Docker rehearsal folds into the human checklist (engine down)"; CONTEXT and Plan 03 lock this deferral. Everything the rehearsal needs is proven present and correct: the script's data is DB-verified, `Dockerfile` + `docker-compose.yml` exist and are runnable, and the identical app is proven in-process and against live uvicorn in Phases 3/4. Only the physical engine-up recorded run remains — the single outstanding item.

### Gaps Summary

No blocking gaps. All 16 must-have truths are VERIFIED empirically (commands executed, DB queried, tests run) — not merely accepted from the SUMMARYs. The SUMMARY claims (317 passing, coverage 100%, 272 census rows, verbatim reason string, ≤80 tagline) were each independently reproduced and hold. The service is submission-ready in every respect that can be verified in-environment.

The one remaining item is the human Docker-engine demo rehearsal — the tail clause of ROADMAP Success Criterion #4. This is not a defect or a stub: the demo script IS executable and grounded in real data; the phase was explicitly scoped to PREPARE materials and fold the container rehearsal into the final human checklist because the engine is down in the build environment. Per that design, status is `human_needed` with this single item, rather than a gap requiring a closure plan.

---

_Verified: 2026-07-11T17:40:00Z_
_Verifier: Claude (gsd-verifier)_
