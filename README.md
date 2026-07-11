# TrustLens

TrustLens is a pay-per-call Agent-to-MCP (A2MCP) service for the OKX.AI marketplace. Any human or agent can get a deterministic, evidence-based answer to "should I hire this OKX.AI agent?" in one paid MCP call. It is a standard MCP server over HTTPS whose endpoints implement the x402 payment standard, priced at 0.01 USDT/call, settling in USDT/USDG on X Layer.

TrustLens computes a marketplace **hiring-trust** score — review authenticity, rating-vs-sales anomalies, sales velocity, and price fairness versus category — returning one deterministic JSON verdict per call (a 0–100 TrustScore, an A–F grade, a confidence level, and a factual per-component breakdown). This is distinct from creditworthiness scoring (Factor), raw data feeds (TO1), and dispute arbitration (Internet Court). Every reason string is neutral and factual; the [methodology](/#methodology) page documents exactly how each score is derived.

### The 4 MCP tools

- `score_agent(agent_id_or_name)` — the full trust card for one agent: TrustScore, grade, confidence, and each component's neutral reason string.
- `compare_agents(ids)` — score several agents side by side in one call.
- `category_leaderboard(category, limit=10)` — the ranked table for one marketplace category.
- `marketplace_stats()` — aggregate distribution stats across the indexed marketplace.

## Local run

```bash
pip install -e .[dev]
python -m indexer.refresh
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

`pip install -e .[dev]` installs the runtime deps plus the test tooling. `python -m indexer.refresh` seeds the SQLite store and builds the leaderboard from the bundled census CSV offline (prints `272 agents, 272 snapshots, source=census`). `uvicorn server.main:app` serves everything on one port — `server/main.py` exposes `app = create_app()`.

Endpoints:

- `/` — the ranked leaderboard site.
- `/healthz` — health check.
- `/mcp` — the MCP (Streamable HTTP) endpoint.

## Tests & coverage gate

```bash
python -m pytest
```

The full suite runs green (314 passing) with a ≥90% coverage gate scoped to `scoring/` (currently 100%).

**Footgun:** the coverage gate (`--cov=scoring`) always applies, so any *subset* run that skips the scoring tests reports 0% and fails the gate. Run partial selections with `--no-cov`. For example, the scraper's offline canned-response tests:

```bash
python -m pytest tests/test_scraper.py --no-cov
```

## Docker

```bash
docker compose up
```

One service, one port (`8000:8000`); the `.env` file is optional (`required: false`). On first start the container entrypoint self-seeds **both** the DB and the leaderboard from the committed census CSV (`[ -f data/trustlens.db ] && [ -f web/dist/index.html ] || python -m indexer.refresh`) — offline, reproducible, and it completes in seconds before uvicorn starts.

**HUMAN-ONLY: requires the Docker Desktop engine running.** This is a carried Phase-3/4 environment blocker — the engine would not start in the build environment and `docker info` fails when it is down. The identical app is proven in-process and against a live uvicorn, so this step is a container smoke test that folds into the final human checklist.

## Optional: refresh from okx.ai (`--scrape`)

```bash
python -m indexer.refresh --scrape
```

By default `refresh` is offline and CSV-only. Passing `--scrape` adds a polite enrichment pass against okx.ai (≤1 req/s, User-Agent `TrustLens/1.0`, responses cached under `data/cache/`) that refreshes sales, rating, price, and positive-percentage fields for agents already in the census. Every failure path — a non-200 response, a timeout, missing or changed page markup, or an unparseable payload — logs a warning and falls back to the census CSV, so the refresh exit-code contract is never affected by network state. The census rows always stand when a scrape yields nothing usable.

## MCP Inspector

List the tools (expects exactly 4, each with an `outputSchema`):

```bash
npx --yes @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/list
```

Call `score_agent` with a CJK agent name:

```bash
npx --yes @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/call --tool-name score_agent --tool-arg 'agent_id_or_name=这个能吃吗？'
```

This returns agent 3345 / grade A / TrustScore 94. The name resolves via an NFKC `name_key`, so `agent_id_or_name="3345"` and the ASCII-`?` variant `这个能吃吗?` resolve to the same card.

More examples:

```bash
npx --yes @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/call --tool-name compare_agents --tool-arg 'ids=["3345","2662"]'
npx --yes @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/call --tool-name category_leaderboard --tool-arg 'category=Trading & DeFi' --tool-arg 'limit=5'
npx --yes @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/call --tool-name marketplace_stats
```

## x402 pre-registration check

Before registering the ASP, confirm the endpoint issues the payment challenge:

```bash
curl -i -X POST https://<host>/mcp
```

Expected: `HTTP/1.1 402 Payment Required` with an uppercase `PAYMENT-REQUIRED` header that base64-decodes to the payment-requirements JSON (scheme `exact`, network `eip155:196`, amount `"10000"` = 0.01 USDT at 6 decimals). `POST /mcp/` returns a byte-identical 402.

Not gated: `/healthz`, `/`, `/badge/*`, and the MCP handshake methods (`initialize`, `tools/list`) all respond normally without payment.

## Configuration (env vars)

Copy `.env.example` to `.env` and fill in values. All five variables:

| Var | Purpose | Placeholder |
| --- | --- | --- |
| `TRUSTLENS_PAY_TO` | wallet receiving 0.01 USDT/call | `0x0000...0000` |
| `TRUSTLENS_PRICE_USDT` | price in human USDT (→ atomic `"10000"`) | `0.01` |
| `X_LAYER_RPC` | X Layer RPC (SDK swap only) | `https://rpc.xlayer.tech` |
| `X402_MOCK` | EXACTLY `1` = mock; anything else = fail-closed 402 | (empty) |
| `TRUSTLENS_BASE_URL` | public base advertised in requirements + methodology | `http://localhost:8000` |

**Never commit real values; `.env` is gitignored.** Use placeholder addresses in any shared example.

## Mock → real payment SDK

In development, set `X402_MOCK=1` to use `MockVerifier` (it accepts any non-empty `PAYMENT-SIGNATURE` and returns a mock receipt). At deploy time, drop the OKX Payment SDK `okxweb3-app-x402` in at the `make_verifier` / `PaymentVerifier` seam in `server/payments.py` — `UnconfiguredVerifier` (the fail-closed production default, which 402s every paid request) is the exact swap point. The real facilitator credentials (`OKX_API_KEY`, `OKX_SECRET_KEY`, `OKX_PASSPHRASE`) are a **HUMAN-ONLY stop condition** — they are tied to a wallet and are never committed or set by the build.

## Deploy

Deploy to any HTTPS-capable host; a public HTTPS domain is required. OKX suggests Hong Kong / Singapore nodes. **HUMAN-ONLY** — remote deploy and domain purchase are stop conditions handled by a human operator.

## Register on OKX.AI (ASP)

Registration and listing are completed through the OKX Onchain OS agent. Quote the two prompts below exactly.

1. Install Onchain OS:

   ```bash
   npx skills add okx/onchainos-skills --yes -g
   ```

2. Log into the OKX Agentic Wallet. **[HUMAN-ONLY]**

3. Send agent prompt 1 (VERBATIM):

   ```text
   Help me register an A2MCP ASP on OKX.AI using Onchain OS
   ```

   Fields it asks for: service name, description, price per call, endpoint URL.

4. Send agent prompt 2 (VERBATIM):

   ```text
   Help me list my ASP on OKX.AI using Onchain OS
   ```

5. Review completes within 24h to the registered wallet email. **[HUMAN-ONLY]**

**HUMAN-ONLY stop conditions:** deploy, wallet login, ASP registration submission, ASP listing submission, and real OKX credentials are all human-only steps — the build prepares the materials and stops here.
