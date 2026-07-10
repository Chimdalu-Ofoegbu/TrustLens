# Roadmap: TrustLens

## Overview

TrustLens goes from a 272-agent census CSV to a live, paid A2MCP trust-score service in five phases that mirror the dependency graph. First the data foundation (a SQLite indexer that survives every observed census edge case, plus the category-source decision that scoring depends on). Then the deterministic scoring engine — the credibility core, with its ≥90% coverage gate and neutral-wording guarantee. Then the free service surface: 4 MCP tools, leaderboard, and /healthz on one dockerized port, de-risking the FastMCP mount/lifespan integration before money enters. Then the x402 v2 payment gate, rehearsing the exact OKX pre-registration curl check against local Docker. Finally the timeboxed scraper enhancement plus hardening and the submission kit. Every phase ends in a demoable state, and ops files land with the phases that need them rather than as final-day polish — the hackathon deadline chain (submit for review July 10–11, up to 24h review, live before July 17 23:59 UTC, human-only deploy/registration steps) leaves no room for a critical-path inversion.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation & Data Indexer** - Census CSV parsed edge-case-safe into SQLite on a pinned scaffold; category source resolved
- [ ] **Phase 2: Scoring Engine** - Deterministic 0–100 TrustScore + A–F grade with neutral per-component reasons, ≥90% coverage on scoring/
- [ ] **Phase 3: MCP Server & Leaderboard** - 4 MCP tools + static leaderboard + /healthz served free from one dockerized port
- [ ] **Phase 4: x402 Payment Layer** - x402 v2 402-challenge gate with pluggable mock verifier; OKX pre-registration check passes locally
- [ ] **Phase 5: Scraper, Hardening & Submission Kit** - Timeboxed polite scraper, full test suite, complete README, rehearsed demo/listing materials

## Phase Details

### Phase 1: Foundation & Data Indexer
**Goal**: The 272-agent census is reliably parsed into a queryable SQLite store on a pinned, test-ready scaffold — the data foundation every downstream feature reads
**Depends on**: Nothing (first phase)
**Requirements**: INDX-01, INDX-02, INDX-03
**Success Criteria** (what must be TRUE):
  1. `python -m indexer.refresh` loads exactly 272 agents from the census CSV into SQLite with zero network access
  2. All four observed census edge cases parse to correct values under fixture tests: "1.55K sold" → 1550; "0.0₄15 USDT" → 0.000015; shifted rating column → missing rating (never a false near-zero rating); multiline quoted taglines and CJK names ("这个能吃吗？") preserved with NFKC-normalized name lookup
  3. `agents` table persists id, name, category (populated by a documented deterministic method — the source decision resolved this phase), price, sold, rating, positive_pct, tagline, first_seen, last_seen; `snapshots` gains one time-series row per refresh, and re-running refresh does not corrupt or duplicate agents
**Plans**: 4 plans

Plans:
- [x] 01-01-PLAN.md — Scaffold (pyproject with pinned deps, pytest tooling) + verified pure field parsers (wave 1)
- [x] 01-02-PLAN.md — Deterministic 9-bucket category derivation + full-census distribution pin (wave 2)
- [ ] 01-03-PLAN.md — SQLite persistence: locked DDL, WAL, idempotent upsert, snapshot append (wave 2)
- [ ] 01-04-PLAN.md — Census loader + `python -m indexer.refresh` CLI + full-census integration proof (wave 3)

### Phase 2: Scoring Engine
**Goal**: Every indexed agent gets a deterministic, explainable, neutrally-worded 0–100 TrustScore with A–F grade — pure functions with no I/O and no wall clock
**Depends on**: Phase 1
**Requirements**: SCOR-01, SCOR-02, SCOR-03, SCOR-04
**Success Criteria** (what must be TRUE):
  1. Scoring the same agent row with the same category stats and injected `as_of` twice yields byte-identical output: 0–100 integer score, A–F grade, and full component breakdown
  2. All five components (sales volume & velocity, review-count-vs-sales ratio, rating credibility, price-vs-category percentile, listing age/consistency) each return a factual `reason` string; thin data (e.g. 5.0 rating with <5 sales) produces a flagged low-confidence result, never an accusation or a crash
  3. A banned-word test passes over all scoring output: no "fraud", "scam", "fake", "manipulat" anywhere — only neutral wording ("pattern consistent with…", "insufficient data")
  4. `pytest --cov=scoring --cov-fail-under=90` passes, including edge cases: 0 sales, missing rating, "1.55K"-sold parsing
**Plans**: TBD

### Phase 3: MCP Server & Leaderboard
**Goal**: Anyone can call all 4 trust tools over MCP and browse the ranked leaderboard — free and ungated — from a single dockerized port
**Depends on**: Phase 2
**Requirements**: MCPS-01, MCPS-02, MCPS-03, MCPS-04, MCPS-05, WEB-01, WEB-02, WEB-03, OPS-01
**Success Criteria** (what must be TRUE):
  1. MCP Inspector connects, lists exactly 4 tools (`score_agent`, `compare_agents`, `category_leaderboard`, `marketplace_stats`), and successfully calls each; every response is deterministic JSON carrying `generated_at` and `methodology_url`
  2. `score_agent("这个能吃吗？")` and `score_agent("3345")` both return a full JSON score card in <500ms from a warm DB
  3. The page at `/` ranks all indexed agents with TrustScore + grade badges, is sortable with a category filter, loads in <2s, includes an "About the methodology" section and a "TrustLens Verified" badge embed snippet, and regenerates from SQLite on indexer refresh
  4. `docker compose up` serves leaderboard (`/`), the MCP endpoint, and `/healthz` on one port
**Plans**: TBD
**UI hint**: yes

### Phase 4: x402 Payment Layer
**Goal**: Paid tool calls are gated by the x402 v2 standard with a pluggable verifier — the OKX pre-registration check passes against local Docker before any human registers
**Depends on**: Phase 3
**Requirements**: PAYX-01, PAYX-02, PAYX-03
**Success Criteria** (what must be TRUE):
  1. `curl -i -X POST` to the MCP endpoint without payment returns HTTP 402 with x402 v2 payment-requirements JSON (scheme `exact`, network `eip155:196`, `payTo`, atomic-unit string `amount` — "10000" for 0.01 USDT at 6 decimals) and the `PAYMENT-REQUIRED` header
  2. With `X402_MOCK=1`, a mock-paid `tools/call` returns the scored result; `/healthz` and `/` are never gated, and MCP handshake methods follow a configurable `FREE_METHODS` policy
  3. Verification sits behind a pluggable `PaymentVerifier` interface that fails closed when misconfigured, so `okxweb3-app-x402` can drop in at deploy time without touching tools
  4. All payment config comes from environment variables (`TRUSTLENS_PAY_TO`, `TRUSTLENS_PRICE_USDT`, `X_LAYER_RPC`, `X402_MOCK`); no hardcoded keys or addresses; `.env` gitignored; `.env.example` documents every var with placeholders
**Plans**: TBD

### Phase 5: Scraper, Hardening & Submission Kit
**Goal**: The service is submission-ready — refresh path proven with graceful fallback, full test suite green, README and demo materials complete and rehearsed against the container
**Depends on**: Phase 4
**Requirements**: INDX-04, OPS-02, OPS-03, SUBM-01, SUBM-02, SUBM-03
**Success Criteria** (what must be TRUE):
  1. Polite scraper (timeboxed ~2h) fetches okx.ai listing + detail pages at ≤1 req/sec with User-Agent `TrustLens/1.0` and an on-disk cache; every failure path (403, empty SPA shell, markup change) degrades gracefully to the census CSV with a warning — proven by canned-response tests
  2. Full pytest suite passes: scoring functions, MCP tool schemas, and one end-to-end call against a local server with x402 mocked
  3. README covers local run, deploy steps (HTTPS-capable host; HK/Singapore suggestion), MCP Inspector test instructions, the exact OKX ASP registration prompts with remaining manual steps, the pre-registration curl check, and the mock→SDK swap
  4. `submission/` contains demo-script.md (90-second storyboard: problem → live MCP call → score card with anomaly flag → agent-calling-agent flow → leaderboard + on-chain revenue), x-post-draft.md (#OKXAI), and listing-copy.md (name, tagline ≤80 chars, description, category Software Services, 0.01 USDT) — and the demo script has been executed once end-to-end against a clean-clone `docker compose up`
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Data Indexer | 2/4 | In Progress|  |
| 2. Scoring Engine | 0/TBD | Not started | - |
| 3. MCP Server & Leaderboard | 0/TBD | Not started | - |
| 4. x402 Payment Layer | 0/TBD | Not started | - |
| 5. Scraper, Hardening & Submission Kit | 0/TBD | Not started | - |

---
*Roadmap created: 2026-07-10 — 5 phases (coarse granularity), 25/25 v1 requirements mapped*
*Phase 1 planned: 2026-07-10 — 4 plans across 3 waves (02 and 03 parallel)*
