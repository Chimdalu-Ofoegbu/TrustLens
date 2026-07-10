# Project Research Summary

**Project:** TrustLens — paid A2MCP trust-score service for the OKX.AI agent marketplace
**Domain:** Paid agent-callable data API (MCP-over-HTTPS + x402 pay-per-call) with deterministic marketplace trust/reputation scoring
**Researched:** 2026-07-10
**Confidence:** HIGH

## Executive Summary

TrustLens sells one answer — "should I hire this agent?" — as a 0.01 USDT/call MCP service over the 272-agent OKX.AI marketplace census, with a free leaderboard and embeddable badge as the marketing funnel. Research across established trust-score products (SecurityScorecard, FICO, BBB, Fakespot, ReviewMeta) shows the score itself is table stakes; what makes a score *credible* is the conventional envelope around it: 0–100 integer plus A–F grade with published bands, per-component breakdown, FICO-style reason strings citing observed-vs-benchmark numbers, an explicit confidence/NR "insufficient data" state, versioned methodology, dual timestamps, and strictly neutral statistical wording (the defamation shield — never "fraud/scam/fake"). Determinism is the sellable property: same call + same snapshot = same bytes, which no LLM-backed competitor can match and which makes the required ≥90% coverage on `scoring/` cheap.

The recommended architecture is two runtimes sharing one SQLite file: an **offline refresh pipeline** (census CSV → normalizers → SQLite → pure-function scoring → precomputed `scores` table → static leaderboard HTML) and an **online read-only single-port FastAPI server** (FastMCP 3.x `http_app()` mounted at `/mcp` with combined lifespans, pure ASGI x402 middleware gating `tools/call`, pluggable Mock/OKX payment verifier). The server never scrapes, never scores, never writes — paid calls are sub-millisecond indexed SELECTs, trivially inside the 500ms budget. The polite okx.ai scraper is a timeboxed (~2h) optional enhancement behind a CLI flag, never the critical path: okx.ai 403s generic bots and the census CSV is the designed primary data source.

The stack is locked and fully verified with one material finding: **FastMCP is now 3.x, not 2.x** — the core API survives, but v2-era constructor kwargs are gone and most online tutorials are wrong; pin `fastmcp>=3,<4` and follow v3 docs only. The top risks are integration wire-format risks, not build risks: (1) the FastMCP mount silently fails at request time unless the parent FastAPI receives the MCP app's lifespan; (2) the OKX pre-registration check (`curl -i -X POST /mcp` → 402 + `PAYMENT-REQUIRED` header) judges x402 **v2** shape — base64 header challenge, atomic-unit string amounts (`"10000"` for 0.01 USDT at 6 decimals) — while most examples online are v1; (3) the hackathon deadline chain (submit for review July 10–11, up to 24h review, live before July 17 23:59 UTC, human-only deploy/registration steps) means Docker/README/registration materials are deliverables that land with the server phase, not final-day polish; (4) four observed census edge cases (subscript-zero prices, shifted rating column, `1.55K` suffixes, multiline CJK taglines) corrupt scores *silently* — parsers with literal fixture rows are the first tests in the repo.

## Key Findings

### Recommended Stack

Stack is locked by PROJECT.md; research verified exact current versions, integration patterns, and one API-generation surprise (FastMCP 3.x). All pins resolve cleanly (`fastapi 0.139.0` + `fastmcp 3.4.4` → starlette 1.3.1, no conflicts). Skip SQLAlchemy even though the lock allows it — stdlib `sqlite3` with connection-per-operation is correct at 272 rows. Hand-roll the x402 middleware on Starlette primitives with `X402_MOCK=1`; the `okxweb3-app-x402` SDK is a documented deploy-time drop-in that requires OKX API creds (human-review stop condition, correctly out of v1 code).

**Core technologies:**
- Python 3.13 (`python:3.13-slim`): runtime — mature bugfix line, full wheel coverage for every dep
- FastAPI 0.139.0 + uvicorn 0.51.0: single-port host app (MCP mount, static leaderboard, `/healthz`, x402 middleware)
- FastMCP 3.4.4 (pin `>=3,<4`): MCP server — `from fastmcp import FastMCP`, `mcp.http_app()` Streamable HTTP; v3 `@mcp.tool` returns the plain function, so tools are directly unit-testable
- stdlib `sqlite3`: agent store — WAL at init, read-only URI connections per request on the server, offline writer
- httpx 0.28.1 + beautifulsoup4 4.15.0 (`html.parser` backend — lxml is an unlisted dep): offline polite scraper only
- pytest 9.1.1 + pytest-cov 7.1.0: coverage gate scoped to `scoring/` via `--cov=scoring --cov-fail-under=90`

Known-bad patterns to ban from day one: `from mcp.server.fastmcp import FastMCP` (that's FastMCP 1.0, a different class), v2 constructor kwargs (`host=`, `port=`, `stateless_http=` in the constructor), SSE transport, static mount at `/` registered before other routes, shared SQLite connections across threads. See STACK.md "What NOT to Use".

### Expected Features

The product surface is fixed by the brief (4 tools: `score_agent`, `compare_agents`, `category_leaderboard`, `marketplace_stats`; leaderboard page; badge; 0.01 USDT/call). Research answers what makes that surface credible: every established trust-score product converges on the same output envelope, and missing pieces make the score look amateur or legally careless.

**Must have (table stakes):**
- Dual encoding: 0–100 integer + A–F grade with published band thresholds; integer only (no false-precision decimals)
- Per-component breakdown — 5 components each `{score, weight, observed, benchmark, reason}` with FICO-style ranked, neutral, deterministic template reason strings
- Confidence field + explicit `NR`/insufficient-data state (a *successful* response, not an error); dirty census rows degrade confidence, never crash
- Response envelope on all 4 tools: `score_version`, `generated_at` + `data_as_of`, marketplace-rating passthrough, constant neutral disclaimer + methodology URL
- MCP `outputSchema` + `structuredContent` on all 4 tools (spec MUST once schema is declared)
- Neutral-wording vocabulary enforced by a banned-word test (`fraud|scam|fake|manipulat`) across API, site, badge, and listing copy
- Leaderboard with methodology section, "272 agents · data as of … · methodology v1.0.0" header, NR rows unranked
- Self-hosted badge SVG + copy-paste snippet linking back to the live score (unlinked badges are worthless)
- x402 402-challenge flow with `X402_MOCK=1`

**Should have (competitive, vs Factor Credit Desk / TO1 Intelligence / Internet Court MCP):**
- One-call hiring verdict positioning — pre-purchase decision in a single deterministic JSON, vs lending scores, raw feeds, or post-hoc arbitration
- Category-relative scoring (price percentile, ratio vs category median) — makes reasons quantitative and fair
- `compare_agents` per-component winners with explicit deterministic tie-breaks
- Reproducibility guarantee as listed sales copy: `score_version` + `data_as_of` + pure-function engine

**Defer (v1.x / v2+):**
- shields.io endpoint JSON, score deltas between snapshots (need a second snapshot), correction channel, history API/webhooks, cross-marketplace coverage

**Anti-features (explicitly rejected):** accusatory labels, LLM-generated prose in responses (kills determinism/testability), "safe to hire" endorsements, scoring thin data anyway, live re-scrape per paid call, pay-to-improve, any surface beyond the fixed 4 tools.

### Architecture Approach

Two independent runtimes share one SQLite file: an offline refresh pipeline (`python -m indexer.refresh [--scrape]`: census → optional scrape → `scoring.compute_all` → `web.build` → `meta.last_refresh`) and an online read-only server (uvicorn, one port). Precompute-at-refresh beats compute-on-request: sub-ms paid calls, leaderboard/tools serve identical numbers from the same run, and every score row carries `computed_at` + `methodology_version` + source snapshot — reproducible evidence, which is the pitch. Packages stay acyclic (`indexer/`, `scoring/`, `web/` never import `server/` or `payments/`); `server/app.py` `create_app()` is the only composition root; `payments/` sees only HTTP scope + JSON-RPC method names, so swapping in OKX's `x402ResourceServer` middleware at deploy time replaces one package at the same layer.

**Major components:**
1. `db/` — schema (agents, snapshots, scores, meta), WAL, read-only URI connections for the server
2. `indexer/` — census CSV parsing/normalizers (the risk pocket), polite scraper with cache + CSV fallback, refresh CLI orchestrator
3. `scoring/` — pure deterministic functions (`score_agent(record, category_stats, as_of)`) with no I/O and no wall clock; `persist.py` is the only DB-touching module — this is what makes ≥90% coverage cheap
4. `web/build.py` — static leaderboard `dist/index.html` via stdlib `string.Template` (Jinja2 is not in the allowed deps)
5. `server/` — FastMCP instance + exactly 4 read-only tools; `create_app()` mounts MCP with `combine_lifespans`, routes ordered `/healthz` → `/mcp` → `/` last
6. `payments/` — x402 v2 challenge builder (`decimal.Decimal` atomic-unit conversion in one place), `PaymentVerifier` Protocol with fail-closed `MockVerifier`, pure ASGI middleware (NOT `BaseHTTPMiddleware`) with configurable `FREE_METHODS` gating

### Critical Pitfalls

1. **FastMCP version drift** — `pip install fastmcp` is 3.x; tutorials and LLM memory show v2/v1. Pin `fastmcp>=3,<4`, one import style everywhere, 5-line smoke server in scaffolding before any tools.
2. **Mount without lifespan** — `app.mount("/mcp", mcp.http_app())` on a plain `FastAPI()` starts fine, then every MCP request 500s ("Task group is not initialized"). Always `http_app(path="/")` + `FastAPI(lifespan=combine_lifespans(...))` + mount; first integration test calls a tool through the mounted HTTP path inside `with TestClient(app):`.
3. **x402 v1/v2 wire confusion** — v2 (Dec 2025) moved the challenge into a base64 `PAYMENT-REQUIRED` header; `amount` is an atomic-unit *string* (`"10000"`), network `eip155:196` (testnet `1952`). Build the challenge in one pure `build_402_challenge()` with golden-file tests; the OKX pre-registration curl check must pass against local Docker *before* the human registers.
4. **Payment gate placement** — gate everything and no client can handshake; gate only inside tools and the bare-POST curl check gets 406 instead of 402. Pure ASGI middleware inspects the JSON-RPC method: `initialize`/`notifications/*`/`tools/list` free (configurable), `tools/call` and unparseable bodies → 402; `/healthz` and `/` never gated. E2E test matrix covers all four rows.
5. **Census CSV silent corruption** — subscript-zero prices (`0.0₄15` = 0.000015, and naive non-ASCII stripping yields a 1,000–10,000x price error), shifted rating column (unrated agents get rating 0.01/5 → falsely tanked score = neutral-language violation), `1.55K sold`, multiline quoted taglines. Pure `parsers.py` with the observed weird values as literal fixtures *before* writing the indexer; end-of-parse assertion of exactly 272 rows; agent 3345 (`这个能吃吗？`) as a named test case with NFKC-normalized name lookup.

Also load-bearing: fail-closed mock parsing (`os.getenv("X402_MOCK", "0") == "1"` — `"0"`/`"false"` are truthy strings), clock injection (`as_of` parameter) so scores don't drift by the day, read-only per-request SQLite connections, static-mount-last route ordering, and the critical-path inversion — ops files are deliverables, not polish.

## Implications for Roadmap

Based on research, suggested phase structure (6 phases; each leaves a demoable state):

### Phase 1: Foundation — Scaffolding + Data Indexer
**Rationale:** Everything downstream reads SQLite rows; census parsing is where silent data corruption lives; version pins and coverage config prevent the two cross-cutting failure modes (FastMCP drift, coverage scramble). The category open question must be resolved here because it changes the scoring inputs.
**Delivers:** Repo skeleton with pinned `requirements.txt` + pytest/coverage config; `db/schema.sql` (agents, snapshots, scores, meta; WAL; `name_normalized` column); `python -m indexer.refresh` loads exactly 272 agents from the census CSV with all four edge cases normalized and fixture-tested; category-source decision (scrape detail pages vs deterministic buckets).
**Addresses:** Data foundation for every feature; CJK-safe lookup groundwork.
**Avoids:** Pitfalls 1 (pins), 8 (CSV corruption), 9 (normalized names), 10 (writer/WAL), 11 (coverage config early).

### Phase 2: Scoring Engine
**Rationale:** Pure functions over plain records — no dependencies, can start in parallel with Phase 1. This is the credibility core, the coverage target, and where determinism is decided (clock injection). Cheap to test now, impossible to retrofit later.
**Delivers:** 5 components each `{score, weight, observed, benchmark, reason}`; 0–100 + A–F + NR grade map; confidence derivation from field completeness; category stats (medians/percentiles) computed at index time; neutral reason templates + banned-word test; ≥90% coverage on `scoring/` green in config; `persist.py` writes the `scores` table in one transaction.
**Uses:** Pure Python + stdlib; golden-file tests with injected `as_of`.
**Avoids:** Pitfall 11 (time-dependent scores), anti-features (accusatory labels, decimal precision, always-score-thin-data).

### Phase 3: MCP Server + Leaderboard (free service) + Docker skeleton
**Rationale:** De-risk the FastMCP mount/lifespan integration — the #1 documented failure — before money enters; per the critical-path pitfall, Docker/compose/`.env.example` land the moment the server serves anything, so `docker compose up` stays perpetually demoable.
**Delivers:** 4 tools with `outputSchema`/`structuredContent` and the full envelope (version, timestamps, passthrough, disclaimer); "not found + closest candidates" lookup ladder; `create_app()` with combined lifespans and fixed route order (`/healthz`, `/mcp`, `/` last) plus route-order test; `web/build.py` leaderboard with methodology section and badge SVG + embed snippet; curl check for 307-free `/mcp`; Dockerfile + compose + `.env.example`.
**Uses:** FastMCP 3.x `http_app(path="/")` mount pattern (verified verbatim in STACK.md), `FileResponse`, stdlib templating.
**Avoids:** Pitfalls 2, 3, 12, 13 (ops timing).

### Phase 4: x402 Payment Layer
**Rationale:** Gating a *working* service is far easier to debug than co-developing tools and payments. The OKX pre-registration curl check is the registration gate; the README deploy + ASP registration section is written the moment this phase completes, because that is when the check can be rehearsed locally.
**Delivers:** `payments/protocol.py` (v2 challenge builder, `Decimal` atomic-unit conversion, golden tests on the decoded `PAYMENT-REQUIRED` header); `PaymentVerifier` Protocol + fail-closed `MockVerifier` with startup banner; pure ASGI middleware with configurable `FREE_METHODS`; e2e matrix (bare POST → 402 + header; initialize/tools/list → 200; unpaid tools/call → 402; mock-paid call → result; `/healthz` and `/` ungated); README registration section with exact Onchain OS prompts.
**Avoids:** Pitfalls 4, 5, 6; anti-patterns (BaseHTTPMiddleware body reads, float amounts, gating the handshake).

### Phase 5: Scraper Enhancement (timeboxed ~2h)
**Rationale:** Census-only already yields a complete working demo; okx.ai markup/bot-protection is the least controllable dependency, so it is sequenced after the money path. CSV fallback is the designed behavior, not a failure. Exception: if Phase 1 chose detail-page scraping for categories, a minimal category scrape pulls forward into Phase 1.
**Delivers:** Polite scraper (1 req/s sleep between requests, `TrustLens/1.0` UA, on-disk cache, hard timeout, single attempt on 403); every code path ends in parsed fields or CSV-fallback-with-warning; canned-response tests for the 403 path and the "200 but empty SPA shell" path; `__NEXT_DATA__`/embedded-JSON check before DOM parsing; re-run refresh.
**Avoids:** Pitfall 7 (scraper as critical path).

### Phase 6: Hardening + Submission Kit
**Rationale:** The deadline chain (submit → up to 24h review → live before July 17 23:59 UTC, with human-only deploy/registration steps) demands the kit be finished at least a day early and the demo rehearsed against the container, because pitfalls 2/3/5 all have "works locally, fails in demo" modes.
**Delivers:** Clean-clone `docker compose up` verification (one port serves `/`, `/healthz`, `/mcp`; DB present in container; curl-free healthcheck); full "Looks Done But Isn't" checklist sweep from PITFALLS.md; README complete (deploy, ASP registration prompts, pre-registration curl check, mock→SDK swap instructions); demo script (Inspector connect → 402 → mock-paid call → leaderboard) executed end-to-end at least once.
**Avoids:** Pitfall 13.

### Phase Ordering Rationale

- **Data → scoring → serving mirrors the dependency graph** (schema → snapshots → scores → tools/leaderboard); scoring's pure functions have no dependencies and can start in parallel with Phase 1.
- **Free service before payment** isolates the two hardest integrations (FastMCP mount, x402 wire format) so they are never debugged simultaneously — the single biggest de-risking decision available.
- **Scraper deliberately late:** the brief designed the census CSV as primary; a scraper failure can consume days (403 puzzle-solving) while the actual product starves. Timebox and fallback are structural.
- **Ops distributed, not deferred:** Docker with the server phase, README registration section with the payment phase, rehearsed kit a day before the deadline — this directly counters the hackathon critical-path inversion on a 7-day timeline with a 24h external review in the loop.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (x402):** MEDIUM-confidence items to verify at build time — whether OKX expects base64 or raw JSON in the `PAYMENT-REQUIRED` header (make encoding a one-line switch), and gating granularity (official x402 guide gates only tool execution; one live OKX A2MCP service gates everything — keep `FREE_METHODS` configurable and check `okxweb3-app-x402`'s middleware source once).
- **Phase 1 (category derivation):** the census CSV has NO category column, yet `category_leaderboard` and the price-vs-category component require one. Quick investigation (does `okx.ai/agents/<id>` expose a category? else deterministic buckets from tagline keywords/price bands, disclosed on the methodology page) must land before scoring is finalized.

Phases with standard patterns (skip research-phase):
- **Phase 2 (scoring):** pure Python + stdlib, conventions fully specified in FEATURES.md.
- **Phase 3 (MCP server/leaderboard):** the exact FastMCP 3.x mount pattern is verified with code in STACK.md/ARCHITECTURE.md.
- **Phase 5 (scraper):** the fallback design *is* the answer; no research can make okx.ai more scrapeable.
- **Phase 6 (ops):** Dockerfile/compose patterns verified; checklist already written in PITFALLS.md.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions live-verified on PyPI 2026-07-10; FastMCP v3 patterns verified against Context7 official docs + v2→v3 upgrade guide; dependency resolution cross-checked |
| Features | HIGH | Conventions drawn from official docs of SecurityScorecard, FICO, BBB, Fakespot, ReviewMeta, MCP 2025-06-18 spec; legal framing MEDIUM (patterns HIGH) |
| Architecture | HIGH / MEDIUM | FastMCP composition and x402 v2 wire format HIGH (official docs); OKX-specific gating granularity MEDIUM (conflicting ecosystem evidence — made configurable by design) |
| Pitfalls | HIGH | FastMCP/SQLite/pytest/Docker pitfalls verified against official docs and GitHub issues; OKX wire details MEDIUM (verify at build time); okx.ai scraping behavior MEDIUM (403 observed, SPA inferred) |

**Overall confidence:** HIGH

### Gaps to Address

- **Category source (blocks scoring finalization):** census CSV lacks a category field. Resolve in Phase 1 — scrape from detail pages or derive deterministic buckets with the method disclosed; changes `CategoryStats` inputs.
- **OKX `PAYMENT-REQUIRED` header encoding (base64 vs raw JSON):** MEDIUM confidence. Challenge builder makes encoding a one-line switch; verify against the OKX x402 doc during Phase 4 and golden-test the decoded shape.
- **Gating granularity under OKX review:** free-handshake vs gate-everything both pass the curl check; ship `FREE_METHODS` as one-line config so flipping during review costs minutes. The real OKX SDK middleware's behavior wins at deploy time.
- **okx.ai scrapeability:** 403 for generic bots observed; pages may be JS-rendered SPA shells. Absorbed by design (CSV primary, 2h timebox, canned-response tests) — not a blocker.
- **Real x402 settlement untested until deploy:** `okxweb3-app-x402` needs OKX API creds (human stop condition). Mitigated by matching the documented wire format byte-for-byte behind the `PaymentVerifier` seam, failing closed at startup, and documenting the SDK swap in the README.

## Sources

### Primary (HIGH confidence)
- Context7 `/prefecthq/fastmcp` (v3 docs) — `http_app()` mount, lifespan requirement, `combine_lifespans`, transports, `stateless_http`, in-memory `Client(mcp)` testing
- gofastmcp.com — v2→v3 upgrade guide (constructor kwargs removed, `@mcp.tool` returns plain function, `get_tools()`→`list_tools()`), FastAPI integration
- PyPI JSON API (live 2026-07-10) — exact versions/`requires_dist` for all runtime and dev pins; docker-library/python `versions.json` for `python:3.13-slim`
- MCP Specification 2025-06-18 (Tools) — `outputSchema` MUST-conform, `structuredContent`, `isError` semantics
- coinbase/x402 v2 spec + HTTP transport spec + x402.org MCP guide — `PAYMENT-REQUIRED`/`PAYMENT-SIGNATURE`/`PAYMENT-RESPONSE` base64 headers, tool-execution-level gating
- SecurityScorecard, FICO/myFICO/VantageScore, BBB, Fakespot, ReviewMeta, Trustpilot TrustBox, shields.io official docs — score envelope, reason codes, NR state, neutral wording, badge conventions
- FastMCP/python-sdk/awslabs GitHub issues (#518, #1220, #1367, #737, #1168, #732, #1544, #2533, #1276) — lifespan, 307-redirect, and version-drift failure modes
- pytest-cov changelog — 7.x coverage-gate behavior
- PROJECT.md — OKX x402 challenge fields, `eip155:196`/`1952`, pre-registration curl check, census edge cases, deadline chain (fetched 2026-07-10)

### Secondary (MEDIUM confidence)
- Mario A2MCP Intelligence Suite (live OKX A2MCP service, Glama listing) — gates entire `/mcp`, `mock-x402`/`okx-x402` mode switch, USDT 6 decimals on X Layer (single source)
- stdlib `sqlite3` threading/WAL, Starlette routing order and pure-ASGI body replay — stable documented behavior
- Defamation fact-vs-opinion framing (Minc Law, KJK) — informs neutral-wording constraint
- okx.ai 403 for generic bots — observed first-hand; SPA rendering inferred

### Tertiary (LOW confidence)
- Zuplo / dev.to / Simplescraper x402 ecosystem posts — background context only, superseded by official specs

---
*Research completed: 2026-07-10*
*Ready for roadmap: yes*
