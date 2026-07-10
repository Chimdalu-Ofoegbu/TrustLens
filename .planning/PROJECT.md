# TrustLens

## What This Is

TrustLens is a pay-per-call Agent-to-MCP (A2MCP) service for the OKX.AI marketplace that returns a trust score for any listed OKX.AI agent — so humans and other agents can check "should I hire this agent?" before paying. It is an OKX AI Genesis Hackathon entry: a standard MCP server over HTTPS whose endpoints implement the x402 payment standard, priced at 0.01 USDT/call, settling in USDT/USDG on X Layer.

## Core Value

Any human or agent can get a deterministic, evidence-based answer to "should I hire this OKX.AI agent?" in one paid MCP call.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Indexer populates SQLite from the census CSV offline, and can politely re-scrape okx.ai (1 req/s, cached, graceful fallback)
- [ ] Deterministic scoring engine: 0–100 TrustScore + A–F grade + component breakdown with neutral factual reason strings
- [ ] MCP server exposing exactly 4 tools (score_agent, compare_agents, category_leaderboard, marketplace_stats) + /healthz
- [ ] x402 payment layer: 402 challenge with payment requirements, verified settlement before serving; X402_MOCK=1 test mode
- [ ] Static leaderboard site at / with sortable ranked table, category filter, methodology section, badge embed snippet
- [ ] pytest suite: ≥90% coverage on scoring/, MCP tool schemas, e2e with x402 mocked
- [ ] Ops files: Dockerfile, docker-compose.yml, .env.example, README with deploy + ASP registration steps
- [ ] Submission kit: demo-script.md, x-post-draft.md, listing-copy.md

### Out of Scope

- Auth systems, user accounts, admin panels, dark mode — explicitly excluded by the brief ("only build what is specified")
- Databases beyond SQLite — brief constraint; SQLite is sufficient for 272 agents
- Real-fund settlement in v1 code — OKX Payment SDK (`okxweb3-app-x402`) requires OKX API credentials tied to a wallet (human-review stop condition); v1 implements the documented x402 v2 wire flow natively with a mock verifier and documents the SDK drop-in as a deploy-time step
- Accusatory language anywhere — all outward text uses neutral analytics wording ("pattern consistent with…", "insufficient data"), never "fraud"/"scam"/"fake"
- Deploying, wallet operations, ASP submission, public posts, hackathon form — human-only steps; the build prepares materials

## Context

- Platform: OKX.AI lists ~272 agents. A2MCP services are MCP servers over HTTPS implementing x402 (HTTP 402 payment-request flow) with the OKX Payment SDK, settling in USDT/USDG on X Layer (zero gas).
- Seed data: `data/okx-marketplace-census-2026-07-10.csv` (copied from read-only original in parent folder) — 272 agents: id, name, tagline, rating, positive %, units sold, price. Known edge cases: "1.55K sold", subscript-zero prices like "0.0₄15 USDT", missing ratings (rating column may hold a price-like value with empty positive %), multiline quoted taglines, CJK names (agent 3345 "这个能吃吗？"). Agent detail pages: `https://www.okx.ai/agents/<id>`. No saved marketplace HTML exists in the project folder — the CSV is the offline seed; the scraper is the refresh path.
- From OKX docs (fetched 2026-07-10):
  - x402 v2 challenge JSON: `x402Version: 2`, `resource {url, description, mimeType}`, `accepts: [{scheme: "exact", network: "eip155:196", asset: "0x779ded0c9e1022225f8e0630b35a9b54be713736", amount: "<atomic units>", payTo: "0x<wallet>", maxTimeoutSeconds: 300}]`; 402 responses carry a `PAYMENT-REQUIRED` header. Testnet network: `eip155:1952`. Pre-registration check: `curl -i -X POST https://domain/path` → expect 402 + header.
  - Python SDK: `pip install okxweb3-app-x402` — `x402ResourceServer(facilitator)` middleware; facilitator client needs `OKX_API_KEY`, `OKX_SECRET_KEY`, `OKX_PASSPHRASE`.
  - ASP registration (README must quote): install Onchain OS (`npx skills add okx/onchainos-skills --yes -g`), log in to Agentic Wallet, send agent prompt **"Help me register an A2MCP ASP on OKX.AI using Onchain OS"** (fields: service name, description, price per call, endpoint URL), then **"Help me list my ASP on OKX.AI using Onchain OS"**; review completes within 24h to the registered wallet email.
  - Server location suggestions: Hong Kong / Singapore nodes; public HTTPS endpoint with domain required.
- Differentiation (bake into copy and scoring design): Factor Credit Desk/Bureau score agent creditworthiness for lending; TO1 Intelligence sells raw wash-trade/uptime data feeds; Internet Court MCP does dispute arbitration. TrustLens is a **marketplace hiring-trust score** — review authenticity, rating-vs-sales anomalies, sales velocity, price fairness vs category — one deterministic JSON verdict per call.
- Pricing: marketplace revenue leaders are agent-callable data APIs at $0.001–$0.01/call returning deterministic JSON → TrustLens at **0.01 USDT/call**.

## Constraints

- **Timeline**: Submit for OKX marketplace review July 10–11, 2026; live before **July 17, 2026 23:59 UTC** — bias every decision toward shipping a working v1 fast
- **Tech stack**: Python 3.11+, FastAPI, FastMCP, SQLite (stdlib `sqlite3` or SQLAlchemy), httpx, BeautifulSoup; uvicorn as the ASGI server for FastAPI; pytest (+coverage) as dev/test tooling. **No other runtime dependencies without asking the user**
- **Scope discipline**: Only build what the brief specifies — no auth, accounts, extra databases, admin panels, dark mode
- **Scraping politeness**: ≤1 req/sec, User-Agent `TrustLens/1.0`, on-disk cache, graceful degradation to census CSV if blocked or markup changes
- **Secrets**: environment variables only (`TRUSTLENS_PAY_TO`, `TRUSTLENS_PRICE_USDT`, `X_LAYER_RPC`, `X402_MOCK`); `.env` gitignored; `.env.example` documents every var with placeholders; never hardcode keys or addresses
- **Language**: all outward-facing text is neutral, factual, methodology-linked — never allegations against named agents
- **Workspace**: work only inside `trustlens/`; census CSV original, research report, and prompt file in the parent folder are read-only inputs
- **Git**: commits authored solely by the user's identity; no AI attribution of any kind in any commit or PR
- **Stop conditions (require human review)**: remote deploys/domain purchase; real wallets/funds/keys/OKX Agentic Wallet login; submitting the ASP listing, posting publicly, or the hackathon Google Form; adding unlisted dependencies; deleting any file; OKX SDK contradicting x402 assumptions; any error unresolved after 2 attempts

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Price at 0.01 USDT/call | Marketplace revenue leaders are $0.001–$0.01/call deterministic-JSON APIs | — Pending |
| Implement x402 v2 flow natively + `X402_MOCK` verifier; document `okxweb3-app-x402` as deploy-time drop-in | Real SDK needs OKX API creds (wallet-tied = stop condition); native 402 challenge satisfies acceptance criteria without unlisted deps | — Pending |
| Single FastAPI app serves MCP endpoint, leaderboard, and /healthz on one port | `docker compose up` must serve everything on one port | — Pending |
| Census CSV copied into repo `data/` | Offline seeding + Docker builds without touching read-only original | — Pending |
| Fixed scoring components: sales volume/velocity, review-vs-sales ratio, rating credibility, price-vs-category percentile, listing age/consistency | Prescribed by brief; deterministic and explainable, each with a neutral `reason` string | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-10 after initialization*
