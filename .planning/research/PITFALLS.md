# Pitfalls Research

**Domain:** Paid MCP (A2MCP + x402) data service — FastMCP + FastAPI + SQLite, hackathon deadline
**Researched:** 2026-07-10
**Confidence:** HIGH overall (FastMCP, x402 v2 spec, SQLite, pytest, Docker verified against official docs/issues; OKX-specific wire details MEDIUM — verify against OKX docs at build time; okx.ai scraping behavior MEDIUM — 403 observed, SPA rendering inferred)

## Critical Pitfalls

### Pitfall 1: FastMCP version drift — writing v2 (or v1) code against a v3.x install

**What goes wrong:**
`pip install fastmcp` today installs **v3.2.x**, but most tutorials, blog posts, and LLM training data show v2 patterns — and some show FastMCP 1.0, which lives inside the official SDK as `from mcp.server.fastmcp import FastMCP` (a different, less-featured class). v3 removed transport kwargs from the constructor (`FastMCP(host=..., port=..., stateless_http=...)` → now passed to `run()` / `http_app()`), renamed `get_tools()` → `list_tools()` (returns a list, not a dict), and changed decorator behavior. Real-world breakage from unpinned fastmcp is documented (e.g., awslabs/mcp#2533: every version of their server broke when fastmcp 3.x shipped). Mixing `mcp` SDK imports with `fastmcp` package imports produces subtly different behavior (python-sdk#1276).

**Why it happens:**
Three coexisting things are all called "FastMCP" (v1 in the official `mcp` SDK, v2 standalone, v3 standalone current). Code written from memory or copied from a 2025 tutorial targets the wrong one.

**How to avoid:**
- Pin explicitly in requirements: `fastmcp~=3.2` (one line, decided in Phase 1 scaffolding).
- Use exactly one import style everywhere: `from fastmcp import FastMCP` — never `from mcp.server.fastmcp import ...`.
- Verify patterns against gofastmcp.com current docs, not blog posts. In v3, all transport config goes to `http_app()`/`run()`.
- v3 bonus for the coverage requirement: `@mcp.tool` returns the original function, so decorated tools stay directly callable in unit tests.

**Warning signs:**
- `TypeError: FastMCP.__init__() got an unexpected keyword argument 'host'` (or `stateless_http`, `streamable_http_path`)
- `AttributeError: 'FastMCP' object has no attribute 'get_tools'`
- Two different `FastMCP` imports in the codebase

**Phase to address:**
Scaffolding/setup phase — pin the version and write a 5-line smoke server before building any tools.

---

### Pitfall 2: Mounting `http_app()` into FastAPI without wiring the lifespan

**What goes wrong:**
`app.mount("/mcp", mcp.http_app())` appears to work — the server starts, routes exist — then the **first real MCP request** dies with `RuntimeError: Task group is not initialized` (or `Received request before initialization was complete` → empty SSE responses). The StreamableHTTP session manager is started by the MCP sub-app's lifespan, and Starlette/FastAPI **does not run lifespans of mounted sub-apps**.

**Why it happens:**
Nested lifespans are silently ignored by the parent ASGI app. Nothing fails at import or startup — only at request time. This is the single most-reported FastMCP+FastAPI integration bug (jlowin/fastmcp#518, modelcontextprotocol/python-sdk#1220, #1367, #737).

**How to avoid:**
Use the documented pattern exactly, in this order:

```python
mcp_app = mcp.http_app(path="/")          # MCP endpoint lives at mount root
app = FastAPI(lifespan=mcp_app.lifespan)  # pass the MCP lifespan to the PARENT
app.mount("/mcp", mcp_app)                # final endpoint: /mcp
```

If TrustLens needs its own lifespan too (e.g., open SQLite at startup), combine them in one `asynccontextmanager` that enters `mcp_app.lifespan(app)` via `AsyncExitStack` — do not define two separate lifespans.

**Warning signs:**
- `/healthz` works but any MCP `initialize`/`tools/call` errors 500
- "Task group is not initialized" in logs
- Tests pass with `Client(mcp)` in-memory but the HTTP endpoint fails

**Phase to address:**
MCP server phase — first integration test must call a tool through the mounted HTTP endpoint (not only in-memory), inside `with TestClient(app):`.

---

### Pitfall 3: MCP endpoint path composition + 307 trailing-slash redirect breaks Inspector and agent clients

**What goes wrong:**
Two related path bugs: (1) `http_app()`'s default internal path is `/mcp`, so mounting it at `/mcp` yields a server at `/mcp/mcp` while everyone tests `/mcp` and gets 404. (2) Starlette's router has `redirect_slashes=True`, so `POST /mcp` can 307-redirect to `/mcp/` — MCP Inspector then shows the misleading "Check if your MCP server is running and proxy token is correct" error; some HTTP clients drop the POST body on 307; behind TLS-terminating proxies the redirect can even downgrade to `http://`. Documented across python-sdk#1168, #732, fastmcp#1544.

**Why it happens:**
Mount path and app-internal path compose invisibly, and the redirect only bites specific clients — curl follows it silently with `-L`, so manual testing "works".

**How to avoid:**
- Always `http_app(path="/")` and choose the public path in `app.mount("/mcp", ...)` — one source of truth.
- Verify with `curl -i -X POST http://localhost:8000/mcp` (no `-L`): you must NOT see a 307. If you do, mount so the exact advertised path resolves directly, or register both `/mcp` and `/mcp/`.
- In MCP Inspector: select transport **"Streamable HTTP"** (not SSE/stdio) and enter the full URL including the path, e.g. `http://localhost:8000/mcp`.
- Note for smoke tests: streamable HTTP requires `Accept: application/json, text/event-stream`; a bare curl without it gets **406 Not Acceptable** — that's protocol behavior, not a bug (but see Pitfall 5: the x402 middleware should answer 402 before this).

**Warning signs:**
- 307 in `curl -i` output; Inspector "proxy token" error; 404 at `/mcp` but something exists at `/mcp/mcp`
- Works in Inspector locally but not through the deployed HTTPS domain

**Phase to address:**
MCP server phase (path decision + curl check in the phase's acceptance test); re-verify in ops phase against the Dockerized server.

---

### Pitfall 4: x402 version confusion — v1 wire format instead of the v2 the OKX marketplace checks

**What goes wrong:**
The 402 response is built from a v1 tutorial: plain-JSON body only, `X-PAYMENT` headers, `resource` as a string inside `accepts`, human-decimal amount `0.01`. OKX's pre-registration check (`curl -i -X POST https://domain/path` expecting **402 + `PAYMENT-REQUIRED` header**) fails, or an agent client that decodes the header per v2 gets garbage — and the listing review (24h turnaround) is burned on a wire-format bug.

**Why it happens:**
x402 v2 shipped December 2025; most online examples are still v1. In v2, payment requirements moved **from the response body into a base64-encoded `PAYMENT-REQUIRED` header**; the client retries with base64 `PAYMENT-SIGNATURE`; the server returns base64 `PAYMENT-RESPONSE` after settlement. The core spec is transport-agnostic — header names live in the HTTP transport spec (`specs/transports-v2/http.md`), so it's easy to read the wrong document.

**How to avoid:**
- Implement exactly the shape from the OKX docs quoted in PROJECT.md: `x402Version: 2`, top-level `resource {url, description, mimeType}`, `accepts: [{scheme: "exact", network: "eip155:196", asset: "0x779d…3736", amount, payTo, maxTimeoutSeconds: 300}]`; testnet `eip155:1952`.
- `amount` is a **string in atomic units** — 0.01 USDT with 6 decimals = `"10000"`, not `0.01`. Verify the token's decimals on X Layer once and hardcode the conversion with a unit test.
- Emit the base64-encoded JSON in the `PAYMENT-REQUIRED` header **and** a human-readable JSON body (belt-and-suspenders; header is what the check looks for). MEDIUM confidence on whether OKX expects base64 or raw JSON in the header — verify against the OKX x402 doc during the payment phase; the challenge builder should make encoding a one-line switch.
- Build the challenge JSON in one pure function (`build_402_challenge()`) with golden-file tests, so the shape is asserted, not hoped.

**Warning signs:**
- Any `X-PAYMENT` header name in the code; `amount` containing a decimal point; `resource` as a plain string
- The pre-registration curl printout doesn't show `PAYMENT-REQUIRED:` in response headers

**Phase to address:**
x402 payment phase — its acceptance criterion is literally the OKX curl check passing against the local Docker container.

---

### Pitfall 5: Payment gate placed wrong — 402 on the MCP handshake breaks every client; 402 nowhere fails the review check

**What goes wrong:**
Two opposite failure modes. (a) Gate everything at `/mcp`: the MCP `initialize` and `tools/list` requests get 402, so no client can even connect or discover tools — the service looks dead in Inspector and to OKX's agent runtime. (b) Gate only inside tool functions: a bare `POST /mcp` returns 406/400 (missing MCP Accept headers / invalid session) instead of 402, so the OKX pre-registration curl check fails. Also: gating `/healthz` or `/` breaks health checks and the leaderboard.

**Why it happens:**
MCP multiplexes handshake and tool calls over one HTTP endpoint; naive HTTP middleware can't tell them apart, and the mounted MCP app rejects non-conforming requests before your tool code runs.

**How to avoid:**
- Implement x402 as ASGI/HTTP middleware wrapping only the `/mcp` mount, running **before** the MCP app (so a bare POST without payment gets 402, not 406).
- Inside the middleware, parse the JSON-RPC body: exempt `initialize`, `notifications/*`, `tools/list`; require payment for `tools/call` (and for unparseable/bare POSTs — that satisfies the curl check). MEDIUM confidence: mirror whatever `okxweb3-app-x402`'s `x402ResourceServer` middleware does — check its source once during the payment phase since it's the documented drop-in.
- `/healthz` and `/` (leaderboard) are never gated — assert this in tests.

**Warning signs:**
- MCP Inspector can't list tools against the payment-enabled server (with mock off)
- `curl -i -X POST /mcp` returns 406 or 400 instead of 402
- Health check flapping after payment layer lands

**Phase to address:**
x402 payment phase, with an e2e test matrix: bare POST → 402; initialize → 200; tools/call unpaid → 402; tools/call with mock payment → result.

---

### Pitfall 6: Mock mode leaking into production paths (truthy-string env parsing)

**What goes wrong:**
`if os.getenv("X402_MOCK"):` — the string `"0"` or `"false"` is truthy in Python, so setting `X402_MOCK=0` in prod **enables** the mock and the service serves paid data for free. Or the inverse: mock branches sprinkled through tool code (`if MOCK: skip verify`) make it impossible to prove the real path works, and one forgotten branch ships.

**Why it happens:**
Env vars are strings; hackathon speed encourages inline `if` checks instead of a seam.

**How to avoid:**
- Parse once at startup: `X402_MOCK = os.getenv("X402_MOCK", "0") == "1"` — fail-closed default (payment required unless explicitly mocked).
- One seam, not many branches: a `PaymentVerifier` protocol with `MockVerifier` and `X402Verifier` implementations chosen at app construction. Tool code never knows mock exists. This is also exactly the shape needed for the documented deploy-time swap to `okxweb3-app-x402`.
- Log a loud one-line banner at startup when mock is active ("X402_MOCK=1 — payments are NOT verified"); assert in the prod-config test that the banner is absent.

**Warning signs:**
- `X402_MOCK` read in more than one file; `getenv` result used directly in a boolean context
- No test that runs with mock **off** and asserts 402

**Phase to address:**
x402 payment phase (design the verifier seam before writing the middleware); ops phase documents the exact prod values in `.env.example`.

---

### Pitfall 7: Treating the scraper as the critical path — okx.ai 403s bots and is likely JS-rendered

**What goes wrong:**
Days sink into defeating a 403 (observed for generic bots — consistent with WAF/bot protection on okx.ai), and even a successful 200 on `https://www.okx.ai/agents/<id>` may return a JS SPA shell where BeautifulSoup finds zero data. Meanwhile the indexer, scoring, and MCP layers — the actual product — starve. Worse: a scraper failure at runtime crashes the indexer instead of degrading to the CSV.

**Why it happens:**
"Fresh data" feels more legitimate than a CSV snapshot, and 403s feel like a puzzle to solve. The brief only requires *polite re-scrape with graceful fallback* — the census CSV is the primary data path.

**How to avoid:**
- Build order: CSV → SQLite → scoring first. The scraper is a later, optional enhancement behind a `--refresh` flag on the indexer CLI, never in the request path.
- Timebox scraping to ~2 hours total. Politeness per the brief: ≤1 req/s (sleep *between* requests), `User-Agent: TrustLens/1.0`, on-disk cache keyed by URL with a TTL, hard timeout per request, no retries on 403 (one attempt, log, fall back).
- If pages are JS-rendered, check for embedded JSON (`__NEXT_DATA__` / inline state) before parsing DOM; if absent, stop — CSV fallback is the designed behavior, not a failure.
- Every scraper code path ends in either "parsed fields" or "fall back to CSV row + warning log" — never an unhandled exception.

**Warning signs:**
- Any scraper import in the FastAPI request path
- Retry loops or header-spoofing experiments in git history
- Scraper returns 200 but all parsed fields are None (SPA shell — stop parsing DOM)

**Phase to address:**
Data/indexer phase: CSV pipeline is the phase deliverable; scraper is the last task in the phase with an explicit timebox and a "403 → CSV fallback" test using canned responses.

---

### Pitfall 8: Census CSV parsing corrupts data silently (subscript-zero prices, shifted rating column, K-suffixes, multiline taglines)

**What goes wrong:**
Four observed edge cases each produce *silently wrong scores* rather than crashes:
1. **Subscript-zero prices** `0.0₄15 USDT` (U+2080–U+2089): naive cleaning that strips non-ASCII yields `0.015` — a **1,000–10,000x price error** feeding the price-fairness component. Correct expansion: subscript digit = count of zeros, so `0.0₄15` → `0.000015`.
2. **Shifted rating column**: for unrated agents the rating cell holds a price-like value (e.g., `0.01 USDT`) and positive% is empty. `float("0.01".split()[0])` "succeeds" → agent gets rating 0.01/5 → trust score tanks on a data artifact, and the outward text effectively (falsely) flags a real vendor — a reputational/neutral-language violation, not just a bug.
3. **`1.55K sold`**: `int()` fails, or a regex that grabs digits yields 155. Must parse K/M suffixes with decimals (`1.55K` → 1550).
4. **Multiline quoted taglines**: any line-based reading (`splitlines`, `pandas` with wrong quoting, `wc -l` sanity checks) miscounts rows and shears fields. Must use stdlib `csv` with `newline=""` and `encoding="utf-8-sig"` (BOM tolerance).

**Why it happens:**
Every one of these parses "successfully" with naive code — no exception, just wrong numbers downstream.

**How to avoid:**
- Write a dedicated `parsers.py` of pure functions (`parse_price`, `parse_sold`, `parse_rating_row`) with the observed weird values as literal test fixtures before writing the indexer.
- Validation gates, fail loud: rating must be numeric in [0, 5] **and** positive% present, else store `rating=None` + mark "insufficient data" (matches the neutral-language requirement). Price must match an expected pattern or the row is flagged.
- End-of-parse assertion: exactly 272 agents loaded; log any row that hit a fallback rule. Spot-check agent 3345 (`这个能吃吗？`) and the known `1.55K` / subscript-price rows in a test.

**Warning signs:**
- Row count ≠ 272; any agent with rating < 1 and empty positive%; any price < 0.000001 or > plausible max
- `.encode('ascii', 'ignore')` or `re.sub(r'[^\x00-\x7F]', '', ...)` anywhere near prices

**Phase to address:**
Data/indexer phase — parser unit tests with real fixture rows are the first tests in the repo (also seeds the ≥90% coverage requirement early).

---

### Pitfall 9: CJK / Unicode name lookup fails — "这个能吃吗？" must resolve

**What goes wrong:**
`score_agent(name="这个能吃吗?")` (ASCII `?`) misses the stored name with full-width `？` (U+FF1F). Token-based fuzzy matching (word-split ratios) scores CJK strings near zero because there are no spaces. Case-folding does nothing for CJK, and copy-pasted names can differ in Unicode normalization form. Result: paid calls return "agent not found" for real agents — a refund-worthy failure in a pay-per-call product.

**Why it happens:**
Fuzzy-match defaults assume space-delimited ASCII text.

**How to avoid:**
Layered lookup, cheapest first: (1) exact `id` match; (2) exact match on `unicodedata.normalize("NFKC", name).casefold().strip()` — NFKC folds full-width punctuation (`？` → `?`) and width variants, stored as an indexed `name_normalized` column at ingest; (3) substring match on normalized names; (4) `difflib.SequenceMatcher` on normalized strings (character-level — works for CJK, stdlib-only, no new deps); return the top match above ~0.6 plus candidates. On miss, return a structured "not found + closest candidates" JSON — never a bare error for a paid call.

**Warning signs:**
- Lookup tests only use ASCII names; no `name_normalized` column in the schema
- `fuzzywuzzy`/token-based matching proposed (also an unlisted dependency — constraint violation)

**Phase to address:**
Data/indexer phase (normalized column at ingest) + MCP tools phase (lookup ladder + "not found" contract), with agent 3345 as a named test case.

---

### Pitfall 10: SQLite threading and lifecycle bugs under uvicorn

**What goes wrong:**
A module-global `sqlite3.connect()` created at import time is used from FastAPI **sync** endpoints, which run in a threadpool → `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`. The reflex fix, `check_same_thread=False`, then permits genuinely unsafe concurrent use of one connection across threads. Separately: running the indexer (writer) against the DB while the server (reader) is up yields `database is locked`; and tests that share one DB file collide.

**Why it happens:**
sqlite3's thread affinity is intended behavior; FastAPI's sync-endpoint threadpool makes it surface immediately. `check_same_thread=False` is cargo-culted from tutorials without the serialization it assumes.

**How to avoid:**
For a 272-row read-mostly service, choose the boring option and write it down:
- **Server = read-only, connection per request** (or per tool call): `sqlite3.connect("file:trustlens.db?mode=ro", uri=True)` opened and closed in a dependency/context manager. Connection setup at this scale is microseconds; no threading questions at all.
- **Indexer = separate offline process** that writes the DB before the server starts (build-time in Docker, or a CLI step). Enable `PRAGMA journal_mode=WAL` at creation so a future live refresh doesn't block readers.
- Tests get a `tmp_path` DB per test via fixture; never share the dev DB.
- If a global connection is ever kept: async-only endpoints (single event-loop thread) + `check_same_thread=False` + treat it as read-only — but per-request is simpler to reason about under deadline.

**Warning signs:**
- "created in a thread" in any traceback; `check_same_thread=False` with sync `def` endpoints and a shared connection
- `database is locked` during `--refresh`; tests failing only when run in full suite

**Phase to address:**
Data/indexer phase (schema + WAL + write path) and MCP server phase (read-only per-request connections as a FastAPI dependency).

---

### Pitfall 11: Coverage scramble — 90% demanded of code that was never designed to be testable

**What goes wrong:**
Tests are deferred to a final phase, then: `--cov` points at the wrong target (repo root vs package) so numbers are meaningless; the MCP HTTP path was only ever exercised manually; scoring includes a **listing-age component that depends on `datetime.now()`**, so expected scores drift day to day and "deterministic scoring" tests are flaky by construction; scraper tests hit the live site (403 in CI); `TestClient(app)` without a `with` block never runs the lifespan, so every mounted-MCP test 500s mysteriously.

**Why it happens:**
Coverage is treated as a reporting task instead of a design constraint; time-dependence sneaks in via the age component.

**How to avoid:**
- **Inject the clock**: every scoring function takes `as_of: date` (defaulting to today at the API boundary only). This single decision makes ≥90% on `scoring/` cheap — pure functions, golden-file tests, byte-stable JSON.
- Scope the gate to what the requirement says: `--cov=trustlens.scoring --cov-fail-under=90` (plus overall reporting); exclude `__main__` blocks and the uvicorn entrypoint via `[tool.coverage.run] omit` / `pragma: no cover` — never e2e through a subprocess (subprocess code isn't measured).
- Test MCP tools three ways, cheapest first: (1) direct function calls (v3 decorators return the original function); (2) in-memory `async with Client(mcp)` for schema/contract tests (official FastMCP testing pattern, no network); (3) a handful of `with TestClient(app):` e2e tests through the real mount with `X402_MOCK=1` — the `with` block is mandatory to run the lifespan.
- Configure async tests once: `asyncio_mode = "auto"` (pytest-asyncio) or anyio, in `pyproject.toml`, not per-test decorators.
- No network in tests, ever: scraper tests consume saved fixture HTML/403 responses.

**Warning signs:**
- Coverage report lists files outside the package or shows `server.py` at 0% counted against the gate
- A test asserts an exact score without passing a date; suite green today, red tomorrow
- Tests hang or 500 on MCP calls (missing `with` / missing async mode)

**Phase to address:**
Cross-cutting: clock injection and pure-function scoring are decided in the scoring phase; test scaffolding (`pyproject` coverage + async config) lands in the scaffolding phase; the dedicated test phase only fills gaps.

---

### Pitfall 12: Route shadowing — static leaderboard mounted at "/" swallows /mcp and /healthz

**What goes wrong:**
`app.mount("/", StaticFiles(directory="static", html=True))` registered before (or alongside) other routes makes `/healthz` and `/mcp` return the leaderboard's 404/index. Starlette matches routes in registration order, and a root mount matches everything.

**Why it happens:**
The one-port requirement (`docker compose up` serves MCP + leaderboard + healthz on one port) forces all three onto one app; mount ordering is an easy thing to get wrong when routes are added across phases.

**How to avoid:**
Fixed registration order, enforced by a comment and a test: (1) `@app.get("/healthz")`, (2) `app.mount("/mcp", mcp_app)`, (3) `app.mount("/", static)` **last**. A three-line test asserts `/healthz` → JSON 200, `/mcp` POST → 402/MCP response (not HTML), `/` → HTML.

**Warning signs:**
- `/healthz` returns HTML or 404 after the leaderboard phase lands
- MCP Inspector suddenly can't connect after an unrelated "add website" commit

**Phase to address:**
Leaderboard phase — the routing-order test is part of its acceptance criteria.

---

### Pitfall 13: Hackathon critical-path inversion — ops and submission materials treated as polish

**What goes wrong:**
The real deadline chain is: **submit for marketplace review July 10–11 → review takes up to 24h → must be live before July 17 23:59 UTC**, and registration requires a public HTTPS endpoint + domain (human-only step) that answers the 402 curl check. If Dockerfile, `.env.example`, README (with the exact ASP registration prompts), and the demo script are left for "after tests", any Docker or deploy hiccup lands with zero slack — and deploy/ASP submission are stop-condition human steps that can't be rushed by the builder.

**Why it happens:**
Ops files feel like paperwork; code feels like progress. But for this project the ops files *are* deliverables (explicit requirements), and the human needs them early to do their part.

**How to avoid:**
- Dockerfile + compose + `.env.example` land as soon as the server serves anything (same phase as the MCP server, not a final phase). From then on, the demo path is `docker compose up`, keeping it perpetually working.
- README's deploy + ASP registration section (with the exact Onchain OS prompts from PROJECT.md) is written when the x402 phase completes — that's the moment the curl check can be rehearsed locally.
- Known time sinks to timebox explicitly: scraper (Pitfall 7, ~2h), leaderboard CSS (ship a plain sortable table first), scoring-algorithm tuning (fixed five components per the brief — resist adding factors), and the `okxweb3-app-x402` SDK (requires OKX API creds = stop condition; the mock-first decision is already made — don't relitigate it mid-build).
- Rehearse the demo (Inspector connect → 402 → mock-paid call → leaderboard) against the Docker container at least a day early; Pitfalls 2/3/5 all have "works locally, fails in demo" failure modes.

**Warning signs:**
- It's July 13+ and there's no Dockerfile; README has no registration section
- Any commit message like "tweak scoring weights" after the scoring phase closed

**Phase to address:**
Roadmap structure itself: ops files co-located with the server phase; submission-kit phase scheduled before the final day, not on it.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Mock verifier instead of real x402 settlement | Ships without OKX creds (stop condition) | Real SDK swap untested until deploy day | Acceptable for v1 **only** behind the `PaymentVerifier` seam (Pitfall 6) with the SDK swap documented in README |
| CSV snapshot as sole data source | No scraping battle; deterministic | Data staleness (marketplace changes after 2026-07-10) | Acceptable — brief designed for it; note snapshot date in methodology section |
| Per-request SQLite connections (no pool) | Zero threading bugs | Micro-latency per call | Always acceptable at 272 rows / hackathon traffic |
| Recompute scores on each request (no cache table) | No cache invalidation logic | Wasted CPU on leaderboard render | Acceptable; if leaderboard feels slow, compute once at startup into memory — still no cache table |
| Skipping robots.txt parsing (hardcoded 1 req/s + UA) | Less code | None at this scale if rate + UA honored | Acceptable given 403-first reality and CSV-primary design |
| Hardcoding `eip155:196` / asset address as defaults | Fewer env vars | Testnet/mainnet mixups | Acceptable only with env override (`X_LAYER_RPC`, network) and both values in `.env.example` |
| `# pragma: no cover` on defensive branches | Hits 90% honestly | Can hide real dead code | Acceptable for `__main__`, SDK-swap stubs, unreachable defensive raises — never on scoring logic |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| FastMCP in FastAPI | Mount without lifespan; double `/mcp/mcp` path | `http_app(path="/")` + `FastAPI(lifespan=mcp_app.lifespan)` + `mount("/mcp", ...)` (Pitfalls 2–3) |
| MCP Inspector | Wrong transport type selected; URL missing `/mcp` path; blaming "proxy token" error | Choose "Streamable HTTP", full URL `http://host:port/mcp`, eliminate 307s first |
| curl smoke tests of MCP | Bare POST → 406 read as "server broken" | Send `Accept: application/json, text/event-stream` + `Content-Type: application/json`; a 402 before the 406 is *correct* once payment middleware is on |
| x402 challenge | v1 shapes (`X-PAYMENT`, JSON-body-only, decimal amount) | v2: base64 `PAYMENT-REQUIRED` header, atomic-unit string amount, `resource` object; follow OKX doc exactly (Pitfall 4) |
| OKX pre-registration check | Testing GET, or testing a paid path that returns 406 | `curl -i -X POST https://domain/mcp` must show `402` + `PAYMENT-REQUIRED` header — replicate locally against Docker before the human registers |
| okx.ai scraping | Fighting the 403 with header spoofing / retries | One polite attempt (UA `TrustLens/1.0`, 1 req/s, cached), then CSV fallback with a logged warning (Pitfall 7) |
| SQLite | Shared global connection + sync endpoints | Read-only per-request connections; offline writer; WAL (Pitfall 10) |
| docker compose env | Confusing `.env` (compose `${VAR}` interpolation) with `env_file:` (container env); baking `.env` into the image | Use `env_file: .env` for container vars; `.dockerignore` + `.gitignore` the `.env`; commit `.env.example` only |
| python:3.11-slim | `HEALTHCHECK CMD curl ...` (curl absent in slim) | `HEALTHCHECK CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"` |
| uvicorn in Docker | Binding 127.0.0.1 → port mapped but unreachable | `uvicorn app.main:app --host 0.0.0.0 --port 8000`; set `PYTHONUNBUFFERED=1` for logs |

## Performance Traps

Scale is tiny (272 agents, hackathon traffic) — the real trap is over-engineering. Only these matter:

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Scraper in request path | First `score_agent` call takes seconds / 403s | Indexer is offline/CLI-only; server reads SQLite only | Immediately, on any request |
| Full 272-page rescrape loop at 1 req/s inside startup | Container takes ~5 min to become healthy | Rescrape only behind explicit `--refresh` CLI flag | Every deploy |
| Recomputing all 272 scores per leaderboard request | `/` renders slowly under demo screen-share | Compute once at startup into memory (or on first request, cached) | Only under concurrent demo load — low priority |
| Streamable HTTP stateful sessions behind multiple workers | Random "session not found" with `--workers >1` | Run a single uvicorn worker (plenty here); or `stateless_http=True` if scaling ever needed | Only if workers > 1 |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Mock verifier reachable in prod (`X402_MOCK` truthy-string bug) | Serving paid endpoints free; failed marketplace review | Fail-closed parse `== "1"`, single seam, startup banner, prod-config test (Pitfall 6) |
| `payTo` wallet or API keys hardcoded / committed | Funds misdirected; key leak in public hackathon repo | Env-only (`TRUSTLENS_PAY_TO` etc.); `.env` gitignored + dockerignored; `.env.example` with placeholders; grep-for-0x pre-commit check |
| Native mock path accepting any `PAYMENT-SIGNATURE` without even shape validation | Trivial bypass if mock semantics blur into "lenient real mode" | Mock mode is binary and explicit; real mode always delegates to verifier/SDK — no "lenient" middle mode |
| Accusatory reason strings ("scam-like", "fake reviews") | Reputational/defamation exposure against named vendors | Banned-words unit test over all reason templates (`fraud|scam|fake|manipulat`); neutral phrasing ("pattern consistent with…", "insufficient data") |
| Error responses leaking internals (paths, tracebacks) to paying agents | Info disclosure on a public paid API | Generic JSON error envelope for tool failures; log details server-side |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Score without evidence | Agents/humans can't act on a bare "62/100"; looks arbitrary next to competitors (Factor Credit Desk etc.) | Always return component breakdown + neutral `reason` strings + methodology link — this is the differentiator |
| "Agent not found" bare error on a paid call | Paying caller gets nothing for money | Fuzzy-match ladder + structured "closest candidates" response (Pitfall 9) |
| Unstable JSON keys between calls/versions | Agent callers (the actual customers) break on key renames | Freeze the response schema early; test with golden files; include `schema_version` field |
| Unrated agents scored as low-trust | Data artifact reads as an accusation (Pitfall 8 case 2) | Distinct "insufficient data" state with its own grade treatment, surfaced honestly on the leaderboard |
| Leaderboard without methodology / snapshot date | Rankings look like allegations; stale data misleads | Methodology section + "data as of 2026-07-10" stamp — both are already requirements; don't drop them under time pressure |

## "Looks Done But Isn't" Checklist

- [ ] **MCP server:** Tools work in-memory — verify through the **mounted HTTP path** inside `with TestClient(app):` and once in MCP Inspector (Streamable HTTP, full `/mcp` URL, no 307).
- [ ] **x402 layer:** 402 fires — verify the `PAYMENT-REQUIRED` **header** is present and base64-decodes to the exact OKX shape (atomic-unit string amount, `eip155:196`, correct asset address), and that `initialize`/`tools/list`/`/healthz`/`/` are NOT gated.
- [ ] **Mock mode:** Paid flow works with `X402_MOCK=1` — verify with mock **off** that every tool call yields 402, and that `X402_MOCK=0`/unset/`false` all mean OFF.
- [ ] **Indexer:** 272 rows load — verify the four edge-case rows specifically (1.55K, subscript price, shifted-rating row, agent 3345) landed with correct typed values, and rerunning the indexer is idempotent.
- [ ] **Scraper:** Code exists — verify the 403 path *and* the "200 but empty SPA" path both fall back to CSV without crashing (canned-response tests).
- [ ] **Scoring:** Deterministic — verify the same input + same `as_of` date gives byte-identical JSON, and that no reason string trips the banned-words test.
- [ ] **Leaderboard:** Renders — verify `/healthz` and `/mcp` still resolve after the static mount (route-order test), sorting works without a JS framework dependency, badge snippet copy-pastes.
- [ ] **Coverage:** ≥90% shown — verify it's measured on `scoring/` (the required target) with `--cov-fail-under` in config, not a hand-run number; suite passes twice in a row (no time flakiness) and with no network.
- [ ] **Docker:** `docker compose up` starts — verify from a clean clone: `.env.example → .env`, one port serves `/`, `/healthz`, `/mcp`; the DB exists inside the container (built or generated); healthcheck passes without curl.
- [ ] **README/submission kit:** Files exist — verify the ASP registration section quotes the exact Onchain OS prompts and the pre-registration curl check, and the demo script was actually executed once end-to-end against the container.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Wrong FastMCP version discovered mid-build | LOW–MEDIUM | Pin to the installed major; mechanical renames (`get_tools`→`list_tools`, move kwargs to `http_app()`); rerun smoke test |
| Lifespan/mount bug found at demo time | LOW | Apply the three-line documented pattern (Pitfall 2); it's config, not architecture |
| x402 shape rejected by OKX review | MEDIUM (24h review round-trip) | Fix `build_402_challenge()` + golden tests against the OKX doc; re-verify with curl before resubmitting — this is why the curl check must pass locally *before* the human registers |
| Silent CSV corruption found after scoring built | MEDIUM | Fix parser, rerun indexer (idempotent), regenerate golden score files; scores change — regenerate leaderboard copy too |
| Mock leaked to prod config | LOW | Flip env + redeploy; add the missing fail-closed test |
| Scraper time sink already consumed | LOW | Declare CSV-only for v1 (designed fallback), move on; document snapshot date |
| Coverage gap discovered on final day | MEDIUM–HIGH | Only recoverable if scoring is pure functions with injected clock — otherwise cut scope to the required `scoring/` target and document; this is why testability is decided in the scoring phase, not the test phase |

## Pitfall-to-Phase Mapping

Assumed phase topics (roadmap TBD): 1 Scaffolding → 2 Data/Indexer → 3 Scoring → 4 MCP server (+Docker skeleton) → 5 x402 → 6 Leaderboard → 7 Tests/hardening → 8 Ops/submission kit.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. FastMCP version drift | Phase 1 (pin `fastmcp~=3.2`) | Smoke server runs; imports uniform; `pip freeze` shows pinned version |
| 2. Lifespan not wired | Phase 4 | `with TestClient(app):` tool call over HTTP succeeds |
| 3. Path/307/Inspector | Phase 4 | `curl -i -X POST /mcp` shows no 307; Inspector connects via Streamable HTTP |
| 4. x402 v1/v2 confusion | Phase 5 | Golden test on decoded `PAYMENT-REQUIRED` header; OKX curl check passes vs Docker |
| 5. Payment gate placement | Phase 5 | Test matrix: bare POST→402, initialize→OK, unpaid call→402, `/healthz` & `/` open |
| 6. Mock leakage | Phase 5 (seam), Phase 8 (env docs) | Prod-config test asserts 402 with mock off; `"0"`/unset/`"false"` all mean off |
| 7. Scraper critical path | Phase 2 (order + timebox) | Scoring works with scraper module deleted; 403 and SPA-shell tests pass offline |
| 8. CSV silent corruption | Phase 2 | 272-row assertion; four named edge-case fixtures typed correctly |
| 9. CJK lookup | Phase 2 (normalized column) + Phase 4 (ladder) | `score_agent("这个能吃吗？")` and ASCII-`?` variant both resolve to agent 3345 |
| 10. SQLite threading | Phase 2 (writer/WAL) + Phase 4 (ro per-request) | Full test suite parallel-safe; no `check_same_thread` on shared sync connections |
| 11. Coverage scramble | Phase 3 (clock injection, pure functions) + Phase 1 (cov config) | `--cov=…scoring --cov-fail-under=90` green in config; suite green two days running |
| 12. Route shadowing | Phase 6 | Route-order test: `/healthz` JSON, `/mcp` MCP, `/` HTML |
| 13. Critical-path inversion | Roadmap structure (Docker in Phase 4; README deploy section in Phase 5; kit in Phase 8 ≥1 day before deadline) | Clean-clone `docker compose up` demo rehearsed before submission day |

## Sources

- FastMCP lifespan/mounting: [gofastmcp.com FastAPI integration](https://gofastmcp.com/integrations/fastapi), [jlowin/fastmcp#518](https://github.com/jlowin/fastmcp/issues/518), [python-sdk#1220](https://github.com/modelcontextprotocol/python-sdk/issues/1220), [python-sdk#1367](https://github.com/modelcontextprotocol/python-sdk/issues/1367), [python-sdk#737](https://github.com/modelcontextprotocol/python-sdk/issues/737) — HIGH
- 307/trailing slash/Inspector: [python-sdk#1168](https://github.com/modelcontextprotocol/python-sdk/issues/1168), [python-sdk#732](https://github.com/modelcontextprotocol/python-sdk/issues/732), [fastmcp#1544](https://github.com/jlowin/fastmcp/issues/1544) — HIGH
- FastMCP versions: [Upgrading from MCP SDK](https://gofastmcp.com/getting-started/upgrading/from-mcp-sdk), [Upgrading from FastMCP 2](https://gofastmcp.com/getting-started/upgrading/from-fastmcp-2), Context7 `/prefecthq/fastmcp` (v3.2.x current; decorator/`list_tools` changes), [awslabs/mcp#2533](https://github.com/awslabs/mcp/issues/2533) (unpinned-version breakage), [python-sdk#1276](https://github.com/modelcontextprotocol/python-sdk/issues/1276) — HIGH
- FastMCP in-memory testing: Context7 `/prefecthq/fastmcp` docs `development/tests.mdx` (`async with Client(server)`) — HIGH
- x402 v2: [coinbase/x402 v2 spec](https://github.com/coinbase/x402/blob/main/specs/x402-specification-v2.md) (transport-agnostic core), [HTTP transport v2](https://github.com/coinbase/x402/blob/main/specs/transports-v2/http.md) (PAYMENT-REQUIRED / PAYMENT-SIGNATURE / PAYMENT-RESPONSE, base64 JSON), [x402 v2 launch post](https://www.x402.org/writing/x402-v2-launch) — HIGH for spec; OKX-specific header encoding MEDIUM (verify OKX doc at build time; OKX values in PROJECT.md fetched 2026-07-10)
- SQLite threading: [python-sqlite thread safety](https://ricardoanderegg.com/posts/python-sqlite-thread-safety/), [fastapi-sqlalchemy#45](https://github.com/mfreeborn/fastapi-sqlalchemy/issues/45), stdlib `sqlite3` documented behavior — HIGH
- TestClient lifespan: [FastAPI testing events docs](https://fastapi.tiangolo.com/advanced/testing-events/), [fastapi discussion #10800](https://github.com/fastapi/fastapi/discussions/10800) — HIGH
- okx.ai scraping: 403 for generic bots observed first-hand (PROJECT.md); SPA-rendering risk inferred from modern marketplace frontends — MEDIUM/LOW, hence CSV-primary design
- CSV edge cases: observed values enumerated in PROJECT.md (census 2026-07-10); subscript-zero convention per CoinGecko/CMC price display standard — HIGH for observed rows
- Hackathon timing: OKX brief constraints in PROJECT.md (24h review, July 17 deadline, human-only deploy steps) — HIGH

---
*Pitfalls research for: TrustLens — paid MCP (A2MCP + x402) trust-score service*
*Researched: 2026-07-10*
