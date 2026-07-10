# Architecture Research

**Domain:** Paid A2MCP data service (MCP server + x402 payments) — indexer → SQLite → deterministic scoring → FastMCP tools + payment middleware + static leaderboard
**Researched:** 2026-07-10
**Confidence:** HIGH (FastMCP composition, x402 wire format from official docs) / MEDIUM (OKX-specific gating granularity — conflicting ecosystem evidence, design made configurable)

## Standard Architecture

### System Overview

Two independent runtimes sharing one SQLite file: an **offline refresh pipeline** (batch, run manually/cron) and an **online read-only server** (uvicorn, one port). The server never scrapes, never scores, never writes — it only reads precomputed rows and serves a pre-built HTML file.

```
OFFLINE (python -m indexer.refresh)                ONLINE (uvicorn server.app:app, one port)
┌─────────────────────────────────┐                ┌──────────────────────────────────────────┐
│  data/census.csv    okx.ai      │                │              FastAPI app                  │
│       │              │ httpx    │                │  ┌────────────────────────────────────┐  │
│       ▼              ▼ 1 req/s  │                │  │  X402 ASGI middleware (outermost)  │  │
│  ┌─────────┐   ┌───────────┐    │                │  │  gates POST /mcp tools/call only   │  │
│  │ census  │   │  scraper  │    │                │  │  → 402 + PAYMENT-REQUIRED header   │  │
│  │ loader  │   │ (+cache,  │    │                │  │  → verify/settle via Verifier ────────┼─▶ payments.verifier
│  └────┬────┘   │ fallback) │    │                │  └───────┬───────────────┬────────────┘  │   (Mock | OKX SDK)
│       │        └─────┬─────┘    │                │          │ free          │ paid          │
│       ▼               ▼         │                │   ┌──────▼─────┐  ┌──────▼──────────┐    │
│  ┌──────────────────────────┐   │                │   │ GET /      │  │ Mount /mcp      │    │
│  │ SQLite: agents, snapshots│   │                │   │ GET /healthz│ │ FastMCP http_app│    │
│  └────────────┬─────────────┘   │                │   │ (FileResp, │  │ 4 tools,        │    │
│               ▼                 │                │   │  meta read)│  │ stateless_http  │    │
│  ┌──────────────────────────┐   │                │   └──────┬─────┘  └──────┬──────────┘    │
│  │ scoring.compute_all      │   │                │          │ read          │ read          │
│  │ (pure fns → scores table)│   │                └──────────┼───────────────┼───────────────┘
│  └────────────┬─────────────┘   │                           ▼               ▼
│               ▼                 │     writes     ┌──────────────────────────────────┐  reads (ro)
│  ┌──────────────────────────┐   │  ─────────────▶│  SQLite (WAL): agents, snapshots,│◀─────────────
│  │ web.build → dist/index.html  │                │  scores, meta  +  web/dist/      │
│  └──────────────────────────┘   │                └──────────────────────────────────┘
└─────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `db/` | Schema DDL, connection helpers, path resolution from env | stdlib `sqlite3`, `schema.sql`, WAL pragma, read-only URI connections for server |
| `indexer/census.py` | Parse census CSV, normalize edge cases ("1.55K" → 1550, "0.0₄15" → 0.000015, missing ratings, multiline taglines, CJK names) | stdlib `csv` + normalizer functions; upsert `agents`, insert `snapshots` |
| `indexer/scraper.py` | Polite refresh from okx.ai agent pages | httpx client, 1 req/s throttle, UA `TrustLens/1.0`, on-disk cache dir, BeautifulSoup; any failure → keep census data (graceful degradation) |
| `indexer/refresh.py` | Pipeline orchestrator, CLI entry (`python -m indexer.refresh [--scrape]`) | argparse; census → (optional) scrape → `scoring.compute_all` → `web.build` → update `meta.last_refresh` |
| `scoring/` | Pure deterministic functions: rows in → `(score 0–100, grade A–F, components[], reasons)` out | No I/O, no `datetime.now()` inside — `as_of` passed in; `persist.py` is the only DB-touching module |
| `web/build.py` | Generate static leaderboard `dist/index.html` at refresh time | stdlib `string.Template` + embedded JSON blob + vanilla JS sort/filter (Jinja2 is NOT in the allowed dep list — do not add it) |
| `server/mcp_tools.py` | FastMCP instance + exactly 4 tools, read-only SELECTs over `scores`/`agents` | `FastMCP("TrustLens")`, tools return dicts; "insufficient data" neutral JSON for unknown agents |
| `server/app.py` | Single-app composition: mount MCP, `/`, `/healthz`, static, add payment middleware, combine lifespans | `create_app()` factory (testable via httpx `ASGITransport`) |
| `payments/protocol.py` | x402 v2 challenge JSON builder + header constants | `x402Version: 2`, `accepts[{scheme:"exact", network:"eip155:196", asset, amount, payTo, maxTimeoutSeconds}]`; base64 for `PAYMENT-REQUIRED` header |
| `payments/verifier.py` | Pluggable `PaymentVerifier` Protocol: `verify()` + `settle()`; `MockVerifier` behind `X402_MOCK=1` | Factory reads env; fail-closed at startup if neither mock nor real verifier configured |
| `payments/middleware.py` | Pure ASGI middleware: inspect POST /mcp bodies, 402-challenge or verify-then-pass | Body buffer + replay pattern (NOT `BaseHTTPMiddleware`) |

## Recommended Project Structure

Top-level packages (required by `python -m indexer.refresh` and the "≥90% coverage on `scoring/`" acceptance criterion — do not nest under a `src/trustlens/` namespace):

```
trustlens/
├── data/
│   ├── okx-marketplace-census-2026-07-10.csv   # repo copy, offline seed
│   └── cache/                    # scraper on-disk cache (gitignored)
├── db/
│   ├── __init__.py               # connect(), connect_ro(), init_db()
│   └── schema.sql                # agents, snapshots, scores, meta
├── indexer/
│   ├── __init__.py
│   ├── census.py                 # CSV parse + value normalizers
│   ├── scraper.py                # httpx + BS4, throttle, cache, fallback
│   └── refresh.py                # python -m indexer.refresh entrypoint
├── scoring/
│   ├── __init__.py
│   ├── components.py             # one pure fn per component → (points, max, reason)
│   ├── engine.py                 # score_agent(record, category_stats, as_of) → ScoreResult; grade map
│   └── persist.py                # compute_all(conn): read snapshots → write scores (one transaction)
├── web/
│   ├── __init__.py
│   ├── build.py                  # scores → dist/index.html (stdlib templating)
│   ├── template.html             # string.Template source w/ methodology + badge snippet
│   └── dist/                     # build output (gitignored or committed for demo safety)
├── server/
│   ├── __init__.py
│   ├── settings.py               # env: TRUSTLENS_PAY_TO, TRUSTLENS_PRICE_USDT, X_LAYER_RPC, X402_MOCK, DB path
│   ├── mcp_tools.py              # FastMCP + score_agent, compare_agents, category_leaderboard, marketplace_stats
│   └── app.py                    # create_app(): composition root
├── payments/
│   ├── __init__.py
│   ├── protocol.py               # challenge builder, header names, atomic-unit conversion
│   ├── verifier.py               # PaymentVerifier Protocol, MockVerifier, factory
│   └── middleware.py             # X402Middleware (pure ASGI)
├── tests/
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

### Structure Rationale

- **`indexer/`, `scoring/`, `web/` never import `server/` or `payments/`** — the offline pipeline runs without the web stack installed conceptually; keeps the dependency graph acyclic: `refresh.py` imports `scoring.persist` and `web.build`; nothing imports `indexer` back.
- **`scoring/components.py` + `engine.py` take plain dataclasses/dicts, not connections** — this is what makes the 90% coverage target cheap: table-driven pytest over pure functions, no fixtures/DB.
- **`payments/` knows nothing about MCP tools** — it sees HTTP scope + JSON-RPC method names only. Swapping in OKX's `x402ResourceServer(facilitator)` middleware at deploy time replaces this package at the same layer (app-level middleware), which is exactly how the OKX SDK is documented to install.
- **`server/app.py` is the only composition root** — everything else is importable in isolation for tests.

## Architectural Patterns

### Pattern 1: Mount FastMCP's ASGI app inside FastAPI with combined lifespans

**What:** FastMCP (v3.x current) exposes `mcp.http_app()` — a Starlette app you mount into FastAPI. The parent app MUST receive the MCP app's lifespan or the StreamableHTTP session manager never initializes (runtime 500s).
**When to use:** Always for this project — it is the documented integration and satisfies "one port serves MCP + leaderboard + healthz".
**Trade-offs:** One process, one deploy; MCP path fixed at compose time.

```python
# server/app.py — verified against FastMCP v3 docs (gofastmcp.com/integrations/fastapi)
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastmcp.utilities.lifespan import combine_lifespans
from server.mcp_tools import mcp
from payments.middleware import X402Middleware

def create_app() -> FastAPI:
    # stateless_http: every request is independent — right fit for pay-per-call,
    # enables `uvicorn --workers N` later without session affinity
    mcp_app = mcp.http_app(path="/", stateless_http=True)

    @asynccontextmanager
    async def app_lifespan(app):
        # startup checks: DB exists, scores populated, verifier configured (fail closed)
        yield

    app = FastAPI(lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan))
    app.add_middleware(X402Middleware)          # wraps EVERYTHING incl. the mount

    @app.get("/healthz")
    def healthz(): ...                          # free: reads meta table

    @app.get("/")
    def leaderboard(): return FileResponse("web/dist/index.html")  # free: pre-built

    app.mount("/mcp", mcp_app)                  # MCP endpoint at POST /mcp
    return app

app = create_app()
```

Key facts (HIGH confidence, official docs): `http_app(path="/")` mounted at `/mcp` yields endpoint `/mcp`; missing lifespan = "session manager won't initialize"; `combine_lifespans` lives at `fastmcp.utilities.lifespan`; `stateless_http=True` is the documented multi-worker/scale mode. Pin `fastmcp>=3` and follow v3 docs — v2-era snippets online differ.

### Pattern 2: Payment gate as pure ASGI middleware with JSON-RPC body inspection

**What:** Starlette middleware added via `add_middleware` wraps mounted sub-apps too, so one app-level middleware can gate `/mcp` while `/` and `/healthz` pass untouched (path check first). For `/mcp` POSTs it buffers the body, inspects the JSON-RPC `method`, and decides: free-pass, 402-challenge, or verify-and-serve.

**Gating decision (the contested part — made configurable):**

| Request to POST /mcp | Treatment | Rationale |
|---|---|---|
| `initialize`, `notifications/*`, `ping`, `tools/list` | FREE (configurable `FREE_METHODS` set) | Official x402 MCP guide gates only tool execution; clients/marketplace must be able to handshake and discover tools |
| `tools/call` (any of the 4 tools) | PAID — no `PAYMENT-SIGNATURE` header → 402; valid → verify+settle → serve | The product: 0.01 USDT/call |
| Empty or unparseable body (bare `curl -i -X POST /mcp`) | 402 + `PAYMENT-REQUIRED` header | Satisfies OKX pre-registration check verbatim |
| GET/DELETE /mcp (SSE open / session close) | FREE | Transport plumbing, not a tool call |

Evidence conflict, flagged honestly: the official x402 MCP guide (docs.x402.org) gates only tool execution, but at least one live OKX A2MCP service (Mario Intelligence Suite on Glama) 402-gates the entire `/mcp` endpoint including `tools/list`. Both pass the OKX curl check. Ship the free-handshake version (better for discovery), keep `FREE_METHODS` a one-line config so flipping to gate-everything during OKX review costs minutes. The real OKX SDK middleware's behavior wins at deploy time anyway.

**Trade-offs:** Body inspection requires the buffer-and-replay pattern; JSON-RPC batch arrays (removed in MCP spec 2025-06-18) should just be treated as paid/rejected.

```python
# payments/middleware.py — pure ASGI (NOT BaseHTTPMiddleware; see anti-patterns)
class X402Middleware:
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/mcp") \
           or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        body = await _drain(receive)                      # buffer full body
        method = _jsonrpc_method(body)                    # None if unparseable
        if method in FREE_METHODS:
            return await self.app(scope, _replay(body), send)
        sig = _header(scope, b"payment-signature")
        if sig is None or not await self.verifier.verify(sig, requirements):
            return await _send_402(send, challenge_b64)   # body JSON + PAYMENT-REQUIRED header
        await self.verifier.settle(sig, requirements)     # settle BEFORE serving (per requirement)
        return await self.app(scope, _replay(body), send) # optionally append PAYMENT-RESPONSE header
```

### Pattern 3: Pluggable verifier behind a Protocol (mock now, OKX facilitator later)

**What:** x402 resource servers delegate `verify` (is this signed payment valid for these requirements?) and `settle` (execute it) to a facilitator. Define that seam as a 2-method Protocol; `X402_MOCK=1` selects `MockVerifier` (accepts well-formed payloads, logs, no chain interaction); the deploy-time drop-in wraps `okxweb3-app-x402`'s facilitator client (needs `OKX_API_KEY`/`OKX_SECRET_KEY`/`OKX_PASSPHRASE` — human-review stop condition, correctly out of v1 code).
**When to use:** Any time a paid dependency is credential-gated during development. This mirrors the ecosystem exactly — the Mario A2MCP service ships the same `mock-x402` / `okx-x402` mode switch.
**Trade-offs:** Mock can't catch facilitator-API mismatches; mitigate by matching the documented wire format byte-for-byte (challenge JSON fields from PROJECT.md) and by failing closed: if `X402_MOCK != 1` and no SDK creds, `create_app()` raises at startup rather than serving unpaid.

```python
# payments/verifier.py
class PaymentVerifier(Protocol):
    async def verify(self, payment_b64: str, requirements: dict) -> bool: ...
    async def settle(self, payment_b64: str, requirements: dict) -> dict: ...
```

**Wire format anchors (from PROJECT.md / OKX docs, cross-checked):** 402 body carries `x402Version: 2`, `resource{url,description,mimeType}`, `accepts:[{scheme:"exact", network:"eip155:196" (testnet "eip155:1952"), asset:"0x779d…3736", amount:"<atomic units>", payTo, maxTimeoutSeconds:300}]`; challenge duplicated base64 in `PAYMENT-REQUIRED` response header; payment proof arrives in `PAYMENT-SIGNATURE` request header (per x402 v2 docs). USDT on X Layer uses **6 decimals** → 0.01 USDT = `"10000"` atomic units; keep amounts as strings, convert from `TRUSTLENS_PRICE_USDT` in one place (`protocol.py`).

### Pattern 4: Precompute scores at refresh; serve reads only (chosen over compute-on-request)

**What:** `indexer.refresh` ends by calling `scoring.compute_all()` (writes `scores` table) and `web.build()` (writes `dist/index.html`). MCP tools and the leaderboard only ever read.
**Why precompute wins here:**
- **Latency:** `score_agent` = one indexed SELECT over 272 rows ≈ sub-millisecond warm — the <500ms budget becomes independent of scoring complexity. Leaderboard = static file read — <2s trivially met.
- **Consistency:** leaderboard, `score_agent`, and `compare_agents` all serve the same numbers from the same computation run; no drift from recomputing category percentiles per request.
- **Determinism/auditability:** score row records `computed_at`, `methodology_version`, and source `snapshot_id` — the paid answer is reproducible evidence, which is the product's pitch.
- Compute-on-request would still be fast at n=272, but buys nothing and forces category-percentile aggregation per call plus clock-dependency risks.
**Trade-offs:** Scores are as fresh as the last refresh — fine; the data source itself is scrape/CSV-refresh cadence. `/healthz` should expose `last_refresh` so staleness is observable.

### Pattern 5: SQLite WAL + read-only server connections

**What:** `PRAGMA journal_mode=WAL` at init; the server opens per-request read-only connections (`sqlite3.connect("file:…/trustlens.db?mode=ro", uri=True)`); the indexer (separate process) writes in transactions.
**Why:** WAL lets `python -m indexer.refresh` run while the server serves without `database is locked` errors; read-only mode makes "server never mutates" structural; per-request connections on a 272-row DB cost microseconds — no pooling, no `check_same_thread` juggling.

## Data Flow

### Refresh flow (offline; run before demo / via cron)

```
data/census.csv ──► indexer.census ──► agents + snapshots ─┐
okx.ai pages ─────► indexer.scraper ─► snapshots (source=scrape, cache-backed,
                     (only with --scrape)                   falls back to census)
                                                            ▼
                                            scoring.compute_all (pure fns + category stats)
                                                            ▼
                                                      scores table
                                                    ┌───────┴────────┐
                                                    ▼                ▼
                                          web.build → dist/index.html   meta.last_refresh
```

### Paid request flow (online)

```
Agent/client POST /mcp {"method":"tools/call","params":{"name":"score_agent",…}}
    ▼
X402Middleware: path=/mcp, POST, method=tools/call → paid
    ├─ no/invalid PAYMENT-SIGNATURE → 402 {x402Version:2, accepts:[…]} + PAYMENT-REQUIRED hdr ──► client pays, retries
    └─ valid → verifier.verify → verifier.settle → replay body downstream
            ▼
FastMCP router → tool fn → SELECT scores JOIN agents (read-only conn)
            ▼
JSON result {trust_score, grade, components[{name,points,reason}], computed_at} (+ PAYMENT-RESPONSE hdr)
```

### Free request flows

```
GET /        → FileResponse(web/dist/index.html)          (pre-built at refresh)
GET /healthz → meta read → {status, agents:272, last_refresh, mock_mode}
POST /mcp {"method":"initialize"|"tools/list"} → FastMCP   (free handshake/discovery)
```

## Suggested Build Order

Dependency graph (arrows = "needed by"):

```
db/schema ──► indexer.census ──► snapshots data ──► scoring.persist ──► scores ──► web.build
   │                                                    ▲                  │          │
   │          scoring.components/engine (PURE — no deps, build anytime) ───┘          │
   │                                                                       ▼          ▼
   └────────────────────────────────────► server.mcp_tools ──► server.app (mount+lifespan+static)
                                                                     ▲
                                          payments.protocol/verifier/middleware (wraps app LAST)
indexer.scraper (enhances snapshots; census path already works) ──► re-run refresh
Dockerfile/compose/README ──► after app works end-to-end
```

Recommended sequence (each step leaves a demoable state):

1. **`db/` + `indexer/census.py` + `refresh.py` skeleton** — `python -m indexer.refresh` populates 272 agents from CSV. Everything downstream needs this data. (CSV normalizers are the risk pocket: "1.55K", subscript-zero prices, missing ratings.)
2. **`scoring/`** — pure components + engine + tests to ≥90%, then `persist.py` writes `scores`. Can start in parallel with step 1 since the engine takes plain records.
3. **`server/mcp_tools.py` + `server/app.py` + `web/build.py`** — full service working FREE: 4 tools callable (test with FastMCP's in-memory `Client(mcp)`), leaderboard at `/`, `/healthz`. De-risks the FastMCP mount/lifespan integration before money enters.
4. **`payments/`** — protocol builder, `MockVerifier`, middleware; e2e via httpx `ASGITransport`: bare POST /mcp → 402 + `PAYMENT-REQUIRED`; `tools/list` free; paid `tools/call` succeeds under `X402_MOCK=1`. Gating a *working* service is far easier to debug than co-developing tools and payment.
5. **`indexer/scraper.py`** — polite refresh path (throttle, cache, fallback). Sequenced after the money path because census data alone yields a working demo, and live-site markup is the least controllable dependency. **Exception — see open question below: if categories only exist on agent detail pages, pull the scraper (or a category-derivation fallback) into step 1.**
6. **Ops + submission kit** — Dockerfile, compose, `.env.example`, README (ASP registration steps), demo script.

**Open question feeding the roadmap:** the census CSV columns (id, name, tagline, rating, positive %, units sold, price) contain **no category field**, yet `category_leaderboard` and the price-vs-category scoring component require one. Resolve in phase 1: (a) scrape category from `okx.ai/agents/<id>` pages, or (b) derive deterministic buckets (e.g., tagline keywords or price bands) with the method disclosed on the methodology page. Decide before scoring is finalized — it changes `CategoryStats`.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Hackathon demo → early paid traffic | None. Single uvicorn worker serves read-only sub-ms queries; WAL handles refresh-while-serving. |
| Hundreds of req/s | `uvicorn --workers N` — already safe because `stateless_http=True` and server is read-only. |
| Real settlement enabled | First real bottleneck: facilitator verify/settle network round-trip per paid call (not the DB). Keep verifier calls async; consider verify-then-serve with async settle only if OKX flow permits. |

### Scaling Priorities

1. **First bottleneck:** verifier round-trip latency once `X402_MOCK=0` — measure; it dominates the 500ms budget, not scoring.
2. **Second bottleneck:** scraper freshness cadence (politeness-capped at 272 req ≈ 5 min/full pass) — irrelevant at this catalog size.

## Anti-Patterns

### Anti-Pattern 1: 402-gating the entire /mcp path including `initialize`

**What people do:** Slap the payment check on every POST to /mcp.
**Why it's wrong:** x402-unaware-but-MCP-aware clients (and possibly marketplace introspection) can't even handshake or list tools; per official x402 MCP guidance the gate belongs on tool execution.
**Do this instead:** `FREE_METHODS` allowlist + always-402 for bodyless/unparseable POSTs (keeps the OKX `curl -i -X POST` pre-registration check green). Keep it configurable — one live OKX A2MCP service does gate everything, so review feedback may force the flip.

### Anti-Pattern 2: Reading the request body in `BaseHTTPMiddleware`

**What people do:** `await request.body()` inside `BaseHTTPMiddleware.dispatch` then call `call_next`.
**Why it's wrong:** Known Starlette footgun — consumed stream hangs or double-reads, and BaseHTTPMiddleware breaks streaming responses (MCP uses SSE-capable responses).
**Do this instead:** Pure ASGI middleware: drain `receive` into a buffer, inspect, pass a replaying `receive` downstream.

### Anti-Pattern 3: Forgetting the FastMCP lifespan on the parent app

**What people do:** `app.mount("/mcp", mcp.http_app())` on a plain `FastAPI()`.
**Why it's wrong:** Documented failure — the StreamableHTTP session manager task group never starts; every MCP request 500s.
**Do this instead:** `FastAPI(lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan))`.

### Anti-Pattern 4: Impure scoring (I/O or wall-clock inside score functions)

**What people do:** Score functions query SQLite or call `datetime.now()` for age/velocity.
**Why it's wrong:** Kills determinism (same input → different score by the hour), makes the 90% coverage target expensive, and drifts tool responses from the leaderboard.
**Do this instead:** `score_agent(record, category_stats, as_of)` — all inputs explicit; only `persist.py` touches the DB; `as_of` = refresh timestamp stored with the score.

### Anti-Pattern 5: Scraping or scoring at request time

**What people do:** Tool call triggers a live fetch of the agent page "for freshness".
**Why it's wrong:** Blows the 500ms budget, violates the 1 req/s politeness constraint under load, and makes paid answers nondeterministic.
**Do this instead:** Refresh pipeline is the only writer; serve precomputed rows; expose `last_refresh` in `/healthz` and tool payloads.

### Anti-Pattern 6: Float arithmetic for payment amounts

**What people do:** `amount = 0.01 * 10**6` and pass floats around.
**Why it's wrong:** x402 `amount` is a string of atomic units; USDT on X Layer has 6 decimals (verified against a live A2MCP service that reads decimals explicitly); float rounding produces challenge/verify mismatches.
**Do this instead:** Convert `TRUSTLENS_PRICE_USDT` → atomic-unit string once in `payments/protocol.py` using `decimal.Decimal`; treat decimals as explicit config.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| okx.ai agent pages | httpx GET, 1 req/s, UA `TrustLens/1.0`, on-disk cache, BS4 parse | Fail soft to census data; markup drift is expected — wrap selectors, log misses |
| OKX x402 facilitator (`okxweb3-app-x402`) | Deploy-time swap behind `PaymentVerifier` Protocol; SDK's `x402ResourceServer(facilitator)` middleware replaces `payments/` at the same app-middleware layer | Needs OKX API creds (stop condition) — v1 ships `MockVerifier`; README documents the swap |
| X Layer (eip155:196 / testnet 1952) | Never touched directly in v1 — only via facilitator | Asset `0x779d…3736` (USDT), 6 decimals |
| OKX ASP pre-registration check | `curl -i -X POST https://domain/mcp` must return 402 + `PAYMENT-REQUIRED` | Middleware's "unparseable body → 402" rule satisfies this by construction; add an e2e test for exactly this curl |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| indexer ↔ scoring | Direct import: `refresh.py` calls `scoring.persist.compute_all(conn)` | scoring never imports indexer |
| indexer/scoring ↔ server | **SQLite file only** (no imports) — writer/reader split, WAL mode | Server connections read-only URI |
| server ↔ payments | ASGI middleware wrap in `create_app()`; payments sees HTTP scope + JSON-RPC method names, never tool internals | Mirrors OKX SDK install point |
| server ↔ web | Filesystem: serve `web/dist/index.html` via FileResponse | Startup check warns if missing; refresh rebuilds |
| tests ↔ everything | scoring: pure unit; tools: FastMCP in-memory `Client(mcp)` (bypasses HTTP/payment); e2e: httpx `ASGITransport` against `create_app()` with `X402_MOCK=1` | Three test layers map 1:1 to the three boundaries |

## Sources

- FastMCP v3 official docs — FastAPI mounting, lifespan requirement, `combine_lifespans`, `stateless_http` (Context7 `/prefecthq/fastmcp`, gofastmcp.com/integrations/fastapi, /deployment/http) — HIGH
- [x402 official guide: MCP Server with x402](https://docs.x402.org/guides/mcp-server-with-x402) — tool-execution-level gating, `PAYMENT-REQUIRED` (base64 challenge) + `PAYMENT-SIGNATURE` headers, verify/retry flow — HIGH
- [Mario A2MCP Intelligence Suite (live OKX A2MCP service, Glama listing)](https://glama.ai/mcp/servers/agent-evidence-lab/a2mcp-signal-snapshot) — real-world reference: gates entire /mcp incl. `tools/list`, `mock-x402`/`okx-x402` mode switch, `eip155:196`, USDT 6 decimals, Docker+reverse-proxy deploy — MEDIUM (single source)
- PROJECT.md (OKX docs fetched 2026-07-10) — x402 v2 challenge JSON fields, `PAYMENT-REQUIRED` header, testnet `eip155:1952`, pre-registration curl check, `okxweb3-app-x402` middleware shape — HIGH (project's authoritative capture)
- Supporting ecosystem reads: [Zuplo on MCP x402 payments](https://zuplo.com/blog/mcp-api-payments-with-x402), [pay-per-call MCP tutorial](https://dev.to/kirothebot/how-to-build-a-pay-per-call-mcp-server-with-x402-and-usdc-58gk), [Simplescraper x402 guide](https://simplescraper.io/blog/x402-payment-protocol) — LOW/context only
- SQLite WAL + read-only URI, Starlette pure-ASGI middleware body replay — standard documented behavior (training knowledge, uncontroversial) — MEDIUM

---
*Architecture research for: TrustLens — paid A2MCP (MCP + x402) trust-score service*
*Researched: 2026-07-10*
