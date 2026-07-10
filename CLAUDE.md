<!-- GSD:project-start source:PROJECT.md -->
## Project

**TrustLens**

TrustLens is a pay-per-call Agent-to-MCP (A2MCP) service for the OKX.AI marketplace that returns a trust score for any listed OKX.AI agent — so humans and other agents can check "should I hire this agent?" before paying. It is an OKX AI Genesis Hackathon entry: a standard MCP server over HTTPS whose endpoints implement the x402 payment standard, priced at 0.01 USDT/call, settling in USDT/USDG on X Layer.

**Core Value:** Any human or agent can get a deterministic, evidence-based answer to "should I hire this OKX.AI agent?" in one paid MCP call.

### Constraints

- **Timeline**: Submit for OKX marketplace review July 10–11, 2026; live before **July 17, 2026 23:59 UTC** — bias every decision toward shipping a working v1 fast
- **Tech stack**: Python 3.11+, FastAPI, FastMCP, SQLite (stdlib `sqlite3` or SQLAlchemy), httpx, BeautifulSoup; uvicorn as the ASGI server for FastAPI; pytest (+coverage) as dev/test tooling. **No other runtime dependencies without asking the user**
- **Scope discipline**: Only build what the brief specifies — no auth, accounts, extra databases, admin panels, dark mode
- **Scraping politeness**: ≤1 req/sec, User-Agent `TrustLens/1.0`, on-disk cache, graceful degradation to census CSV if blocked or markup changes
- **Secrets**: environment variables only (`TRUSTLENS_PAY_TO`, `TRUSTLENS_PRICE_USDT`, `X_LAYER_RPC`, `X402_MOCK`); `.env` gitignored; `.env.example` documents every var with placeholders; never hardcode keys or addresses
- **Language**: all outward-facing text is neutral, factual, methodology-linked — never allegations against named agents
- **Workspace**: work only inside `trustlens/`; census CSV original, research report, and prompt file in the parent folder are read-only inputs
- **Git**: commits authored solely by the user's identity; no AI attribution of any kind in any commit or PR
- **Stop conditions (require human review)**: remote deploys/domain purchase; real wallets/funds/keys/OKX Agentic Wallet login; submitting the ASP listing, posting publicly, or the hackathon Google Form; adding unlisted dependencies; deleting any file; OKX SDK contradicting x402 assumptions; any error unresolved after 2 attempts
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Core Technologies
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.13 (image `python:3.13-slim`) | Runtime | Satisfies the "3.11+" constraint; 3.13.14 is the mature bugfix line with full wheel coverage for every dep. 3.14 works but buys nothing here. |
| FastAPI | 0.139.0 (2026-07-01) | HTTP host app: static leaderboard, `/healthz`, x402 middleware, MCP mount point | Locked. Requires `starlette>=0.46.0` (upper pin removed) — resolves cleanly with FastMCP's `starlette>=1.0.1` to starlette 1.3.1. |
| FastMCP (`fastmcp` on PyPI) | 3.4.4 (2026-07-09) | MCP server framework; `http_app()` produces the Streamable-HTTP ASGI app | Locked. **Now a meta-package** that installs `fastmcp-slim[client,server]==3.4.4`; import namespace unchanged (`from fastmcp import FastMCP`). Pin `fastmcp>=3,<4`. |
| mcp (official SDK) | 1.28.1 (auto-installed) | Protocol layer under FastMCP | Do NOT install or import directly — FastMCP pins `mcp>=1.24.0,<2.0` and wraps it. |
| uvicorn | 0.51.0 | ASGI server, one process, one port | Locked. FastMCP's server extra already requires `uvicorn>=0.35`, so pinning 0.51.0 is consistent. Plain `uvicorn` is enough; `[standard]` extras (uvloop) are a nice-to-have in Docker only. |
| SQLite (stdlib `sqlite3`) | stdlib (3.13) | Agent store: 272 rows, read-heavy | Locked (stdlib option chosen). Zero deps, zero ORM ceremony; connection-per-operation is correct and fast at this scale. |
| httpx | 0.28.1 (2024-12-06, still latest) | Scraper HTTP client | Locked. Same version FastMCP pins (`>=0.28.1,<1.0`) — no conflict. Sync `httpx.Client` for the offline indexer. |
| beautifulsoup4 | 4.15.0 (2026-06-07) | HTML parsing for okx.ai agent pages | Locked. Use the stdlib `"html.parser"` backend — `lxml` would be an unlisted runtime dep. |
### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.1.1 (2026-06-19) | Test runner | Dev/test only. Requires Python >=3.10 — fine. |
| pytest-cov | 7.1.0 (2026-03-21) | Coverage gate on `scoring/` | Dev/test only. Requires `coverage>=7.10.6` (auto-resolved; coverage 7.15.0 current). 7.0 dropped subprocess measurement — irrelevant here (in-process tests only). |
| SQLAlchemy | 2.0.51 | ORM (allowed by lock) | **Skip it.** Permitted but overkill for 272 rows and adds nothing over `sqlite3.Row`. Only reach for it if the schema grows real relations post-hackathon. |
| okxweb3-app-x402 | (deploy-time) | OKX Payment SDK facilitator middleware | NOT in v1 requirements (needs wallet-tied OKX API creds = stop condition). v1 hand-rolls the x402 v2 wire flow with plain Starlette middleware + `X402_MOCK=1`; README documents the SDK as the deploy-time drop-in. |
### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| uvicorn CLI | Local dev server | `uvicorn app.main:app --port 8000 --reload`. One port serves MCP + leaderboard + healthz. |
| pytest + pyproject config | Coverage-gated test run | Config below; `pytest` alone enforces the 90% gate on `scoring/`. |
| Docker (`python:3.13-slim`) | Deployment | Current slim = Debian 13 "trixie" base; `slim-bookworm` also published if you need Debian 12. Pin `python:3.13-slim` (or `python:3.13.14-slim` for full reproducibility). |
## Verified Integration Patterns
### 1. FastMCP 3.x mounted inside FastAPI — one port (VERIFIED, HIGH confidence)
# app/main.py
### 2. SQLite from sync FastAPI / scoring code (HIGH confidence, stdlib)
- Run `PRAGMA journal_mode=WAL` once at init only if the scraper will write while the server reads; otherwise skip.
- Store timestamps as ISO-8601 TEXT — the implicit datetime adapters are deprecated since Python 3.12.
- Always parameterized queries (`?`), never f-strings.
- Do NOT use `check_same_thread=False` + shared connection + lock — more code, same result, easier to get wrong.
### 3. httpx + BeautifulSoup polite scraper (HIGH confidence)
### 4. pytest + pytest-cov scoped to scoring/ at ≥90% (HIGH confidence, changelog-verified)
# pyproject.toml
- `--cov=scoring` takes the importable package name; combined with `[tool.coverage.run] source`, only `scoring/` counts toward the 90% gate — MCP wiring and scraper don't dilute or inflate it.
- pytest-cov 7.0 dropped subprocess coverage; irrelevant here (in-process tests only), just don't expect coverage from `subprocess.run` calls.
- v3 bonus: because `@mcp.tool` now returns the original function, tests can import and call tool functions directly — no MCP client harness needed for unit tests; keep one e2e test through the HTTP app with `X402_MOCK=1`.
### 5. Dockerfile (HIGH confidence)
## Installation
# requirements.txt (runtime)
# requirements-dev.txt (test)
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| stdlib `sqlite3`, connection-per-op | SQLAlchemy 2.0.51 (allowed by lock) | Only if schema grows real relations/migrations post-hackathon; pure overhead for 272 rows now |
| `fastmcp` 3.4.4 (pin `>=3,<4`) | Pin old `fastmcp==2.12.x` | Only if a 3.x regression surfaces mid-build; the mount pattern is identical, so downgrade is a one-line pin change |
| Stateful HTTP (default) | `http_app(stateless_http=True)` | When scaling to multiple uvicorn workers / horizontal replicas behind a load balancer |
| `python:3.13-slim` | `python:3.12-slim` / `3.13-slim-bookworm` | If any Debian-trixie-specific issue appears on the deploy host (unlikely; all deps ship wheels) |
| Hand-rolled x402 middleware + `X402_MOCK` | `okxweb3-app-x402` SDK in-code | Deploy time only, once OKX API creds exist (human-review stop condition per PROJECT.md) |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `from mcp.server.fastmcp import FastMCP` | That's FastMCP 1.0 vendored inside the official `mcp` SDK — older, different API; blog posts mix the two constantly | `from fastmcp import FastMCP` (the `fastmcp` PyPI package) |
| `FastMCP("name", host=..., port=..., sse_path=..., streamable_http_path=..., stateless_http=...)` | Constructor kwargs **removed in 3.0** — this is the main 2.x→3.x break | Pass to `mcp.run(...)` or `mcp.http_app(...)` |
| SSE transport (`transport="sse"`, old `mcp.sse_app()`) | Legacy in FastMCP v3; superseded by Streamable HTTP in the MCP spec (2025-03-26) | `mcp.http_app()` / `transport="http"` |
| `mcp_app` mounted without passing its lifespan to FastAPI | Session manager never initializes → every MCP call fails; the #1 documented mounting mistake | `FastAPI(lifespan=mcp_app.lifespan)` or `combine_lifespans(...)` |
| Static mount at `/` registered before `/healthz` or `/mcp` | Starlette matches in registration order — the catch-all shadows everything | Mount `StaticFiles(..., html=True)` last |
| `lxml` / `html5lib` parsers | Unlisted runtime deps (violates lock); `html.parser` handles okx.ai pages fine | `BeautifulSoup(html, "html.parser")` |
| `requests`, `requests-cache`, `hishel`, `aiosqlite` | All unlisted deps; sync httpx + hand-rolled disk cache + stdlib sqlite3 cover every need | Patterns above |
| Shared `sqlite3.Connection` across threadpool calls | Cross-thread use raises or corrupts state; `check_same_thread=False` + lock is needless complexity | New connection per operation |
| Component-object access on decorated tools (`score_agent.name`) | v3 `@mcp.tool` returns the plain function; `.name`/`.description` access breaks (v2 behavior only behind deprecated `FASTMCP_DECORATOR_MODE=object`) | Introspect via `mcp.list_tools()` (renamed from v2 `get_tools()`) |
| `python:3.15-rc-slim`, unpinned `python:latest` | RC/moving targets during a one-week hackathon | `python:3.13-slim` |
## Stack Patterns by Variant
- Keep `http_app(path="/")` + `app.mount("/mcp", mcp_app)` as shown — docs state the endpoint lands at `/mcp`.
- If a client ever reports a 307, it's the Starlette trailing-slash redirect on the mount boundary; test both `/mcp` and `/mcp/` with `curl -i -X POST` early (the same command OKX's pre-registration check uses). (MEDIUM confidence on the edge case; the happy path is documented.)
- Switch to `mcp.http_app(path="/", stateless_http=True)` (or `FASTMCP_STATELESS_HTTP=true`) so MCP sessions don't need worker affinity.
- The indexer already degrades to the census CSV (`data/okx-marketplace-census-2026-07-10.csv`) — no stack change; this is why the cache + fallback live in the indexer, not the request path.
## Version Compatibility
| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| fastmcp 3.4.4 | mcp >=1.24.0,<2.0 (1.28.1 resolves) | Auto-installed via `fastmcp-slim[client,server]`; never pin `mcp` yourself |
| fastmcp 3.4.4 | httpx >=0.28.1,<1.0 | Our explicit `httpx==0.28.1` pin sits exactly at the floor — no conflict |
| fastmcp 3.4.4 (server extra) | uvicorn >=0.35 | Our `uvicorn==0.51.0` pin OK |
| fastmcp 3.4.4 | starlette >=1.0.1 | — |
| fastapi 0.139.0 | starlette >=0.46.0 (no upper bound) | Resolves with FastMCP to starlette 1.3.1 — **verified no conflict** (FastAPI dropped its historical `<x` upper pin) |
| pytest-cov 7.1.0 | coverage >=7.10.6 (7.15.0 resolves), pytest >=7 | Works with pytest 9.1.1 |
| All runtime deps | Python 3.13 | Floors: fastmcp/fastapi/uvicorn/pytest >=3.10, httpx >=3.8, bs4 >=3.7 — 3.13 satisfies everything with headroom |
## Sources
- Context7 `/prefecthq/fastmcp` (v3.2.x snapshot; 4,237 snippets) — `http_app()` + FastAPI mount + lifespan pattern, `combine_lifespans` import path, transport names, `stateless_http`, SSE-legacy status — HIGH
- https://gofastmcp.com/development/upgrade-guide — v2→v3 breaking changes (constructor kwargs removed, `@mcp.tool` returns plain function, `get_tools()`→`list_tools()`) — HIGH
- https://gofastmcp.com/integrations/fastapi — mount pattern, "always pass the lifespan context", 2.3.1+ mounting — HIGH
- PyPI JSON API (live, 2026-07-10) — exact versions/release dates/`requires_dist` for fastmcp 3.4.4, fastmcp-slim 3.4.4, mcp 1.28.1, fastapi 0.139.0, uvicorn 0.51.0, httpx 0.28.1, beautifulsoup4 4.15.0, pytest 9.1.1, pytest-cov 7.1.0, coverage 7.15.0, SQLAlchemy 2.0.51, starlette 1.3.1 — HIGH
- https://pytest-cov.readthedocs.io/en/latest/changelog.html — 7.0.0 subprocess-measurement removal + coverage>=7.10.6 floor; 7.1.0 fail-under consistency fix — HIGH
- docker-library/python `versions.json` (GitHub master, 2026-07-10) — python 3.13.14 `slim-trixie`/`slim-bookworm` variants — HIGH
- Python stdlib `sqlite3` / Starlette routing-order / httpx Client semantics — stable long-standing APIs — HIGH (training-data-stable, spot-consistent with current docs)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
