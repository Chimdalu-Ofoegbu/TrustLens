# Phase 5: Scraper, Hardening & Submission Kit - Research

**Researched:** 2026-07-11
**Domain:** Polite HTML/JSON scraping with graceful degradation + hackathon submission materials (README, demo, listing, x-post)
**Confidence:** HIGH (okx.ai scrapeability empirically probed from this machine; all seams read from live code; demo agent verified against the built DB)

## Summary

The single highest-value finding of this research overturns the phase's founding assumption. **okx.ai does NOT 403 the `TrustLens/1.0` User-Agent, and its agent pages are NOT an empty JS SPA shell.** A polite probe from this machine (≤1 req/sec, UA `TrustLens/1.0`, single attempt each) returned **HTTP 200** for `robots.txt`, `/agents`, and `/agents/3345`; `robots.txt` says `Allow: /`; and every page is **server-side rendered** (`isSSR: true`) with a rich embedded JSON blob — `<script type="application/json" id="appState">` — that `BeautifulSoup(html, "html.parser")` + `json.loads` extracts with zero JavaScript execution. The detail-page blob (`appContext.initialProps.AgentDetailPage.overview`) carries `agentId`, `name` (CJK preserved), `score` (rating), `approvalRate` (positive %), `usageCount` (sold), `serviceLowestFee` (price), `categories`, `createdAt`/`updatedAt`, and full `reviews`. Cross-checked against the built census DB, scraped `usageCount` matches census `sold` almost exactly (172=172, 62=62, 539=539) with two agents showing small upward drift (1377 vs 1370, 176 vs 175) — proving both that the scraper genuinely works and that it delivers real freshness value over the 2026-07-10 snapshot.

**This does not change the locked design — it strengthens it.** The CSV stays PRIMARY (the scraper is behind a `--scrape` flag, off by default, so all 296 existing tests and determinism hold), and graceful degradation remains the core deliverable. What changes is the *primary parse target* (embedded `appState` JSON, not brittle DOM selectors) and the *realism of the canned fixtures*: the "success" fixture is now a real 200-with-JSON sample, and the failure fixtures (403, empty-SPA, changed-markup, timeout) simulate degradations that are now *contingencies* rather than the expected default. One structural mismatch matters for the planner: okx.ai's real listed categories are a **6-value code set** (`WORLD_CUP`, `FINANCE`, `SOFTWARE_SERVICES`, `LIFESTYLE`, `ART_CREATION`, `OTHER`) that has **zero overlap** with TrustLens's derived 9-bucket `CANONICAL_CATEGORIES` — so a scraped category can never be stored raw into a reason string, and `category_source='listed'` enrichment must either map through a translation table or (simpler, recommended) be captured for display-only metadata without feeding scoring/reason text.

**Primary recommendation:** Build `indexer/scraper.py` as a sync `httpx.Client` (UA `TrustLens/1.0`, 1 req/s sleep-between, on-disk cache under `data/cache/`, hard per-request timeout, no retries) whose parser extracts the `appState` JSON via `html.parser` + `json.loads`; wrap every code path so it terminates in either `(source="scrape") AgentRecord`s handed to the existing `persist()` seam, or a `log.warning(...)` + CSV fallback — never an unhandled exception. The demo anomaly-flag hero is **GlassDesk (id=3465): D / 45 / low confidence, 5.0 rating on 1 sale**, contrasted against **这个能吃吗？ (id=3345): A / 94 / high**, both 5.0 stars — the perfect "flagged not accused" beat.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Fetch okx.ai HTML | New `indexer/scraper.py` (offline CLI tier) | — | Scraping is an offline enrichment step, NEVER in the FastAPI request path (Pitfall 7). Behind `python -m indexer.refresh --scrape`. |
| Parse agent fields from HTML | `indexer/scraper.py` | `indexer/parse.py` (reuse `parse_price`/`parse_sold` if a value arrives as a display string) | Scraper produces `AgentRecord`s; the JSON blob gives typed-ish values (strings like `"0.01"`, ints like `539`) so most parsing is a `float()`/`int()` cast, not the census's messy display-string parsing. |
| Persist scraped records | `indexer/refresh.py` `persist()` seam (unchanged) | `indexer/db.py` | The seam already exists: `persist(conn, records, captured_at, source="scrape")`. Scraper reuses it verbatim — no new writer. |
| Category validation | `indexer/category.py` `CANONICAL_CATEGORIES` | `scoring/components.py` (already gates on it) | Scraped category codes are validated/mapped before any storage that touches scoring; reasons already refuse non-canonical category text. |
| Graceful fallback control flow | `indexer/scraper.py` + `refresh.py` CLI | — | Every failure mode returns "nothing usable" and the census records stand; refresh's 0/1/2 exit contract is preserved. |
| README / demo / listing / x-post | `README.md` + `submission/*.md` (docs tier) | — | Pure documentation deliverables; no runtime code. Human-only steps clearly marked. |

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Scraper (INDX-04 verbatim + brief politeness rules):**
- New module `indexer/scraper.py`; the CSV remains the PRIMARY seed path (okx.ai 403s bots and is a JS SPA — proven in earlier research). The scraper is the OPTIONAL refresh enrichment, timeboxed ~2h of build effort.
  - *[RESEARCH NOTE — empirical override: okx.ai returned 200, not 403, and is server-side-rendered, not an empty SPA. The CSV-primary + `--scrape`-gated design is still correct and still locked; only the parse target and fixture realism update. See "okx.ai Scrapeability Verdict" below.]*
- Politeness (all locked): ≤1 req/sec rate limit; `User-Agent: TrustLens/1.0`; on-disk response cache (e.g. `data/cache/` keyed by URL hash, gitignored); `httpx` sync client (already a dep); `BeautifulSoup(..., "html.parser")` (stdlib backend, no lxml).
- Targets: okx.ai/agents listing + `https://www.okx.ai/agents/<id>` detail pages.
- Graceful degradation is the core deliverable: EVERY failure path — 403/blocked, empty SPA shell (no parseable data), markup change (selectors miss), network error, timeout — logs a WARNING and falls back to census CSV data without crashing. The refresh exit-code contract (0/1/2) and determinism are preserved.
- Integration: the scraper feeds the SAME loader path as the census (source-tagged 'scrape' vs 'census' per the Phase 1 seam); when the scraper yields nothing usable, the census rows stand. A CLI flag gates it (e.g. `python -m indexer.refresh --scrape`); default refresh stays offline/CSV-only so all existing tests and determinism hold.
- Category enrichment: if a detail page yields a real listed category, store it with `category_source='listed'` (the Phase 1 seam) — BUT reasons/leaderboard already treat category as derived; scraped categories are validated against the canonical 9-bucket set (Phase 2 WR-02 fix) before use so scraped text can't break neutral language.
- Tests: canned-response fixtures ONLY (no live network in tests) — feed the parser saved HTML samples + simulate each failure mode (403 response, empty-shell HTML, changed markup, timeout) and assert graceful CSV fallback + warning. Never hit okx.ai in the test suite.

**README (OPS-02 verbatim):**
- `README.md` covering, in order: what TrustLens is (neutral framing) + the 4 tools; local run (`pip install -e .[dev]`, `python -m indexer.refresh`, `uvicorn server.main:app --port 8000`); the leaderboard at `/`, `/healthz`, `/mcp`; running tests + the coverage gate; Docker (`docker compose up` — one port; note the entrypoint self-seeds); MCP Inspector test instructions (the exact verified `npx --yes @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/list` command + a tools/call example incl. the CJK-name quirk); the x402 pre-registration curl check verbatim (`curl -i -X POST https://<host>/mcp` → expect 402 + PAYMENT-REQUIRED); env-var config table (all 5 vars, pointing at .env.example); the mock→real-SDK swap (X402_MOCK vs dropping in okxweb3-app-x402 at the PaymentVerifier seam); deploy steps (any HTTPS-capable host; OKX suggests HK/Singapore nodes; needs a public HTTPS domain); and the EXACT OKX ASP registration steps.
- ASP registration section MUST quote verbatim (from OKX docs, in PROJECT.md): install Onchain OS (`npx skills add okx/onchainos-skills --yes -g`), log into the Agentic Wallet, then the two agent prompts — **"Help me register an A2MCP ASP on OKX.AI using Onchain OS"** (fields: service name, description, price per call, endpoint URL) and **"Help me list my ASP on OKX.AI using Onchain OS"** — review completes ≤24h to the registered wallet email. Clearly mark which steps are HUMAN-ONLY (deploy, wallet login, submission) per the stop conditions.
- Neutral analytics language throughout; link the methodology page.

**OPS-03 (locked):**
- Confirm/round out the pytest suite: scoring functions (done), MCP tool schemas (done), one e2e call against a local server with x402 mocked (done in Phase 4). This phase ensures the suite is green as a whole and adds the scraper's canned-response tests. No coverage-gate change.

**Submission kit (SUBM-01..03 verbatim):**
- `submission/demo-script.md` — 90-second storyboard: problem → live MCP call from Claude (score_agent on a real agent) → score card with an anomaly flag (e.g. a 5.0-rating-thin-sales agent shown flagged-not-accused) → agent-calling-agent flow → leaderboard + on-chain revenue (0.01 USDT/call settling). Must be executable against a clean-clone `docker compose up`; note the Docker-engine human step.
- `submission/x-post-draft.md` — launch thread with #OKXAI; neutral, factual, no accusations; highlights the one-call hiring-trust verdict + determinism + on-chain pay-per-call.
- `submission/listing-copy.md` — ASP listing fields: name (TrustLens), tagline ≤80 chars (enforce the limit), description, category "Software Services", price 0.01 USDT. Plus the endpoint URL placeholder and the methodology URL.
- All copy uses neutral analytics language; the banned-vocabulary test's spirit applies (no fraud/scam/fake/manipulat anywhere in submission text) — consider extending the test to scan submission/ md files too.

**Stop conditions (reaffirm):** This phase PREPARES materials; it does NOT deploy, register, post, or fill the hackathon form. The final orchestrator output is the ordered human checklist. The Docker container smoke test (Phase 3 HUMAN-UAT) folds into that checklist.

**Git & conduct:** Commits authored by the user's git identity only; NEVER any AI attribution; conventional commits `feat(05-XX): ...`. No new runtime deps; 2-attempt stop rule; scraper build timeboxed.

### Claude's Discretion
- Scraper module structure, cache key scheme, exact selectors (best-effort; fallback is what's tested)
- README section ordering/formatting within the required content
- Demo-script beat timing; x-post thread length; listing description wording (within neutral-language + char limits)

### Deferred Ideas (OUT OF SCOPE)
- Live scraping in CI/tests — never (canned responses only)
- INDX-05 recurring snapshot scheduling — v2
- Actual deploy / registration / posting / Google Form — human steps in the final checklist
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INDX-04 | Polite scraper for okx.ai listing + detail pages: ≤1 req/sec, UA `TrustLens/1.0`, on-disk cache, graceful degradation to census CSV when blocked or markup changes | Empirically probed: 200 OK, SSR, `appState` JSON target confirmed; `persist(source="scrape")` seam exists; `data/cache/` already gitignored; exact graceful-degradation control flow + 4 canned fixtures specified below. |
| OPS-02 | README: local run, deploy steps, MCP Inspector instructions, exact OKX ASP registration prompts | Section-by-section outline below with VERIFIED Inspector commands (from 03-05-PLAN), VERIFIED curl check (from 04-VERIFICATION), verbatim ASP prompts (from PROJECT.md), and the mock→SDK swap at the `make_verifier` seam. |
| OPS-03 | Full pytest suite passes: scoring, MCP schemas, one e2e with x402 mocked | Baseline confirmed green: **296 passed, scoring coverage 100%** (`python -m pytest -q`). Scraper adds canned-response tests only; no coverage-gate change. |
| SUBM-01 | `submission/demo-script.md` — 90s storyboard with anomaly flag | Hero agent identified & verified: **GlassDesk (id=3465) D/45/low, 5.0 rating on 1 sale**; contrast **3345 A/94**. Exact reason strings captured. Executable against `docker compose up`. |
| SUBM-02 | `submission/x-post-draft.md` — launch thread with #OKXAI | Differentiation angle vs Factor/TO1/Internet Court gathered from FEATURES.md; neutral-language + banned-word constraints documented. |
| SUBM-03 | `submission/listing-copy.md` — name, tagline ≤80 chars, description, category Software Services, price 0.01 USDT | 5 valid taglines ≤80 chars drafted & char-counted (66–79); note okx.ai's real category value is `SOFTWARE_SERVICES` (display "Software services"). |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

CLAUDE.md is the GSD-composed project brief (PROJECT.md + STACK.md). Actionable directives the planner MUST honor:

- **No new runtime dependencies.** Scraper uses only `httpx` (0.28.1, already pinned) + `beautifulsoup4` (4.15.0) + stdlib. NO `lxml`, `html5lib`, `requests`, `requests-cache`, `hishel`, `aiosqlite`. Parse with `BeautifulSoup(html, "html.parser")`.
- **Scraping politeness is a hard contract:** ≤1 req/sec, UA `TrustLens/1.0`, on-disk cache, graceful degradation to census CSV.
- **Neutral language everywhere outward-facing:** never "fraud/scam/fake/manipulat" — applies to README, demo, listing, x-post. The banned-word test's spirit extends to `submission/`.
- **Secrets via env only:** README documents 5 vars via `.env.example`; never hardcode keys/addresses.
- **Workspace:** work only inside `trustlens/`; the parent-folder census original, research report, and prompt file are read-only.
- **Git:** commits authored solely by the user's identity; NO AI attribution of any kind (Co-Authored-By, "Generated with", etc.) in any commit or PR. Conventional commits `feat(05-XX): ...`.
- **Stop conditions (human-only, mark in README + final checklist):** remote deploy / domain purchase; real wallet / funds / keys / OKX Agentic Wallet login; submitting the ASP listing, posting publicly, the hackathon Google Form; adding unlisted dependencies; deleting any file; any error unresolved after 2 attempts.
- **GSD workflow:** file edits go through a GSD command; this phase prepares materials, it does not deploy/register/post.

## okx.ai Scrapeability Verdict (EMPIRICAL — probed 2026-07-11 from this machine)

> Probe conduct: two probe sessions, `httpx.Client` with `headers={"User-Agent":"TrustLens/1.0"}`, `timeout=15`, `follow_redirects=True`, 1.5s sleep between requests (>1 req/sec), single attempt each, read-only. Raw bodies saved to scratchpad. This is the source of truth for parser + fixture design.

### Verdict: SCRAPEABLE. Server-rendered, embedded JSON, no 403, no bot wall for our UA.

| Probe | Result | Detail |
|-------|--------|--------|
| `GET /robots.txt` | **200** | Body: `User-agent: *` / `Allow: /` / `Sitemap: https://www.okx.ai/default-index.xml`. Nothing disallowed. `server: cloudflare`. `[VERIFIED: live probe]` |
| `GET /agents` (listing) | **200**, 101,709 bytes, `text/html` | SSR. Embedded `appState` JSON carries `agentList` with `total: 305`, `pageNo:1, pageSize:20, list:[20 agents]` + a 6-code category filter set. `server: cloudflare`, `cf-cache-status: DYNAMIC`. `[VERIFIED: live probe]` |
| `GET /agents/3345` (detail) | **200**, 49,929 bytes, `text/html` | SSR. `<h1>` = `这个能吃吗？` (real agent name, CJK preserved). Embedded `appState` JSON carries full `overview`, `services`, `reviews`, `similar`. `[VERIFIED: live probe]` |

**No `__NEXT_DATA__` and no `self.__next_f` chunks** (App-Router streaming markers absent) — but the data is NOT hidden behind client JS. It lives in `<script data-id="__app_data_for_ssr__" type="application/json" id="appState">` with `isSSR: true, useSSR: true, isSSRSuccess: true`. `BeautifulSoup(html, "html.parser").find("script", id="appState")` → `json.loads(tag.string)` returns the whole tree with zero JS execution. **Verified working on the saved sample.** `[VERIFIED: live probe + parser dry-run]`

### The scrape target — detail page JSON shape

`data["appContext"]["initialProps"]["AgentDetailPage"]["overview"]` (verified keys, agent 3345):

| JSON key | Value (3345) | Maps to `AgentRecord` field | Notes |
|----------|--------------|------------------------------|-------|
| `agentId` | `"3345"` | `id` | string |
| `name` | `"这个能吃吗？"` | `name` (+ `name_key` via `parse.name_key`) | CJK preserved exactly |
| `score` | `"5.0"` | `rating` | string → `float`; `"0.0"`/absent = unrated |
| `approvalRate` | `"100%"` | `positive_pct` | strip `%` → `float` |
| `usageCount` | `539` | `sold` | already `int` |
| `serviceLowestFee` | `"0.01"` | `price_usdt` | string → `float`; NOT subscript-encoded here (clean decimal) |
| `categories` | `["LIFESTYLE"]` | `category` (validate/map) | **code set, not display; see mismatch below** |
| `createdAt` / `updatedAt` | `1783041174238` / `1783782565739` | (v2 seam: listing age) | epoch ms; real age signal, but listing-age component is a documented v2 seam — capture for metadata only |
| `reviews.totalScore` / `reviews.totalCount` | `"5.0"` / `1` | (enrichment) | real review count — census lacks this; do NOT wire into scoring this version |

Listing page: `data["appContext"]["initialProps"]["AgentMarketplaceAgentList"]["agentList"]` = `{total:305, pageNo, pageSize:20, list:[...]}`; each entry has `agentId, name, score, approvalRate, usageCount, startingPrice, symbol, categories, categoryName`. Pagination is `pageNo`/`pageSize` (implies a JSON API; **do not** build a 16-page crawl loop — Pitfall: full 305-agent rescrape at 1 req/s ≈ 5+ min; if enrichment is wanted, scrape a bounded set or the detail pages for agents already in the census).

### Census fidelity cross-check (proves the scraper works AND adds value)

Scraped `usageCount` vs census `sold`, same run: `[VERIFIED: live probe vs built DB]`

| id | scraped usageCount | census sold | scraped score | census rating | Δ |
|----|-------------------|-------------|---------------|---------------|---|
| 1891 | 172 | 172 | 4.7 | 4.7 | exact |
| 62 (id 1445) | 62 | 62 | 4.8 | 4.8 | exact |
| 3345 | 539 | 539 | 5.0 | 5.0 | exact |
| 2013 | **1377** | 1370 | — | — | **+7 (drift since 2026-07-10 snapshot)** |
| 1500 | **176** | 175 | 4.6 | 4.6 | **+1 (drift)** |

The near-perfect match confirms the census is a faithful snapshot of this exact `appState` source; the small upward drift on active agents is exactly the freshness the scraper is meant to capture.

### The category mismatch (planner MUST account for this)

okx.ai listed categories are a **6-code set** — verified filter list:
`ALL`, `WORLD_CUP` ("World Cup🔥"), `FINANCE`, `SOFTWARE_SERVICES` ("Software services"), `LIFESTYLE`, `ART_CREATION` ("Art creation"), `OTHER` ("Others").

TrustLens's derived `CANONICAL_CATEGORIES` (from `indexer/category.py`) is a **9-bucket set**: Security & Trust, Sports & Prediction, Lifestyle & Health, Creative & Media, Social & News, Developer Tools & Infra, Trading & DeFi, Market Data & Analytics, Other Services.

**Zero string overlap.** A scraped category like `"LIFESTYLE"` is neither a canonical bucket nor safe to render into a reason string (`scoring/components.py` refuses any value outside `CANONICAL_CATEGORIES`). Two safe options for the planner (recommend Option B for the timebox):
- **Option A (mapping):** add a code→bucket table (`LIFESTYLE`→`Lifestyle & Health`, `SOFTWARE_SERVICES`→`Developer Tools & Infra`, `ART_CREATION`→`Creative & Media`, `FINANCE`→`Trading & DeFi`, `WORLD_CUP`→`Sports & Prediction`, `OTHER`→`Other Services`), store the mapped bucket with `category_source='listed'`. Note the mapping is lossy/approximate and does NOT match the keyword-derived distribution the Phase 2 percentiles depend on — so mixing sources would shift percentiles. Only safe if scrape and census never coexist for the same agent's category.
- **Option B (display-only, recommended):** the scraper enriches `sold`/`rating`/`price`/`positive_pct` (the fields that actually feed scoring and match census semantics) and does NOT overwrite `category` — leave `category_source='derived'`. This sidesteps the percentile-drift risk entirely, honors "scraped text can't break neutral language," and still delivers the freshness value. The `category_source='listed'` seam stays available but unused this version (a documented v2 seam, consistent with how listing-age already works).

## Standard Stack

Everything the scraper needs is already a pinned dependency. **No installs.** `[VERIFIED: pyproject.toml + import check]`

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | 0.28.1 | Sync `httpx.Client` for the offline scraper | Already pinned; FastMCP pins the same floor. Sync (not async) — the scraper is a CLI step, not request-path. `[VERIFIED: import httpx → 0.28.1]` |
| beautifulsoup4 | 4.15.0 | Extract `appState` JSON via `find("script", id="appState")` | Already pinned. Use `"html.parser"` backend (stdlib) — NOT lxml. `[VERIFIED: import bs4 → 4.15.0]` |
| stdlib `json` | 3.11+ | Parse the `appState` blob | The parse target is JSON, so `json.loads` does the heavy lifting; DOM selectors are the *fallback*, not the primary. |
| stdlib `hashlib` | 3.11+ | Cache key = `sha256(url).hexdigest()` | On-disk cache under `data/cache/` (already gitignored). |
| stdlib `time` | 3.11+ | `time.sleep(1.1)` between requests | Rate limit ≤1 req/sec = sleep BETWEEN requests, not a token bucket. |
| stdlib `logging` | 3.11+ | `log.warning(...)` on every degradation | Matches `indexer.census`/`refresh` logging convention (row-num/id only, `%r` for CJK-safe logging). |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.1.1 | Canned-fixture tests | Feed saved HTML + simulated failures; assert graceful fallback. `--no-cov` for subset runs (scoring-only gate footgun). |
| `httpx.MockTransport` OR fixture files | 0.28.1 | Offline scraper tests | Two viable patterns — see "Test Fixtures" below. Never hit okx.ai in tests. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `appState` JSON parse | DOM selectors (`index_statLabel__*` etc.) | The CSS class names are hashed/build-generated (`index_segment__iQCWo`) — they WILL change on any okx.ai redeploy. JSON keys (`usageCount`, `score`) are far more stable. Use JSON primary, DOM as a documented fallback. |
| Detail-page-per-census-agent | Listing-page pagination crawl | Listing gives 20/page × ~16 pages = 305 agents at 1 req/s ≈ 5 min + is only a summary. Detail pages are richer but 272 of them at 1 req/s ≈ 4.5 min. For the timebox, scrape a SMALL bounded sample (e.g. first N, or a fixed demo set) to prove the path; full enrichment is a v2 concern (INDX-05). |
| Live-network smoke test | Canned fixtures only | Locked: NEVER hit okx.ai in the suite. The real 200 sample saved during this research becomes the "success" fixture. |

**Installation:** None — all deps already in `pyproject.toml`.

**Version verification:** `[VERIFIED: 2026-07-11]` `python -c "import httpx; print(httpx.__version__)"` → `0.28.1`; `import bs4` → `4.15.0`; Python runtime `3.14.2` (satisfies `>=3.11`).

## Architecture Patterns

### System Architecture Diagram

```
  python -m indexer.refresh [--scrape]
             │
             ├─ (always) load_census(csv) ──► [AgentRecord ...] (source="census")
             │                                        │
   --scrape? │                                        │
     no ─────┼────────────────────────────────────────┤
     yes     │                                         │
             ▼                                         │
   indexer/scraper.py :: scrape_agents()               │
             │                                         │
   ┌─────────┴───────────────────────────────┐         │
   │ for each target URL (≤1 req/s, cached):  │         │
   │   fetch() ──► httpx.Client GET, UA,      │         │
   │               timeout, disk cache        │         │
   │      │                                    │        │
   │      ├─ 403 / 5xx ──────► WARN ─┐          │        │
   │      ├─ timeout/neterr ─► WARN ─┤          │        │
   │      ├─ 200 body:               │          │        │
   │      │    parse_appstate()      │          │        │
   │      │      ├─ no appState ────► WARN ─┤    │        │
   │      │      ├─ json error ─────► WARN ─┤    │        │
   │      │      ├─ missing keys ───► WARN ─┤    │        │
   │      │      └─ OK ─► AgentRecord(source="scrape")   │
   │      └─────────────────────────► [ ] (empty on any WARN)
   └───────────────────────────────────────────┘        │
             │                                           │
             ▼                                           ▼
     [scraped records] ── merge (scrape wins per-id, else census stands) ──►
                                                         │
                                                         ▼
                            persist(conn, records, captured_at, source)  ← UNCHANGED SEAM
                                                         │
                              compute_all() + web_build()  (unchanged)
                                                         │
                                          exit 0 / 1 (csv) / 2 (db)  ← UNCHANGED CONTRACT
```

The scraper is a pure *source* that produces `AgentRecord`s or nothing; it NEVER touches the DB, scoring, or exit codes directly. If it yields nothing, the census records flow through exactly as today.

### Recommended Project Structure
```
indexer/
├── scraper.py       # NEW: fetch (httpx+cache+rate-limit) + parse_appstate + scrape_agents
├── refresh.py       # +1 flag (--scrape), +merge step; persist() seam untouched
├── census.py        # unchanged
├── parse.py         # reuse name_key; optionally parse_price/parse_sold if a display string appears
├── category.py      # +optional CODE→bucket map if Option A chosen
└── ...
tests/
├── test_scraper.py  # NEW: canned fixtures (success/403/empty-spa/changed-markup/timeout)
└── fixtures/        # NEW: saved okx.ai HTML samples (the real 200 + synthetic failures)
submission/
├── demo-script.md   # NEW (SUBM-01)
├── x-post-draft.md  # NEW (SUBM-02)
└── listing-copy.md  # NEW (SUBM-03)
README.md            # NEW (OPS-02)
```

### Pattern 1: Polite fetch with disk cache + rate limit
**What:** One `httpx.Client` reused across the run; cache-first; sleep between network hits; hard timeout; single attempt.
**When to use:** Every okx.ai GET.
**Example:**
```python
# indexer/scraper.py  (design sketch — verified shape against saved sample)
import hashlib, json, logging, time
from pathlib import Path
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("indexer.scraper")
UA = "TrustLens/1.0"
CACHE_DIR = Path("data/cache")
RATE_S = 1.1          # > 1 req/sec
TIMEOUT_S = 15.0

def _cache_path(url: str) -> Path:
    return CACHE_DIR / (hashlib.sha256(url.encode()).hexdigest() + ".html")

def fetch(client: httpx.Client, url: str, *, _last: list) -> str | None:
    p = _cache_path(url)
    if p.is_file():
        return p.read_text(encoding="utf-8")           # cache hit: no network, no sleep
    if _last:                                           # politeness: sleep BETWEEN network calls
        time.sleep(RATE_S)
    _last.append(url)
    try:
        r = client.get(url, timeout=TIMEOUT_S)          # single attempt, no retries
    except httpx.HTTPError as exc:
        log.warning("fetch failed url=%r: %s", url, exc.__class__.__name__)
        return None
    if r.status_code != 200:
        log.warning("fetch non-200 url=%r status=%d", url, r.status_code)
        return None                                     # 403/5xx → CSV fallback
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(r.text, encoding="utf-8")
    return r.text
```

### Pattern 2: JSON-first parse with best-effort degradation
**What:** Extract `appState` JSON; every missing/malformed step returns `None` + a warning, never raises.
**Example:**
```python
# Source: verified against the real saved okx.ai detail page (2026-07-11)
def parse_appstate(html: str, url: str) -> "AgentRecord | None":
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", attrs={"id": "appState", "type": "application/json"})
    if tag is None or not tag.string:
        log.warning("no appState script url=%r (SPA/markup change)", url)
        return None
    try:
        data = json.loads(tag.string)
        ov = data["appContext"]["initialProps"]["AgentDetailPage"]["overview"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        log.warning("appState parse miss url=%r: %s", url, exc.__class__.__name__)
        return None
    try:
        return AgentRecord(
            id=str(ov["agentId"]),
            name=ov["name"],
            name_key=name_key(ov["name"]),
            category=derive_category(ov["name"], ov.get("description", "")),  # Option B: keep derived
            tagline=ov.get("description", ""),
            price_usdt=float(ov["serviceLowestFee"]) if ov.get("serviceLowestFee") else None,
            price_raw=str(ov.get("serviceLowestFee", "")),
            sold=int(ov.get("usageCount", 0)),
            rating=float(ov["score"]) if ov.get("score") and float(ov["score"]) > 0 else None,
            positive_pct=float(ov["approvalRate"].rstrip("%")) if ov.get("approvalRate") else None,
        )
    except (ValueError, KeyError, TypeError) as exc:
        log.warning("appState field cast miss url=%r: %s", url, exc.__class__.__name__)
        return None
```
*(Note: this keeps `category` derived from listing text like the census does — Option B. If Option A is chosen, map `ov["categories"][0]` through a code table and set `category_source="listed"`.)*

### Pattern 3: Merge honoring "census stands when scrape yields nothing"
```python
def merge(census: list[AgentRecord], scraped: list[AgentRecord]) -> list[AgentRecord]:
    by_id = {r.id: r for r in census}       # census is the floor
    for s in scraped:
        by_id[s.id] = s                       # scrape wins ONLY for ids it successfully parsed
    return list(by_id.values())
```

### Anti-Patterns to Avoid
- **DOM-selector-primary parsing:** okx.ai class names are build-hashed (`index_segment__iQCWo`) — they break on every redeploy. JSON keys are stable. Selectors are the documented *fallback* only.
- **Retry loops / header spoofing on 403:** Locked "one attempt, log, fall back." (Moot now — no 403 observed — but keep the discipline for when okx.ai adds a bot wall.)
- **Full 305/272-page crawl inside refresh:** ~5 min at 1 req/s; blocks the pipeline. Bound the sample or defer full enrichment to v2 (INDX-05).
- **Scraper import anywhere under `server/`:** Pitfall 7 — scraping is offline-only, never request-path. Assert no `server/*` module imports `indexer.scraper`.
- **Overwriting `category` with a raw scraped code:** breaks the canonical-vocabulary contract and shifts Phase 2 percentiles. Use Option B (leave derived) unless a full mapping + isolation is built.
- **Letting a scrape failure change the exit code:** the scraper returns `[]` on any failure; refresh's 0/1/2 contract is driven by census + DB stages only.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP client with timeouts/redirects | Custom `urllib` wrapper | `httpx.Client` (already pinned) | Redirect handling, timeout semantics, connection reuse are all solved; hand-rolling is Pitfall bait. |
| HTML→data extraction | Regex over raw HTML for fields | `BeautifulSoup("html.parser").find(id="appState")` + `json.loads` | The data is a clean JSON island; regex-scraping HTML is the classic fragility trap. The JSON is authoritative. |
| Response caching | `requests-cache` / `hishel` | `hashlib.sha256(url)` → file under `data/cache/` | Both are UNLISTED deps (constraint violation). A 6-line disk cache covers the need at this scale. |
| Rate limiting | Token-bucket library | `time.sleep(1.1)` between network fetches | ≤1 req/s over a handful of URLs needs one `sleep`, not a scheduler. |
| Field parsing of prices/sold | New parsers in the scraper | Reuse `indexer/parse.py` if a value arrives as a display string | The `appState` values are mostly clean (`"0.01"`, `539`) so casts suffice; but `parse_price`/`parse_sold` already handle every messy case if okx.ai ever returns display strings. |
| AgentRecord persistence | New writer for scraped rows | `refresh.persist(conn, records, ..., source="scrape")` | The seam was purpose-built in Phase 1 (`indexer/refresh.py:64`, `models.py:25`, `db.py` snapshot `source`). Reuse it verbatim. |

**Key insight:** okx.ai already did the hard part — it ships a fully-populated `appState` JSON in the SSR HTML. The scraper's real job is not "extraction" (that's `json.loads`) but **graceful degradation discipline**: every one of the five failure modes must land softly on the census. That control flow — not clever parsing — is the deliverable.

## Common Pitfalls

### Pitfall 1: Scraper failure changes refresh's exit code
**What goes wrong:** A scrape exception propagates and refresh exits 2 (or crashes), breaking the offline determinism the whole test suite depends on.
**Why it happens:** Treating the scraper as part of the DB/persist stage instead of an isolated source.
**How to avoid:** `scrape_agents()` catches everything internally and returns `list[AgentRecord]` (possibly empty). The merge is pure. Exit codes stay driven by census-read (1) and DB (2) stages only. Add a test: `--scrape` with a MockTransport that 403s every request → refresh still exits 0 with 272 census rows.
**Warning signs:** any `raise` reachable from `scrape_agents`; refresh exit code varying with network state.

### Pitfall 2: CSS-class selectors as the primary parser
**What goes wrong:** Parser works today, silently returns all-None after okx.ai's next frontend deploy (hashed class names change).
**Why it happens:** DOM looks easier than digging out the JSON.
**How to avoid:** Parse `appState` JSON first (stable keys). If you also want DOM fallback, treat "all fields None" as a parse miss → warning → CSV fallback (never store a hollow record).
**Warning signs:** selectors like `index_statLabel__roJkD` in the parser as the only path; scraped rows with every enrichment field None.

### Pitfall 3: Coverage-gate footgun on scraper subset runs
**What goes wrong:** `pytest tests/test_scraper.py` alone measures scoring coverage as 0% and fails the `--cov-fail-under=90` gate.
**Why it happens:** `addopts` in `pyproject.toml` always applies `--cov=scoring`.
**How to avoid:** Run scraper tests with `python -m pytest tests/test_scraper.py --no-cov` for iteration; the full-suite run keeps the gate. Document this in the README test section (it already bites the census/server tests). `[VERIFIED: pyproject.toml addopts]`
**Warning signs:** "Required test coverage of 90% reached" failing on a scraper-only run.

### Pitfall 4: Demo anomaly agent that reads as an accusation (or is a competitor)
**What goes wrong:** Picking `Factor Credit Desk` (id 4502, also flagged D) as the demo subject looks like an attack on a named competitor; picking a CJK-named agent makes the demo hard to narrate.
**Why it happens:** Grabbing the first flagged row without checking identity.
**How to avoid:** Use **GlassDesk (3345 contrast, 3465 hero)** — neutral English names, not competitors, textbook reason strings. The demo narration says "flagged for thin data, not an assessment of conduct" (the actual reason string).
**Warning signs:** demo subject name appears in the Factor/TO1/Internet Court differentiation list.

### Pitfall 5: Console cp1252 crash when handling CJK during scraper dev/tests
**What goes wrong:** Any `print()` of a scraped CJK name (`这个能吃吗？`) crashes on a Windows cp1252 console with `UnicodeEncodeError` — this literally happened twice during this research probe.
**Why it happens:** Windows default console encoding is cp1252; CJK isn't representable.
**How to avoid:** The refresh entrypoint already does `sys.stdout.reconfigure(encoding="utf-8")` (`refresh.py:143`) and logs ids/names with `%r`. The scraper must follow the same convention: log with `%r`, never bare-`print` scraped text; write any debug dumps to a UTF-8 file. Tests that assert on CJK read/write with `encoding="utf-8"`.
**Warning signs:** `charmap codec can't encode` in scraper test output.

## Code Examples

### Extract the appState JSON (verified on the real saved page)
```python
# Source: live okx.ai /agents/3345 (probed 2026-07-11), parser dry-run confirmed
from bs4 import BeautifulSoup
import json

soup = BeautifulSoup(html, "html.parser")
tag = soup.find("script", attrs={"id": "appState", "type": "application/json"})
data = json.loads(tag.string)
ov = data["appContext"]["initialProps"]["AgentDetailPage"]["overview"]
# ov == {"agentId":"3345","name":"这个能吃吗？","score":"5.0","approvalRate":"100%",
#        "usageCount":539,"serviceLowestFee":"0.01","categories":["LIFESTYLE"], ...}
```

### The persist seam the scraper reuses (already in the codebase)
```python
# indexer/refresh.py:64 — DO NOT re-implement; call with source="scrape"
def persist(conn, records, captured_at, source="census"):
    for rec in records:
        upsert_agent(conn, rec, captured_at)
        insert_snapshot(conn, rec, captured_at, source)  # snapshots.source records provenance
```

### Reason string the demo surfaces (verified via score_agent)
```text
# GlassDesk (id 3465), rating_credibility.reason, VERIFIED from built DB:
"perfect 5.0 rating backed by only 1 sale(s) — pattern consistent with limited
 review history; low confidence, flagged for thin data (not an assessment of conduct)"
```

## Test Fixtures (canned-response, offline — INDX-04 + OPS-03)

Two viable offline patterns; recommend **saved-file fixtures** for the parser + **`httpx.MockTransport`** for the fetch/degradation control flow.

| Fixture | How to build | Asserts |
|---------|-------------|---------|
| **success** | Save the real 200 detail HTML captured in this research (scratchpad `okx_detail_3345.html`) into `tests/fixtures/`. | `parse_appstate` returns an `AgentRecord` with id 3345, sold 539, rating 5.0, price 0.01. |
| **403 blocked** | `httpx.MockTransport(lambda req: httpx.Response(403))`. | `fetch` returns None + one WARNING; `scrape_agents` returns `[]`; refresh exits 0 with census rows. |
| **empty SPA shell** | HTML with `<div id="__next"></div>` and NO `appState` script. | `parse_appstate` returns None + WARNING (no appState). |
| **changed markup** | Real HTML but rename the script id to `appStateXYZ` (or truncate the JSON). | `parse_appstate` returns None + WARNING (no appState / JSON error). |
| **timeout** | `MockTransport` raising `httpx.ConnectTimeout`. | `fetch` catches `httpx.HTTPError` → None + WARNING; no crash. |
| **missing keys** | Valid JSON but `appContext.initialProps` lacks `AgentDetailPage`. | `parse_appstate` returns None + WARNING (KeyError caught). |

All six run with `python -m pytest tests/test_scraper.py --no-cov`. **Never** construct a real `httpx.Client()` against okx.ai in a test.

## README Outline (OPS-02) — section-by-section with VERIFIED commands

Order per the locked CONTEXT. Every command below is either verified in an earlier phase or verified in this research.

1. **What TrustLens is + the 4 tools** — neutral framing (pull one-liner from PROJECT.md Core Value). Tools: `score_agent`, `compare_agents`, `category_leaderboard`, `marketplace_stats`. Link the methodology page (`/#methodology`).
2. **Local run:**
   - `pip install -e .[dev]`  `[VERIFIED: pyproject has [project.optional-dependencies] dev]`
   - `python -m indexer.refresh`  `[VERIFIED: ran it — "272 agents, 272 snapshots, source=census"]`
   - `uvicorn server.main:app --host 0.0.0.0 --port 8000`  `[VERIFIED: server/main.py exposes app = create_app()]`
   - Endpoints: leaderboard `/`, health `/healthz`, MCP `/mcp`.
3. **Tests + coverage gate:**
   - `python -m pytest`  `[VERIFIED: 296 passed, scoring coverage 100%, gate ≥90%]`
   - Footgun note: subset runs need `--no-cov` (the `--cov=scoring` gate reports 0% otherwise).
4. **Docker:**
   - `docker compose up`  `[CITED: docker-compose.yml — build ., port 8000:8000, env_file .env optional]`
   - Note: the entrypoint self-seeds the DB + leaderboard from the bundled census on first start (`[ -f data/trustlens.db ] || python -m indexer.refresh`) — reproducible, offline, seconds. `[VERIFIED: Dockerfile CMD]`
   - **HUMAN-ONLY:** requires Docker Desktop engine running (a carried Phase-3/4 environment blocker — the engine would not start in the build env; `docker info` fails). This folds into the final checklist.
5. **MCP Inspector:** `[VERIFIED verbatim from 03-05-PLAN.md]`
   - List: `npx --yes @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/list` → exactly 4 tools, all with `outputSchema`.
   - Call (CJK quirk): `npx --yes @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/call --tool-name score_agent --tool-arg 'agent_id_or_name=这个能吃吗？'` → 3345 / A / 94. Also `agent_id_or_name="3345"` and the ASCII-`?` variant `这个能吃吗?` resolve to the same card (NFKC name_key).
   - Compare/leaderboard/stats examples: `--tool-name compare_agents --tool-arg 'ids=["3345","2662"]'`; `--tool-name category_leaderboard --tool-arg 'category=Trading & DeFi' --tool-arg 'limit=5'`; `--tool-name marketplace_stats`.
6. **x402 pre-registration curl check:** `[VERIFIED verbatim from 04-VERIFICATION.md]`
   - `curl -i -X POST https://<host>/mcp` → `HTTP/1.1 402 Payment Required` with an uppercase `PAYMENT-REQUIRED` header that base64-decodes to the requirements JSON (scheme `exact`, network `eip155:196`, amount `"10000"`). `POST /mcp/` returns byte-identical 402.
   - Note: `/healthz`, `/`, `/badge/*`, and the MCP handshake (`initialize`, `tools/list`) are NOT gated.
7. **Env-var config table:** all 5 vars, pointing at `.env.example`. `[VERIFIED: .env.example]`
   | Var | Purpose | Placeholder |
   |-----|---------|-------------|
   | `TRUSTLENS_PAY_TO` | wallet receiving 0.01 USDT/call | `0x0000...0000` |
   | `TRUSTLENS_PRICE_USDT` | price in human USDT (→ atomic `"10000"`) | `0.01` |
   | `X_LAYER_RPC` | X Layer RPC (SDK swap only) | `https://rpc.xlayer.tech` |
   | `X402_MOCK` | EXACTLY `1` = mock; anything else = fail-closed 402 | (empty) |
   | `TRUSTLENS_BASE_URL` | public base advertised in requirements + methodology | `http://localhost:8000` |
8. **Mock→real-SDK swap:** `X402_MOCK=1` uses `MockVerifier`; deploy-time, drop in `okxweb3-app-x402` at the `make_verifier`/`PaymentVerifier` seam (`server/payments.py`; `UnconfiguredVerifier` is the exact swap point). Real creds (`OKX_API_KEY`/`OKX_SECRET_KEY`/`OKX_PASSPHRASE`) = **HUMAN-ONLY stop condition**. `[CITED: 04-VERIFICATION.md, PROJECT.md]`
9. **Deploy steps:** any HTTPS-capable host; OKX suggests HK/Singapore nodes; needs a public HTTPS domain. **HUMAN-ONLY.** `[CITED: PROJECT.md]`
10. **OKX ASP registration — quote VERBATIM (mark HUMAN-ONLY):** `[CITED: PROJECT.md, verbatim]`
    - Install Onchain OS: `npx skills add okx/onchainos-skills --yes -g`
    - Log into the Agentic Wallet.
    - Agent prompt 1: **"Help me register an A2MCP ASP on OKX.AI using Onchain OS"** (fields: service name, description, price per call, endpoint URL).
    - Agent prompt 2: **"Help me list my ASP on OKX.AI using Onchain OS"**.
    - Review completes ≤24h to the registered wallet email.
    - **HUMAN-ONLY:** wallet login, registration, listing submission are stop conditions.

## Submission Kit facts

### listing-copy.md (SUBM-03)
- **Name:** TrustLens
- **Tagline (≤80 chars — VERIFIED counts, all banned-word-clean):** `[VERIFIED: char count]`
  | Tagline | Chars |
  |---------|-------|
  | Deterministic trust scores for OKX.AI agents, in one paid MCP call | 66 |
  | Evidence-based hiring-trust scores for OKX.AI agents via one paid MCP call | 74 |
  | Hiring-trust scores for OKX.AI agents — one paid MCP call, deterministic JSON | 77 |
  | TrustScore for any OKX.AI agent — evidence-based, deterministic, one paid call | 78 |
  | Should you hire this OKX.AI agent? One paid MCP call, one deterministic verdict | 79 |
  - (Rejected: "One paid MCP call returns a deterministic hiring-trust score for any OKX.AI agent" = 81 chars, OVER.)
- **Category:** "Software Services" (brief) — note okx.ai's actual code is `SOFTWARE_SERVICES`, display "Software services". `[VERIFIED: listing filter set]`
- **Price:** 0.01 USDT/call. Endpoint URL placeholder + methodology URL (`<base>/#methodology`).
- **Description differentiation line** (bake in): TrustLens is a marketplace **hiring-trust** score (review authenticity, rating-vs-sales anomalies, sales velocity, price fairness) — distinct from creditworthiness (Factor), raw data feeds (TO1), and arbitration (Internet Court). `[CITED: FEATURES.md, PROJECT.md]`

### demo-script.md (SUBM-01) — 90s storyboard beats with REAL data
| Beat | Content | Verified data |
|------|---------|---------------|
| Problem | "Can you trust a marketplace agent before you pay it?" | — |
| Live MCP call | Claude calls `score_agent("这个能吃吗？")` → **A / 94 / high**, 5.0 rating on 539 sales | `[VERIFIED: score_agent]` |
| **Anomaly flag (the money beat)** | Call `score_agent("GlassDesk")` (id 3465) → **D / 45 / low confidence**; same 5.0 stars, but on **1 sale**. Read the reason: "perfect 5.0 rating backed by only 1 sale(s) — pattern consistent with limited review history; low confidence, flagged for thin data (not an assessment of conduct)." Two agents, both 5.0 — TrustLens shows *why* one is A and one is D. | `[VERIFIED: score_agent(3465) + built DB]` |
| Agent-calling-agent | One agent calls `score_agent` on another before hiring — the A2MCP flow. | (narrate; uses the same paid call) |
| Leaderboard + on-chain | Show `/` (272 agents, sortable, grades) + the 0.01 USDT/call settling on X Layer (the 402→paid flow from Phase 4). | `[VERIFIED: 272 rows built; Phase 4 paid flow]` |
- **Executable against clean-clone `docker compose up`.** Mark the Docker-engine start as HUMAN-ONLY.
- **Backup hero (if GlassDesk feels too obscure):** `Token Radar` (id 2991, D/52/low, 5.0 on 3 sales) or `Thumbnail Maker` (id 4511, D/45/low, 5.0 on 1 sale). AVOID `Factor Credit Desk` (4502) — it's a named competitor.

### x-post-draft.md (SUBM-02)
- Thread with `#OKXAI`. Neutral, factual, NO accusations (banned-word test spirit applies).
- Angle: one-call hiring-trust verdict + determinism (`score_version` + `data_as_of` + pure functions = same call, same bytes) + on-chain pay-per-call (0.01 USDT on X Layer, zero gas).
- Differentiation one-liner: "Not creditworthiness (Factor), not raw feeds (TO1), not arbitration (Internet Court) — a pre-purchase hiring-trust score for any OKX.AI agent." `[CITED: FEATURES.md]`

### Banned-word test extension (recommended)
Extend the existing banned-vocabulary test to scan `submission/*.md` for `fraud|scam|fake|manipulat` (case-insensitive). `[CITED: CONTEXT.md — "consider extending the test"]`

## OPS-03 status

**Already covered (VERIFIED green):** `python -m pytest -q` → **296 passed, scoring coverage 100.00%** (gate ≥90% intact). Suite includes: scoring components/engine/golden/persist, MCP tool schemas + in-process HTTP e2e (`test_server_app.py`, `test_server_tools.py`), x402 unit + gate + mocked-paid e2e (`test_payments.py`, `test_payments_gate.py`), indexer parse/census/db/refresh, web build/badge. `[VERIFIED: full run 2026-07-11]`

**What Phase 5 adds:** `tests/test_scraper.py` (canned-fixture parser + 5 degradation modes + merge + "scrape-failure-doesn't-change-exit-code"). Run subset with `--no-cov`. **No coverage-gate change** (scraper is not under `--cov=scoring`; the gate scopes only to `scoring/`). Optionally add the `submission/` banned-word scan test.

## State of the Art

| Old Approach (assumed pre-research) | Current Approach (empirically verified) | When Changed | Impact |
|--------------------------------------|------------------------------------------|--------------|--------|
| okx.ai 403s all bots | 200 for UA `TrustLens/1.0`; `robots.txt` `Allow: /` | Observed 2026-07-11 | Scraper CAN succeed; success fixture is a real 200 sample |
| okx.ai is an empty JS SPA (BeautifulSoup finds nothing) | Server-side rendered; `appState` JSON island parseable by html.parser + json.loads | Observed 2026-07-11 | Parse target = stable JSON keys, not brittle hashed DOM classes |
| Scrape target = DOM selectors | Scrape target = `appContext.initialProps.AgentDetailPage.overview` | Observed 2026-07-11 | Selectors demoted to documented fallback |
| Scraped categories map to the 9 buckets | okx.ai uses 6 codes with ZERO overlap | Observed 2026-07-11 | `category_source='listed'` needs mapping OR stays display-only (Option B recommended) |

**Deprecated/outdated:** The "403 + SPA" framing in PITFALLS.md Pitfall 7 (MEDIUM/LOW confidence, explicitly "inferred") is now empirically superseded — but its *prescription* (CSV-primary, one attempt, graceful fallback, canned tests) remains exactly right and is unchanged.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | okx.ai will keep serving `TrustLens/1.0` (no future Cloudflare bot challenge) | Scrapeability Verdict | LOW — the graceful-degradation design handles a future 403 exactly as the census fallback; nothing breaks, enrichment just stops. |
| A2 | The `appState` JSON shape is stable across okx.ai deploys | Parse target | MEDIUM — JSON keys are more stable than hashed CSS, but a frontend rewrite could rename them. The "changed markup" fixture + warning-on-miss makes this a soft failure, not a crash. |
| A3 | OKX ASP registration prompts in PROJECT.md are still current (fetched 2026-07-10) | README §10 | MEDIUM — quoted verbatim from a 1-day-old fetch; a human runs these steps and can correct live. Marked HUMAN-ONLY. |
| A4 | Extending the banned-word test to `submission/` is desired | OPS-03 | LOW — CONTEXT says "consider"; it's optional hardening, not a blocker. |
| A5 | The listing category "Software Services" is the right pick despite okx.ai's `SOFTWARE_SERVICES` being a distinct filter | listing-copy | LOW — brief says "Software Services" explicitly; the okx.ai display value "Software services" matches. |

**Note:** No `[ASSUMED]`-tagged claims about okx.ai's *scrapeability* remain — that was the whole point of the probe, and it is now `[VERIFIED: live probe]`. The assumptions above are forward-looking (stability) or human-owned (registration), not present-state facts.

## Open Questions (RESOLVED)

1. **Full-marketplace enrichment scope**
   - What we know: listing is 20/page × ~16 pages (`total: 305`); detail pages are 272 in census. At 1 req/s, either full crawl is ~5 min.
   - What's unclear: whether the timebox wants ANY live enrichment beyond proving the path, or just the graceful-fallback + fixtures (the designed deliverable).
   - Recommendation: scrape a SMALL bounded demo set (e.g. 3–5 detail pages, or none — fixtures suffice) to prove the path; defer full enrichment to v2 (INDX-05). The plan should make the sample size a constant.
   - **RESOLVED: bounded/gated `--scrape` path proves the mechanism; canned fixtures are the tested deliverable; full enrichment deferred to v2/INDX-05 (orchestrator decision, implemented in 05-01)**

2. **Category enrichment: Option A (map) vs Option B (display-only)**
   - What we know: 6-code okx.ai set vs 9-bucket derived set, zero overlap; scoring refuses non-canonical category text; Phase 2 percentiles depend on the derived distribution.
   - What's unclear: whether the user wants the real listed category surfaced at all.
   - Recommendation: **Option B** — enrich `sold`/`rating`/`price`/`positive_pct` (which match census semantics and feed scoring), leave `category` derived. Lowest risk, honors the neutral-language contract, still delivers freshness. Keep `category_source='listed'` as a documented-but-unused v2 seam.
   - **RESOLVED: Option B (orchestrator decision, locked in 05-01 — category stays derived; per-record scrape source-tagging also left as a documented v2/INDX-05 seam to preserve the determinism contract)**

3. **Docker rehearsal for the demo**
   - What we know: `docker compose up` self-seeds and serves everything on one port; the demo script must run against it. The Docker Desktop engine did not start in the Phase 3/4 build env.
   - What's unclear: whether the engine is available on the human's machine for the demo rehearsal.
   - Recommendation: the final human checklist includes "start Docker Desktop, `docker compose up`, rehearse the demo path" — the same carried item from Phase 3 HUMAN-UAT and Phase 4 VERIFICATION.
   - **RESOLVED: routed to the final human checklist; the plan produces an executable script but does not fake the run (orchestrator decision, locked in 05-03)**

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | everything | ✓ | 3.14.2 (≥3.11 ✓) | — |
| httpx | scraper HTTP | ✓ | 0.28.1 | — |
| beautifulsoup4 | scraper parse | ✓ | 4.15.0 | — |
| okx.ai reachability | scraper (dev/probe only, NEVER tests) | ✓ | 200 for UA TrustLens/1.0 | CSV fallback (by design) |
| pytest / pytest-cov | test suite | ✓ | 9.1.1 / 7.1.0 | — |
| node + npx | MCP Inspector (README doc + optional live check) | (documented) | — | README documents the exact command; raw-HTTP e2e already proves tools/list+call |
| Docker Desktop engine | `docker compose up` demo rehearsal | ✗ (build env) | client CLI 29.5.2 only | HUMAN-ONLY: start engine on the human's machine (carried Phase-3/4 item) |

**Missing dependencies with no fallback:** None that block Phase 5 code. The Docker engine is a human/demo-time step, not a code blocker (the same app is proven in-process + live uvicorn).

**Missing dependencies with fallback:** Docker engine → human starts it for the demo/UAT; okx.ai unreachability → CSV fallback (the designed behavior).

## Security Domain

> `security_enforcement: true`, ASVS level 1. The scraper introduces one new outbound-HTTP surface and one file-cache surface; submission docs are a language/reputation surface.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Scraper is unauthenticated read of a public site; no creds involved. |
| V3 Session Management | no | Stateless GETs. |
| V4 Access Control | no | No new endpoints; scraper is offline CLI, never request-path (assert no `server/*` imports it). |
| V5 Input Validation | **yes** | Scraped `appState` is UNTRUSTED third-party input. Cast/validate every field (`float()`/`int()` in try/except); NEVER let scraped text reach a reason-string template (`scoring/components.py` already refuses non-canonical categories; keep it that way). Scraped `name`/`tagline` are stored via parameterized `?` (indexer/db.py) — no SQL injection surface. |
| V6 Cryptography | no (only `hashlib.sha256` for cache keys — non-security use) | Never hand-roll crypto; sha256-for-filename is fine. |
| V7 Error Handling & Logging | **yes** | Log scraped ids/names with `%r` (log-injection + cp1252 safety, per census convention). No tracebacks or raw scraped cells into logs beyond `%r`. Warnings carry url/status, not raw body. |
| V12 Files & Resources | **yes** | Cache writes go ONLY under `data/cache/` (gitignored). Cache filename = `sha256(url)` — no path traversal from URL content. Hard request timeout (15s) prevents resource hang; single attempt prevents amplification against okx.ai. |
| V13 API / SSRF | **yes** | URLs are hardcoded to `https://www.okx.ai/...` (not user-supplied), so no SSRF. If an id ever comes from input, constrain to `^\d+$` before building the URL. |

### Known Threat Patterns for the scraper + submission docs

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious/oversized scraped payload feeds scoring | Tampering | Field-level cast+validate; scraped category never renders to text; scoring stays pure over validated `AgentRecord`s. |
| Scraped CJK/newline text in logs → log injection / console crash | Tampering / DoS | `%r` logging + `utf-8` stdout reconfigure (already the refresh convention). |
| Path traversal via cache filename | Tampering | `sha256(url).hexdigest()` filename — no user-controlled path segments. |
| Hammering okx.ai (impoliteness → IP block) | DoS (self-inflicted) | ≤1 req/s sleep-between, single attempt, on-disk cache (cache hit = no network), hard timeout. |
| Accusatory language against a named agent in submission copy | Reputation / (Repudiation of neutrality) | Banned-word test extended to `submission/`; demo uses the neutral "flagged for thin data (not an assessment of conduct)" reason string; avoid competitor names as demo subjects. |
| Scraper crash breaks offline determinism | DoS (pipeline) | scrape_agents returns `[]` on any failure; refresh exit contract unchanged; test with a 403 MockTransport. |

## Sources

### Primary (HIGH confidence)
- **Live okx.ai probe (2026-07-11, this machine, UA TrustLens/1.0, ≤1 req/s):** `robots.txt` (200, Allow: /), `/agents` (200, SSR, `agentList` total 305), `/agents/3345` (200, SSR, full `overview`). Raw bodies + parsed `appState` saved to scratchpad. Parser recipe dry-run confirmed. Census-fidelity cross-check vs built DB.
- **Built census DB (`data/trustlens.db`, `python -m indexer.refresh`, 2026-07-11):** 272 agents, 121 scored, 151 NR; 42 flagged (5.0/thin-sales); GlassDesk (3465) D/45/low and 3345 A/94/high verified via `score_agent`.
- **Codebase (read directly):** `indexer/refresh.py` (persist seam, 0/1/2 exit contract, utf-8 stdout), `indexer/census.py`, `indexer/models.py` (AgentRecord + `category_source`), `indexer/db.py` (snapshots.source, parameterized writes), `indexer/parse.py`, `indexer/category.py` (CANONICAL_CATEGORIES), `scoring/components.py` (flag logic, canonical-category gate), `server/tools.py`, `server/main.py`, `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `.gitignore` (data/cache/ ignored).
- **Full test run (2026-07-11):** `python -m pytest -q` → 296 passed, scoring coverage 100%.
- **Phase docs:** `04-VERIFICATION.md` (verified curl check, mock/SDK seam, Docker human blocker), `03-05-PLAN.md` (verified Inspector commands incl. CJK), `03-HUMAN-UAT.md` (Docker smoke test).

### Secondary (MEDIUM confidence)
- `PROJECT.md` / CLAUDE.md — OKX ASP prompts (verbatim, fetched 2026-07-10), x402 facts, stop conditions, differentiation. (Human-owned steps; 1-day-old fetch.)
- `.planning/research/FEATURES.md` — differentiation vs Factor/TO1/Internet Court, neutral-language norms.

### Tertiary (LOW confidence)
- `.planning/research/PITFALLS.md` Pitfall 7 (okx.ai "403 + SPA") — explicitly self-labeled inferred/MEDIUM-LOW; **now empirically superseded** by the live probe (verdict: 200 + SSR). Its prescription (CSV-primary, graceful fallback) stands.

## Metadata

**Confidence breakdown:**
- Scrapeability verdict: HIGH — direct live probe, raw bodies saved, parser dry-run + census cross-check.
- Standard stack: HIGH — every dep already pinned and import-verified; no installs.
- Architecture / graceful-degradation flow: HIGH — seams read from live code; the control flow maps to real failure signatures.
- Demo agent: HIGH — GlassDesk (3465) and 3345 verified via `score_agent` against the built DB.
- README commands: HIGH — each verified in an earlier phase or this session.
- Category enrichment path: MEDIUM — the mismatch is verified; the choice between Option A/B is a design call left to planning (recommend B).

**Research date:** 2026-07-11
**Valid until:** okx.ai structure ~7 days (fast-moving frontend — re-probe if the plan is executed >1 week out); code seams / demo data stable until the next refresh; OKX ASP prompts as of 2026-07-10 fetch.
