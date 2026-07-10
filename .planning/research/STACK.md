# Stack Research

**Domain:** Paid A2MCP data service (MCP-over-HTTPS + x402 pay-per-call) — Python, single-port FastAPI host
**Researched:** 2026-07-10
**Confidence:** HIGH (all versions verified live on PyPI 2026-07-10; FastMCP patterns verified against Context7 `/prefecthq/fastmcp` v3 docs and the official v2→v3 upgrade guide)

> Stack is LOCKED by PROJECT.md. This document verifies current versions, exact package names, and correct integration patterns within that lock. One material finding: **FastMCP is now 3.x, not 2.x** — the 2.x-era API the plan assumed (`FastMCP()`, `@mcp.tool`, `http_app()`) survives intact in 3.x, but several 2.x constructor kwargs were removed. Details below. No showstoppers.

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

This exact shape is from the current official docs (`docs/deployment/http.mdx`, `docs/integrations/fastapi.mdx` via Context7 `/prefecthq/fastmcp`). The API drifted at 3.0 but this pattern carried over from 2.3.1+ unchanged.

```python
# app/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastmcp import FastMCP                    # v2/v3 import — NOT mcp.server.fastmcp

mcp = FastMCP("TrustLens")                     # v3: NO host/port/transport kwargs here

@mcp.tool                                      # bare decorator works; v3 returns the
def score_agent(agent_id: str) -> dict:       # original function unchanged, so tests
    """Trust score for an OKX.AI agent."""     # can call score_agent(...) directly
    ...

mcp_app = mcp.http_app(path="/")               # Streamable HTTP ASGI app; path="/"
                                               # because the mount below adds /mcp

app = FastAPI(title="TrustLens", lifespan=mcp_app.lifespan)  # REQUIRED — without the
                                               # lifespan the MCP session manager never
                                               # initializes and every call fails

@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}

app.mount("/mcp", mcp_app)                                        # MCP at POST /mcp
app.mount("/", StaticFiles(directory="site", html=True), name="site")  # leaderboard —
                                               # MUST be mounted LAST (Starlette matches
                                               # routes in registration order; "/" is a
                                               # catch-all)
```

Run: `uvicorn app.main:app --host 0.0.0.0 --port 8000` → `/mcp` (MCP Streamable HTTP), `/healthz`, `/` (static leaderboard), all one port.

**If you need your own startup logic (DB init), combine lifespans** — verified helper, new-ish import path:

```python
from contextlib import asynccontextmanager
from fastmcp.utilities.lifespan import combine_lifespans

@asynccontextmanager
async def app_lifespan(app):
    init_db()          # seed SQLite from census CSV if missing
    yield

app = FastAPI(lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan))
```

**Transport facts (v3, verified):** `http_app()` serves Streamable HTTP. `mcp.run()` accepts `transport="stdio" | "http" | "sse" | "streamable-http"`; `"http"` is the recommended name, `"streamable-http"` is a live alias, `"sse"` is legacy ("use HTTP instead for new projects" — official docs). For multi-worker deploys later, `mcp.http_app(stateless_http=True)` (or `FASTMCP_STATELESS_HTTP=true`) removes session affinity — a good fit for pay-per-call, but the default stateful mode is fine for v1 single-worker.

**Tool functions:** both `def` and `async def` are supported. Keep TrustLens tools sync `def` — the scoring path is CPU + SQLite, no await points needed.

**x402 placement:** a plain Starlette `BaseHTTPMiddleware` (or pure ASGI middleware) on `app` that intercepts `request.url.path.startswith("/mcp")`, checks the payment header, and returns `Response(status_code=402, headers={"PAYMENT-REQUIRED": ...})` with the x402 v2 challenge JSON body. No extra package needed — Starlette is already there.

### 2. SQLite from sync FastAPI / scoring code (HIGH confidence, stdlib)

FastAPI runs sync `def` endpoints and FastMCP runs sync tools in a threadpool → **never share one `sqlite3.Connection` across calls**. At 272 rows, connection-per-operation is the simple correct pattern (open cost is microseconds):

```python
import sqlite3
from contextlib import closing

def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)        # new connection per call — thread-safe by construction
    conn.row_factory = sqlite3.Row         # dict-like rows
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def fetch_agent(db_path: str, agent_id: str) -> dict | None:
    with closing(get_conn(db_path)) as conn:
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        return dict(row) if row else None
```

- Run `PRAGMA journal_mode=WAL` once at init only if the scraper will write while the server reads; otherwise skip.
- Store timestamps as ISO-8601 TEXT — the implicit datetime adapters are deprecated since Python 3.12.
- Always parameterized queries (`?`), never f-strings.
- Do NOT use `check_same_thread=False` + shared connection + lock — more code, same result, easier to get wrong.

### 3. httpx + BeautifulSoup polite scraper (HIGH confidence)

1 req/s, `TrustLens/1.0` UA, on-disk cache, graceful CSV fallback — all with zero extra deps:

```python
import hashlib, time
from pathlib import Path
import httpx
from bs4 import BeautifulSoup

MIN_INTERVAL = 1.0                          # ≤ 1 req/sec (project constraint)
_last_request = 0.0

client = httpx.Client(
    headers={"User-Agent": "TrustLens/1.0"},
    timeout=httpx.Timeout(10.0, connect=5.0),
    follow_redirects=True,
)

def polite_get(url: str, cache_dir: Path) -> str | None:
    cached = cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".html")
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    global _last_request
    wait = MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    try:
        resp = client.get(url)
        _last_request = time.monotonic()
        resp.raise_for_status()
    except httpx.HTTPError:
        return None                          # caller falls back to census CSV
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached.write_text(resp.text, encoding="utf-8")
    return resp.text

def parse_agent(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")   # stdlib parser — lxml is an unlisted dep
    ...
```

The scraper is an offline indexer script (not request-path code), so sync httpx + `time.sleep` is correct — no async ceremony.

### 4. pytest + pytest-cov scoped to scoring/ at ≥90% (HIGH confidence, changelog-verified)

`--cov=PACKAGE --cov-report=term-missing --cov-fail-under=N` is unchanged through pytest-cov 7.1.0; 7.1.0 specifically fixed `--cov-fail-under` consistency across report options.

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=scoring --cov-report=term-missing --cov-fail-under=90"

[tool.coverage.run]
source = ["scoring"]        # measurement scoped to the scoring package only

[tool.coverage.report]
show_missing = true
```

- `--cov=scoring` takes the importable package name; combined with `[tool.coverage.run] source`, only `scoring/` counts toward the 90% gate — MCP wiring and scraper don't dilute or inflate it.
- pytest-cov 7.0 dropped subprocess coverage; irrelevant here (in-process tests only), just don't expect coverage from `subprocess.run` calls.
- v3 bonus: because `@mcp.tool` now returns the original function, tests can import and call tool functions directly — no MCP client harness needed for unit tests; keep one e2e test through the HTTP app with `X402_MOCK=1`.

### 5. Dockerfile (HIGH confidence)

```dockerfile
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Verified from docker-library/python `versions.json` (2026-07-10): `python:3.13-slim` = 3.13.14, variants `slim-trixie` (current default) and `slim-bookworm`. 3.11.15/3.12.13/3.14.6 also available if needed.

## Installation

```bash
# requirements.txt (runtime)
fastapi==0.139.0
fastmcp==3.4.4
uvicorn==0.51.0
httpx==0.28.1
beautifulsoup4==4.15.0

# requirements-dev.txt (test)
pytest==9.1.1
pytest-cov==7.1.0
```

`pip install -r requirements.txt` — fastmcp transitively brings `fastmcp-slim[client,server]`, `mcp` 1.28.x, `starlette` 1.3.x, `pydantic` 2.x. No pins conflict (verified: FastAPI needs `starlette>=0.46.0`, FastMCP needs `starlette>=1.0.1`, `httpx>=0.28.1,<1.0`, `uvicorn>=0.35`).

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

**If the OKX marketplace client turns out to require the endpoint exactly at `/mcp` with no redirect:**
- Keep `http_app(path="/")` + `app.mount("/mcp", mcp_app)` as shown — docs state the endpoint lands at `/mcp`.
- If a client ever reports a 307, it's the Starlette trailing-slash redirect on the mount boundary; test both `/mcp` and `/mcp/` with `curl -i -X POST` early (the same command OKX's pre-registration check uses). (MEDIUM confidence on the edge case; the happy path is documented.)

**If you add multiple uvicorn workers for the live deploy:**
- Switch to `mcp.http_app(path="/", stateless_http=True)` (or `FASTMCP_STATELESS_HTTP=true`) so MCP sessions don't need worker affinity.

**If scraping okx.ai gets blocked:**
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

---
*Stack research for: TrustLens — paid A2MCP trust-score service (OKX AI Genesis Hackathon)*
*Researched: 2026-07-10*
