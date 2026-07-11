# Requirements: TrustLens

**Defined:** 2026-07-10
**Core Value:** Any human or agent can get a deterministic, evidence-based answer to "should I hire this OKX.AI agent?" in one paid MCP call.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Indexer & Data

- [x] **INDX-01**: `python -m indexer.refresh` populates SQLite from the census CSV with zero network access
- [x] **INDX-02**: Parser handles census edge cases: K-suffixed sold counts ("1.55K sold"), subscript-zero USDT prices ("0.0₄15 USDT"), missing ratings (price-like value in rating column with empty positive %), multiline quoted taglines, CJK agent names
- [x] **INDX-03**: SQLite persists `agents` (id, name, category, price, sold, rating, positive_pct, tagline, first_seen, last_seen) and `snapshots` (time series per refresh)
- [ ] **INDX-04**: Polite scraper for okx.ai listing + agent detail pages: ≤1 req/sec, User-Agent `TrustLens/1.0`, on-disk response cache, graceful degradation to census CSV when blocked or markup changes

### Scoring Engine

- [x] **SCOR-01**: Pure, deterministic scoring functions produce 0–100 TrustScore + A–F grade + component breakdown for any agent row
- [x] **SCOR-02**: Components implemented: sales volume & velocity, review-count-vs-sales ratio, rating credibility (5.0 with <5 sales = low confidence, flagged not accused), price-vs-category percentile, listing age/consistency — every component returns a `reason` string
- [x] **SCOR-03**: All scoring/output wording is neutral and factual ("pattern consistent with…", "insufficient data") — never accusatory ("fraud", "scam", "fake")
- [x] **SCOR-04**: pytest coverage ≥90% on `scoring/`, including edge cases: 0 sales, missing rating, "1.55K"-sold parsing

### MCP Server

- [ ] **MCPS-01**: MCP server exposes exactly 4 tools: `score_agent(agent_id_or_name)`, `compare_agents(ids)`, `category_leaderboard(category, limit=10)`, `marketplace_stats()`
- [ ] **MCPS-02**: All tool responses are deterministic JSON including `generated_at` and `methodology_url` fields
- [ ] **MCPS-03**: `/healthz` endpoint returns service health
- [ ] **MCPS-04**: `score_agent("这个能吃吗？")` and `score_agent("3345")` both return a full JSON score card in <500ms from a warm DB
- [ ] **MCPS-05**: MCP Inspector successfully lists and calls all 4 tools

### x402 Payments

- [ ] **PAYX-01**: Call without payment returns HTTP 402 with x402 v2 payment-requirements JSON (scheme `exact`, network `eip155:196`, `payTo`, atomic `amount`) and the `PAYMENT-REQUIRED` header
- [ ] **PAYX-02**: With `X402_MOCK=1`, a mock-paid call returns the scored result; verification is a pluggable interface so the OKX Payment SDK (`okxweb3-app-x402`) can drop in at deploy time
- [ ] **PAYX-03**: Payment config via environment variables only (`TRUSTLENS_PAY_TO`, `TRUSTLENS_PRICE_USDT`, `X_LAYER_RPC`, `X402_MOCK`); no hardcoded keys/addresses; `.env` gitignored; `.env.example` documents every var with placeholders

### Leaderboard Site

- [ ] **WEB-01**: Single static HTML page (inline CSS/JS, no framework) served by FastAPI at `/` — ranked table of all indexed agents with TrustScore + grade badges, sortable, category filter, loads in <2s
- [ ] **WEB-02**: Page includes "About the methodology" section and a "TrustLens Verified" badge embed snippet
- [ ] **WEB-03**: Page content auto-regenerates from SQLite on indexer refresh

### Ops & Tests

- [ ] **OPS-01**: `docker compose up` serves everything (MCP + leaderboard + healthz) on one port (Dockerfile + docker-compose.yml)
- [ ] **OPS-02**: README covers: local run, deploy steps (HTTPS-capable host; HK/Singapore suggestion), MCP Inspector test instructions, and the exact OKX ASP registration prompts with remaining manual steps
- [ ] **OPS-03**: Full pytest suite passes: scoring functions, MCP tool schemas, and one end-to-end call against a local server with x402 mocked

### Submission Kit

- [ ] **SUBM-01**: `submission/demo-script.md` — 90-second demo storyboard (problem → live MCP call from Claude → score card with anomaly flag → agent-calling-agent flow → leaderboard + on-chain revenue)
- [ ] **SUBM-02**: `submission/x-post-draft.md` — launch thread with #OKXAI
- [ ] **SUBM-03**: `submission/listing-copy.md` — ASP name, tagline ≤80 chars, description, category Software Services, price 0.01 USDT

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Payments

- **PAYX-04**: Real on-chain settlement via `okxweb3-app-x402` facilitator (requires OKX API credentials + wallet — human-gated deploy-time step; integration point + docs ship in v1)

### Data

- **INDX-05**: Scheduled recurring re-scrapes building longitudinal snapshot series for richer velocity/consistency signals

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Auth systems / user accounts | Brief: "Do NOT add" — x402 payment IS the access control |
| Databases beyond SQLite | Brief constraint; 272 agents fit trivially |
| Admin panels, dark mode | Brief: "Do NOT add… any feature not listed" |
| Accusatory labels on agents | Legal/defamation risk; neutral analytics language mandated |
| Remote deploy / domain purchase / wallet ops / listing submission / public posts | Stop conditions — human performs these; build prepares materials |
| New runtime dependencies beyond FastAPI, FastMCP, SQLite, httpx, BeautifulSoup (+uvicorn, pytest dev) | Brief requires asking first |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INDX-01 | Phase 1 | Complete |
| INDX-02 | Phase 1 | Complete |
| INDX-03 | Phase 1 | Complete |
| INDX-04 | Phase 5 | Pending |
| SCOR-01 | Phase 2 | Complete |
| SCOR-02 | Phase 2 | Complete |
| SCOR-03 | Phase 2 | Complete |
| SCOR-04 | Phase 2 | Complete |
| MCPS-01 | Phase 3 | Pending |
| MCPS-02 | Phase 3 | Pending |
| MCPS-03 | Phase 3 | Pending |
| MCPS-04 | Phase 3 | Pending |
| MCPS-05 | Phase 3 | Pending |
| PAYX-01 | Phase 4 | Pending |
| PAYX-02 | Phase 4 | Pending |
| PAYX-03 | Phase 4 | Pending |
| WEB-01 | Phase 3 | Pending |
| WEB-02 | Phase 3 | Pending |
| WEB-03 | Phase 3 | Pending |
| OPS-01 | Phase 3 | Pending |
| OPS-02 | Phase 5 | Pending |
| OPS-03 | Phase 5 | Pending |
| SUBM-01 | Phase 5 | Pending |
| SUBM-02 | Phase 5 | Pending |
| SUBM-03 | Phase 5 | Pending |
| PAYX-04 | v2 (not in roadmap) | Deferred |
| INDX-05 | v2 (not in roadmap) | Deferred |

**Coverage:**
- v1 requirements: 25 total (count corrected from 24 during roadmap mapping — MCP Server section contains 5 IDs)
- Mapped to phases: 25
- Unmapped: 0 ✓

---
*Requirements defined: 2026-07-10*
*Last updated: 2026-07-10 after roadmap creation (traceability mapped, 5 phases)*
