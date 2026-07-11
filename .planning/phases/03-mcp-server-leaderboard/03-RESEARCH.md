# Phase 3: MCP Server & Leaderboard - Research

**Researched:** 2026-07-11
**Domain:** FastMCP 3.4.4 mounted in FastAPI 0.139.0 (Streamable HTTP), static leaderboard generation, Docker packaging
**Confidence:** HIGH — every integration seam was proven with a working proof-of-concept on THIS machine (Python 3.14.2, fastmcp 3.4.4, fastapi 0.139.0, starlette 1.3.1, mcp 1.28.1, uvicorn 0.51.0, node 24.15.0, Inspector 0.22.0), against the real 272-agent `data/trustlens.db`. Code shapes below are transcribed from the working PoC, not from docs.

## Summary

The locked mount pattern from STACK.md has one **empirically confirmed defect on the installed stack**: starlette 1.3.1's `Mount("/mcp", ...)` compiles to regex `^/mcp/(?P<path>.*)$`, so bare `POST /mcp` **never reaches the MCP app**. With the static leaderboard mounted at `/` it returns **405** (StaticFiles swallows it); without the static mount it returns **307 → /mcp/**. Either way the advertised endpoint `/mcp` is broken for exact-path clients and for OKX's Phase-4 `curl -i -X POST /mcp` check. The fix is a 5-line pure-ASGI path-rewrite middleware (verified: both `/mcp` and `/mcp/` then answer 200 with static, healthz, and badge routes intact). Everything else in the locked pattern works exactly as documented: `http_app(path="/")`, `combine_lifespans`, mount-before-static ordering.

Structured output (MCPS-02 / 2025-06-18 compliance) is solved by **TypedDict return annotations**: FastMCP derives a full `outputSchema` (properties + required) via pydantic serialization-mode TypeAdapter, emits `structuredContent` alongside a JSON text block, and — critically — **validates tool returns against the schema server-side** ("Output validation error: 'agent_id' is a required property"). Consequence: success paths must return exactly conforming dicts, and the not-found path must `raise ToolError(<deterministic JSON string>)` (verified clean `isError:true` result; plain `ValueError` **leaks exception internals to the client**). MCP Inspector 0.22.0 CLI lists and calls all tools against the live server with zero extra flags (`npx --yes @modelcontextprotocol/inspector --cli http://127.0.0.1:8000/mcp --method tools/list`), with three Windows quirks documented below. Warm end-to-end tool-call latency is **median 39 ms / max 103 ms** (500 ms budget met 5–12x); a 272-row leaderboard built with stdlib templating weighs **117.8 KiB** with sortable/filterable vanilla JS that passes `node --check`.

**Primary recommendation:** Use the locked composition PLUS the `McpPathRewrite` middleware verbatim, TypedDict returns + `ToolError` for all 4 tools, `json_response=True` on `http_app()` (verified Inspector-compatible; makes every raw-HTTP test and the Phase-4 curl check plain JSON instead of SSE), and the exact commands/files quoted below. One environment blocker: **Docker Desktop's engine is installed but not running** — the executor must start it before the OPS-01 task.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**App composition (locked — from verified STACK/ARCHITECTURE research)**
- `server/` package with a `create_app()` factory: FastMCP 3.4.4 (`from fastmcp import FastMCP`), `mcp_app = mcp.http_app(path="/")`, mounted at `/mcp`, with the MCP app's lifespan passed to FastAPI (the #1 documented mounting mistake is omitting it) — combine lifespans if the app needs its own
- Route registration order: `/healthz` and `/mcp` BEFORE the static mount at `/` (Starlette matches in registration order; static-at-/ registered last)
- One port (default 8000), plain `uvicorn`; Streamable HTTP transport only (never SSE); test both `/mcp` and `/mcp/` for the 307 trailing-slash edge
- Read-only DB access: connection-per-request against `data/trustlens.db` (WAL), sqlite3 stdlib; the server NEVER writes and NEVER recomputes scores

**The 4 tools (locked verbatim from the brief — no more, no fewer)**
1. `score_agent(agent_id_or_name)` — full score card
2. `compare_agents(ids: list)` — cards + per-component winners
3. `category_leaderboard(category, limit=10)` — ranked slice
4. `marketplace_stats()` — aggregate stats
- Every response: deterministic JSON including `generated_at`, `methodology_url`, plus the Phase 2 envelope (score_version, data_as_of, confidence, disclaimer) — values read from the scores/agents tables, not recomputed
- MCP 2025-06-18 compliance: tools declare `outputSchema` and return conforming `structuredContent` (FastMCP v3 derives schemas from type annotations — researcher verifies the exact pattern)
- Lookup semantics for `score_agent`: id exact match → name exact → NFKC-casefolded `name_key` match; MUST resolve both `"3345"` and `"这个能吃吗？"`; name_key collisions (2 real ones exist) resolve deterministically with the ambiguity disclosed in the response
- Unknown agent → structured not-found error JSON (neutral wording), never a crash
- NR agents: score card with grade "NR", score null, confidence low, honest reasons — a valid, sellable answer

**Leaderboard (locked — WEB-01..03 + brief verbatim)**
- Single static HTML page, inline CSS/JS, NO framework, NO external requests (fonts/CDNs) — self-contained bytes
- Generated from SQLite by the refresh pipeline (stdlib `string.Template` or f-string templating — Jinja2 is NOT an allowed dep): builder module (`web/build.py`) invoked at the end of `indexer.refresh` (WEB-03) writing `web/dist/index.html` (gitignored)
- Content: ranked table of ALL agents (sortable columns incl. score, sold, rating, price, category; ranked by TrustScore desc, NR agents listed after scored ones), grade badges, category filter dropdown, "About the methodology" section (`id="methodology"` anchor: component weights, grade bands, NR rule, score_version, data_as_of, disclaimer, derived-category disclosure), "TrustLens Verified" badge embed snippet (self-hosted SVG endpoint `/badge/{agent_id}.svg` + copyable HTML snippet)
- Loads <2s: trivial for a static file — keep total page weight sane (no images beyond inline SVG)
- Neutral presentation: grade colors neutral/analytic (no alarmist red "danger" styling), all copy factual with methodology links; NO dark mode (brief exclusion)
- `methodology_url` = `{TRUSTLENS_BASE_URL}/#methodology` with env `TRUSTLENS_BASE_URL` defaulting to `http://localhost:8000`

**/healthz (locked — MCPS-03)**
- JSON: status, agent count, score count, score_version, data_as_of; 200 when DB present with scores, 503 otherwise; never payment-gated (Phase 4 must keep it free)

**Docker (locked — OPS-01)**
- `Dockerfile` on `python:3.13-slim`; `docker-compose.yml` serving everything on one port
- Container start: entrypoint ensures DB exists (runs `python -m indexer.refresh` if `data/trustlens.db` missing — offline CSV seed works in-image), then `uvicorn server.main:app`
- `.env` optional at this phase (compose `env_file` wired but tolerant of absence); full `.env.example` lands in Phase 4 with the payment vars

**Performance (locked — MCPS-04)**
- `score_agent("这个能吃吗？")` and `score_agent("3345")` return full score cards in <500ms from a warm DB — enforce with a timed test (generous CI margin, e.g. assert < 500ms after one warm-up call)

**Tests (locked)**
- MCP tool schema tests: `tools/list` returns exactly 4 tools with expected names/schemas; tool calls return the envelope fields; direct function-call unit tests (FastMCP v3 `@mcp.tool` returns the plain function) + one in-process e2e through the HTTP app (`with TestClient(app):` — lifespan context REQUIRED)
- healthz, leaderboard build (all 272 rows present, filter/sort hooks in DOM, methodology anchor, badge snippet), lookup edge cases (CJK, id, collision, not-found), perf smoke
- Full suite green; scoring/ coverage gate unaffected (server tests run with the gate active — measure scoring only, per existing pyproject)
- MCPS-05 (MCP Inspector lists/calls all 4 tools): node 24 + npx available — verify via Inspector CLI against the running server if feasible (`npx @modelcontextprotocol/inspector --cli`), else document the exact Inspector command in README and prove tools/list + tools/call over raw HTTP in the e2e test; README instructions land in Phase 5 regardless

**Git & conduct (locked)**
- Commits authored by the user's git identity only; NEVER any AI attribution; conventional commits `feat(03-XX): ...`
- No new runtime deps beyond the locked set (fastapi/fastmcp/uvicorn already pinned); 2-attempt stop rule

### Claude's Discretion
- server/ module layout (main.py/app.py/tools.py/db.py split), exact healthz field names
- Sort/filter vanilla-JS implementation details; visual design within the UI-SPEC (generated by gsd-ui-phase for this phase)
- Badge SVG styling; collision-disclosure response shape
- Whether `web/build.py` is imported by refresh or shells out (import preferred — keep refresh's exit-code contract)

### Deferred Ideas (OUT OF SCOPE)
- x402 payment gating — Phase 4 (design composition so ASGI middleware wraps cleanly; FREE set will be /healthz, /, /badge/*, MCP initialize/tools/list)
- README/deploy docs — Phase 5 (OPS-02)
- Scraper — Phase 5
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MCPS-01 | MCP server exposes exactly 4 tools | Verified composition pattern + `mcp.list_tools()`/in-memory `Client(mcp)` test patterns (§Code Examples 1, 6); tools/list round-trip proven live |
| MCPS-02 | All tool responses deterministic JSON incl. `generated_at`, `methodology_url` | TypedDict return pattern derives full `outputSchema`; `structuredContent` verified on the wire with real 3345 card incl. envelope fields (§Structured Output) |
| MCPS-03 | `/healthz` returns service health | Verified live: 200 JSON `{status, agents:272, scores:272, score_version, data_as_of}`; registered before mounts (§Code Examples 1) |
| MCPS-04 | `score_agent("这个能吃吗？")` and `score_agent("3345")` < 500 ms warm | Measured live over HTTP: median 39 ms, p95 41 ms, max 103 ms — 5–12x margin; timed-test recipe in §Performance |
| MCPS-05 | MCP Inspector lists and calls all 4 tools | Inspector 0.22.0 CLI verified against live server (tools/list + tools/call incl. CJK arg); exact commands + 3 Windows quirks + raw-HTTP fallback (§MCP Inspector) |
| WEB-01 | Single static HTML page at `/`, sortable, category filter, <2 s | 272-row page built from real DB: 117.8 KiB, sortable/filter JS passes `node --check`; full builder skeleton in §Leaderboard |
| WEB-02 | Methodology section + badge embed snippet | `id="methodology"` anchor + `/badge/{id}.svg` endpoint verified (200, image/svg+xml); snippet shape in §Badge |
| WEB-03 | Page auto-regenerates on indexer refresh | Wiring point in `indexer/refresh.py::_persist_records` after `compute_all`, preserving the 0/1/2 exit-code taxonomy (§Leaderboard → refresh wiring) |
| OPS-01 | `docker compose up` serves everything on one port | Exact Dockerfile/compose/.dockerignore/entrypoint lines in §Docker; CLI 29.5.2 + compose v5.1.4 present; **engine currently not running** (§Environment Availability) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Tech stack locked: Python 3.11+, FastAPI, FastMCP, SQLite stdlib, httpx, BeautifulSoup, uvicorn; pytest(+cov) dev-only. **No other runtime dependencies without asking** — everything below is stdlib or already-pinned deps.
- Scope discipline: no auth, accounts, extra databases, admin panels, dark mode.
- All outward-facing text neutral, factual, methodology-linked — never allegations (leaderboard copy, badge, error messages included; reuse `scoring.engine.DISCLAIMER` verbatim).
- Secrets via env vars only; `.env` gitignored; this phase introduces only `TRUSTLENS_BASE_URL` (default `http://localhost:8000`).
- Work only inside `trustlens/`; commits authored solely by the user's identity, no AI attribution.
- Stop conditions: no remote deploys, no deleting files, any error unresolved after 2 attempts → human review.
- GSD workflow enforcement: file changes go through `/gsd-execute-phase`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 4 MCP tools (lookup, compare, leaderboard slice, stats) | API/Backend (`server/tools.py`) | Database (read-only SELECTs) | Tools are thin read adapters over precomputed `scores`+`agents`; NEVER recompute (locked) |
| MCP transport (Streamable HTTP, sessions) | API/Backend (FastMCP `http_app` mounted in FastAPI) | — | fastmcp/mcp SDK owns protocol; app owns mounting + lifespan |
| `/healthz` | API/Backend (FastAPI route) | Database | Counts read per request; must stay free in Phase 4 |
| Leaderboard HTML generation | Offline pipeline (`web/build.py`, invoked by `indexer.refresh`) | Database | Build-time templating; server only serves bytes (WEB-03) |
| Leaderboard serving | API/Backend (StaticFiles mount at `/`, registered LAST) | CDN-none | Self-contained file; no external requests allowed |
| Sort/filter interactivity | Browser (inline vanilla JS) | — | Pure client-side DOM reordering; no framework (locked) |
| Badge SVG | API/Backend (`/badge/{id}.svg` route) | Database | Deterministic SVG from grade/score; registered before static |
| DB refresh / scoring | Offline pipeline (existing Phase 1-2 code) | — | Server never writes (locked) |
| Container packaging | Ops (Dockerfile + compose) | — | Entrypoint self-seeds DB from committed census CSV |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | everything | ✓ | 3.14.2 (repo installed `pip install -e`, global env) | — |
| fastmcp / fastmcp-slim | MCPS-01..05 | ✓ | 3.4.4 | — |
| mcp (SDK, transitive) | transport | ✓ | 1.28.1 | never import directly |
| fastapi / starlette | host app | ✓ | 0.139.0 / **1.3.1** | — (1.3.1 drives the mount fix) |
| uvicorn | server | ✓ | 0.51.0 | — |
| pydantic | schema derivation | ✓ | 2.13.4 | — |
| pytest / pytest-cov / coverage | tests | ✓ | 9.1.1 / 7.1.0 / 7.15.0 | — |
| node / npx | MCPS-05 Inspector | ✓ | v24.15.0 / 11.12.1 | raw-HTTP JSON-RPC fallback (§MCP Inspector) |
| @modelcontextprotocol/inspector | MCPS-05 | ✓ via npx | 0.22.0 (published 2026-07-03) | same fallback |
| Docker CLI + compose | OPS-01 | ✓ | 29.5.2 / compose v5.1.4 | — |
| **Docker engine (Docker Desktop)** | OPS-01 build/run | **✗ not running** | `docker info` → "failed to connect ... dockerDesktopLinuxEngine" | **Executor must start Docker Desktop before the OPS-01 task**; all non-Docker tasks proceed regardless |
| `data/trustlens.db` | tools/leaderboard | ✓ warm | 272 agents / 272 scores (121 scored, 151 NR); 3345 → 94/A/high | rebuild: `python -m indexer.refresh` |

**Missing dependencies with no fallback:** none (Docker engine is a start-the-app action, not an install).

**Windows console note:** the default console encoding is cp1252 — any script printing CJK agent names MUST call `sys.stdout.reconfigure(encoding="utf-8")` first (refresh.py already does this; PoC scripts crashed without it).

## Standard Stack

### Core (all verified installed at these exact versions)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastmcp | 3.4.4 [VERIFIED: pip list on this machine] | MCP server + `http_app()` | Locked; import `from fastmcp import FastMCP` |
| fastapi | 0.139.0 [VERIFIED: pip list] | Host app: healthz, badge, static, mount | Locked |
| starlette | 1.3.1 [VERIFIED: pip list] | Routing under FastAPI — **Mount semantics changed vs 0.x** | Transitive; drives the path fix |
| mcp | 1.28.1 [VERIFIED: pip list] | Protocol layer; supported protocol versions 2024-11-05, 2025-03-26, 2025-06-18, 2025-11-25 [VERIFIED: server 400 error message] | Never import/pin directly |
| uvicorn | 0.51.0 [VERIFIED: pip list] | ASGI server, one port | Locked |
| sqlite3 (stdlib) | 3.13/3.14 stdlib | Read-only store access | Locked |
| string.Template / html / json (stdlib) | stdlib | Leaderboard templating + escaping | Jinja2 forbidden |

**No `pip install` needed for this phase** — everything is already in the environment; `pyproject.toml` only needs `"server", "web"` added to `[tool.setuptools] packages`.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `McpPathRewrite` middleware (FIX A) | Exact `Route("/mcp", endpoint=mcp_app)` with `http_app(path="/mcp")`, no mount (FIX B) | FIX B verified working too, but `/mcp/` then 405s and it appends raw routes to FastAPI's router (less conventional). FIX A keeps the locked mount composition and serves both paths |
| `json_response=True` | Default SSE-format responses | Both verified live incl. Inspector; SSE requires a `data:`-line parser in every raw-HTTP test; JSON mode returns plain `application/json`. Recommend JSON mode |
| TypedDict returns | `dataclass` returns | dataclass also produces object schemas but instantiation is heavier and `dict`-shaped rows fit TypedDict naturally; TypedDict verified end-to-end |
| stateful sessions (default) | `stateless_http=True` | Stateless removes the session-id dance and the GET SSE channel (methods become POST/DELETE only) — simpler for pay-per-call, but the session flow is already proven and Inspector-tested; keep default for v1 (matches locked "one worker" plan) |

## The Mount Pattern — Corrected and Verified

### What was proven (PoC, this machine)

| Variant | POST /mcp | POST /mcp/ | GET / (static) | Verdict |
|---------|-----------|------------|----------------|---------|
| V1: locked pattern verbatim + static at `/` | **405** (StaticFiles swallows it) | 200 MCP | 200 | BROKEN for exact path |
| V2: locked pattern, no static | **307 → /mcp/** | 200 MCP | n/a | Redirect trap (drops POST bodies in some clients) |
| V3: **FIX A — locked pattern + `McpPathRewrite`** | **200 MCP** | **200 MCP** | 200 | **RECOMMENDED** |
| V4: FIX B — `http_app(path="/mcp")` + exact `Route`, no mount | 200 MCP | 405 | 200 | works; fallback option |

Root cause [VERIFIED: starlette 1.3.1 source + regex test]: `Mount("/mcp", ...)` compiles `path_regex = ^/mcp/(?P<path>.*)$` — bare `/mcp` does not match; with a catch-all static mount registered later, `/mcp` matches StaticFiles instead (405 for POST). FastMCP internally registers its endpoint as an exact `Route(streamable_http_path, methods=["GET","POST","DELETE"])` (stateful) [VERIFIED: fastmcp/server/http.py:608-631]. The official FastMCP FastAPI integration page itself writes the mounted endpoint URL with a trailing slash (`/analytics/mcp/`) and does not address the bare-path case [CITED: gofastmcp.com/integrations/fastapi]. Upstream reports of the 307 flavor: [CITED: github.com/modelcontextprotocol/python-sdk/issues/1168], [CITED: github.com/jlowin/fastmcp/issues/1364], [CITED: github.com/modelcontextprotocol/python-sdk/issues/1367].

### Phase-4 interaction (design now, pay later)

`app.add_middleware` is LIFO — the LAST-added middleware runs FIRST. Add `McpPathRewrite` first, then the Phase-4 `X402Middleware` after it, so x402 runs before the rewrite and sees both `/mcp` and `/mcp/` — its check must be `scope["path"].startswith("/mcp")` (already the ARCHITECTURE.md plan). Alternatively add x402 before the rewrite in code order; either works with `startswith`. Free-route set (`/healthz`, `/`, `/badge/*`) is untouched by the rewrite.

## Wire Protocol Reference (exact, verified live on uvicorn)

Headers required on EVERY request to `/mcp` (default SSE-format mode):

```
Content-Type: application/json
Accept: application/json, text/event-stream     <- BOTH values or the server 406s
```

Sequence (stateful mode, the default):

```
1) POST /mcp  {"jsonrpc":"2.0","id":1,"method":"initialize","params":{
       "protocolVersion":"2025-06-18","capabilities":{},
       "clientInfo":{"name":"e2e","version":"0"}}}
   -> 200, response header `mcp-session-id: <hex>`  (SAVE IT)
   -> body (default mode) is SSE: lines `event: message` / `data: {...InitializeResult...}`
   -> result.protocolVersion == "2025-06-18", result.serverInfo.name == FastMCP name

2) POST /mcp  {"jsonrpc":"2.0","method":"notifications/initialized"}
   + header `mcp-session-id: <hex>`
   -> 202, empty body

3) POST /mcp  {"jsonrpc":"2.0","id":2,"method":"tools/list"}
   + `mcp-session-id` -> 200, result.tools[] each with name/description/inputSchema/outputSchema

4) POST /mcp  {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{
       "name":"score_agent","arguments":{"agent_id_or_name":"这个能吃吗？"}}}
   + `mcp-session-id` -> 200, result = {content:[{type:"text",text:"<json>"}],
                                        structuredContent:{...card...}, isError:false}
```

`MCP-Protocol-Version: 2025-06-18` header on post-initialize requests is **optional** (omitting it works; an invalid value → 400 "Unsupported protocol version ... Supported versions: 2024-11-05, 2025-03-26, 2025-06-18, 2025-11-25") [VERIFIED: live probes]. Include it in tests for spec fidelity.

Negative matrix (verified — the assertions Phase 4 tests will build on):

| Request | Response |
|---------|----------|
| POST /mcp without `Accept: ...text/event-stream` | 406, JSON-RPC error -32600 "Not Acceptable" |
| POST /mcp valid Accept, no `mcp-session-id` (non-initialize) | 400, -32600 "Bad Request: Missing session ID" |
| POST /mcp empty body | 400, -32700 "Parse error" |
| GET /mcp without session | 400 (GET is the server-notification SSE channel; needs a session) |
| Bad `MCP-Protocol-Version` | 400, -32600 "Unsupported protocol version" |

SSE parsing helper for raw-HTTP tests (or set `json_response=True` and skip it):

```python
def mcp_json(resp) -> dict:
    """Extract the JSON-RPC message from a Streamable HTTP response."""
    if resp.headers.get("content-type", "").startswith("application/json"):
        return resp.json()
    for line in resp.text.splitlines():          # SSE frame: "data: {...}"
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise AssertionError(f"no JSON-RPC payload in response: {resp.text[:200]}")
```

**`json_response=True` (recommended):** `mcp.http_app(path="/", json_response=True)` returns plain `application/json` bodies for initialize/tools/list/tools/call (verified: identical results, still Streamable HTTP transport, still stateful, `Accept: application/json` alone then also accepted, and **Inspector CLI works against it** — verified live on port 8766). This does not violate the "never SSE" lock — that lock bans the legacy SSE *transport* (`transport="sse"`); `json_response` only selects the response format of the Streamable HTTP transport.

## Structured Output — the exact pattern for the 4 tools (MCPS-02)

**Derivation mechanics** [VERIFIED: fastmcp/tools/function_parsing.py:270-355 + wire tests]: FastMCP builds `outputSchema` from the return annotation with `TypeAdapter(T).json_schema(mode="serialization")`. Object-shaped types pass through; non-object types (e.g. `list[dict]`) are wrapped as `{"result": ...}` with `"x-fastmcp-wrap-result": true` and the wire `structuredContent` becomes `{"result": [...]}` — **avoid non-object returns**; every tool must return a dict-shaped type.

| Return annotation | Derived outputSchema | Verdict |
|---|---|---|
| `-> ScoreCard` (TypedDict) | Full `{properties: {...}, required: [all keys], type: "object"}`; `int \| None` → `anyOf[integer,null]`; `dict[str, Any]` field → `{type: object, additionalProperties: true}` | **USE THIS** |
| `-> dict` | `{"additionalProperties": true, "type": "object"}` — declared but vacuous | avoid |
| `-> list[dict]` | wrapped + `x-fastmcp-wrap-result` | avoid |

**Server-side output validation is ON** [VERIFIED]: a TypedDict-annotated tool returning a dict missing a required key produces `isError:true` "Output validation error: 'agent_id' is a required property". Therefore:
- Success paths return **exactly** the TypedDict shape — every envelope key present on every response (matches the FEATURES.md "no optional-key surprises" rule anyway). Use `typing.NotRequired[...]` only for genuinely conditional keys (e.g. collision disclosure).
- **Not-found is a `ToolError`, never a nonconforming dict:**

```python
from fastmcp.exceptions import ToolError

# verified wire result: {"content":[{"type":"text","text":"<this json>"}], "isError":true}
raise ToolError(json.dumps(
    {"error": "not_found",
     "query": query,
     "detail": "no agent matched by id, exact name, or normalized name",
     "candidates": closest,          # deterministic, may be []
     "methodology_url": methodology_url},
    ensure_ascii=False, sort_keys=True, separators=(",", ":")))
```

- **Never let plain exceptions escape a tool**: `raise ValueError("...internals...")` reaches the client verbatim as `Error calling tool 'x': ...internals...` [VERIFIED] — an info-disclosure bug. Wrap tool bodies so unexpected exceptions re-raise as a generic neutral `ToolError`.

**Verified card on the wire** (score_agent("这个能吃吗？") through the mounted HTTP app — CJK unescaped in both text block and structuredContent):

```json
"structuredContent": {"agent_id": "3345", "name": "这个能吃吗？", "category": "Lifestyle & Health",
  "score": 94, "grade": "A", "confidence": "high", "score_version": "1.0.0",
  "generated_at": "2026-07-10T00:00:00Z", "data_as_of": "2026-07-10T00:00:00Z",
  "methodology_url": "http://localhost:8000/#methodology",
  "disclaimer": "TrustScore is a statistical estimate computed from public marketplace data as of the stated snapshot; it is not a statement of fact about any vendor or agent.",
  "components": { "...5 components as stored in scores.components..." }},
"isError": false
```

**TypedDict skeletons for the 4 tools** (planner: give each tool its own TypedDict; `components` stays `dict[str, Any]` — the stored component blobs have heterogeneous `observed`/`benchmark` types):

```python
from typing import Any, NotRequired, TypedDict

class ScoreCard(TypedDict):
    agent_id: str
    name: str
    category: str
    score: int | None            # None for NR — anyOf[integer,null] in schema
    grade: str
    confidence: str
    score_version: str
    generated_at: str
    data_as_of: str
    methodology_url: str
    disclaimer: str
    components: dict[str, Any]   # 5 keys, each {score,weight,reason,observed,benchmark,flagged}
    marketplace: dict[str, Any]  # passthrough: sold, rating, positive_pct, price_usdt, tagline
    ambiguous_matches: NotRequired[list[dict[str, str]]]  # collision disclosure (2 real cases)

class CompareResult(TypedDict):
    agents: list[ScoreCard]
    component_winners: dict[str, str | None]   # component -> winning agent_id (None = tie)
    overall_winner: str | None
    generated_at: str
    methodology_url: str
    score_version: str
    data_as_of: str
    disclaimer: str

class CategoryLeaderboard(TypedDict):
    category: str
    entries: list[dict[str, Any]]   # rank, agent_id, name, score, grade, confidence
    total_in_category: int
    generated_at: str
    methodology_url: str
    score_version: str
    data_as_of: str
    disclaimer: str

class MarketplaceStats(TypedDict):
    agents_total: int
    scored: int
    not_rated: int
    grade_distribution: dict[str, int]
    category_counts: dict[str, int]
    median_price_usdt: float | None
    generated_at: str
    methodology_url: str
    score_version: str
    data_as_of: str
    disclaimer: str
```

`generated_at` determinism note: the scores table stamps `generated_at = data_as_of = "2026-07-10T00:00:00Z"` (verified in DB). Serve the STORED value — do not read the wall clock — and byte-determinism (locked requirement "deterministic JSON") holds for free.

Input-validation behavior worth a test: FastMCP validates arguments strictly — calling `score_agent` with integer `3345` yields `isError:true` "Input should be a valid string" [VERIFIED via Inspector arg coercion]. That is conforming behavior, not a bug.

## MCP Inspector (MCPS-05) — exact commands, verified on this machine

Server must be running (`uvicorn server.main:app --port 8000`). Inspector 0.22.0 auto-negotiates Streamable HTTP from a plain URL — **no transport flag needed**:

```bash
# tools/list — verified output: all tools with name/description/inputSchema/outputSchema
npx --yes @modelcontextprotocol/inspector --cli http://127.0.0.1:8000/mcp --method tools/list

# tools/call — numeric-looking strings NEED embedded JSON quotes (see quirk 2)
npx --yes @modelcontextprotocol/inspector --cli http://127.0.0.1:8000/mcp \
  --method tools/call --tool-name score_agent --tool-arg 'agent_id_or_name="3345"'

# CJK works through Git Bash (verified: resolves to 3345, isError:false)
npx --yes @modelcontextprotocol/inspector --cli http://127.0.0.1:8000/mcp \
  --method tools/call --tool-name score_agent --tool-arg 'agent_id_or_name=这个能吃吗？'
```

**Windows quirks (all observed here):**
1. **Exit code is unreliable**: node crashes at teardown with `Assertion failed: !(handle->flags & UV_HANDLE_CLOSING), file src\win\async.c, line 76` (native 0xC0000409, surfaces as exit 1) AFTER printing complete valid JSON to stdout. Any scripted MCPS-05 check must **assert on parsed stdout, never on exit code**.
2. **`--tool-arg key=value` JSON-parses the value**: `agent_id_or_name=3345` arrives as integer 3345 → FastMCP strict validation → `isError:true "Input should be a valid string"`. Use `'agent_id_or_name="3345"'` (single-quoted for the shell, embedded double quotes).
3. **Without `--cli` the Inspector launches UI mode** (proxy on ports 6274/6277 + browser) and blocks forever — in scripts ALWAYS pass `--cli`. There is no `--version` flag (it's treated as a server command and starts UI mode).
4. GUI alternative for the demo: `npx @modelcontextprotocol/inspector`, transport "Streamable HTTP", URL `http://127.0.0.1:8000/mcp`.

**Raw-HTTP fallback** (if npx is unavailable on a reviewer's machine — also the shape of the in-process e2e test): the 4-step JSON-RPC sequence from §Wire Protocol via curl:

```bash
curl -s -i -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
# grab mcp-session-id from response headers, then repeat with -H "mcp-session-id: <id>"
```

## Performance (MCPS-04) — measured

| Path | min | median | p95 | max |
|------|-----|--------|-----|-----|
| tools/call score_agent("这个能吃吗？") over live HTTP (30 calls, warm) | 33.6 ms | **38.7 ms** | 40.5 ms | 45.9 ms |
| tools/call score_agent("3345") over live HTTP | 36.9 ms | 42.3 ms | — | 102.6 ms |
| direct function call (no HTTP) | 17.4 ms | 22.6 ms | — | 55.4 ms |
| fresh `sqlite3.connect(mode=ro URI)` + first query | 16.7 ms | 20.8 ms | — | 26.8 ms |
| fresh plain-path connect + first query | 7.5 ms | 10.3 ms | — | 25.5 ms |
| query on warm connection | — | **0.11 ms** | — | — |

Reading: virtually all latency is Windows fresh-connection first-query cost (schema parse + file open, likely AV-scanned), NOT the query. Connection-per-request stays the right call (locked; 20 ms ≪ 500 ms; Linux/Docker will be faster). Do not add pooling.

**Timed-test recipe** (through the in-process HTTP app so the full mount/session stack is measured):

```python
def test_score_agent_under_500ms(client, session_headers):  # TestClient from `with` fixture
    body = call_body("score_agent", {"agent_id_or_name": "这个能吃吗？"})
    client.post("/mcp", headers=session_headers, content=body)      # 1 warm-up call
    for arg in ("这个能吃吗？", "3345"):
        t0 = time.perf_counter()
        r = client.post("/mcp", headers=session_headers, content=call_body("score_agent", {"agent_id_or_name": arg}))
        elapsed = time.perf_counter() - t0
        assert r.status_code == 200 and elapsed < 0.5    # observed ~0.04s; 12x margin
```

## Leaderboard (WEB-01..03) — prototyped against the real DB

**Measured:** 272 rows → **120,650 bytes (117.8 KiB)** single self-contained file; sortable/filter inline JS (~45 lines) passes `node --check`; CJK names render; `0.000015` and the real minimum price `0.000001` format correctly; NR rows sort after scored rows; 9 category options; `id="methodology"` anchor and badge snippet present. <2 s load is trivial at this size.

**Structure that worked (transcribe from PoC `build_leaderboard.py`):**
- One `string.Template` for the page (`$rows`, `$category_options`, `$agent_count`, `$data_as_of`, `$score_version`, `$disclaimer`, `$weight_items`, `$base_url`). NOTE: the inline `<script>` uses `$`-free JS (or `$$` escapes) — the PoC JS avoids `$` entirely; keep it that way or `Template.substitute` raises.
- Row construction via one `ROW.format(...)` f-string-style template per agent with `html.escape(value)` for text and `html.escape(value, quote=True)` for attributes (agent names contain quotes/CJK — escaping is mandatory).
- SQL: `SELECT ... FROM agents a JOIN scores s ON s.agent_id = a.id ORDER BY (s.score IS NULL), s.score DESC, a.id` — puts NR after scored deterministically.
- Sort/filter mechanism: every `<tr>` carries `data-rank/name/category/score/grade/sold/rating/price` attributes; `<th data-k="score" data-t="n">` headers; click handler sorts the cached row array (`''` → `-Infinity` so missing values sink), re-appends rows, ties broken by original rank; `<select id="cat">` filter toggles `row.style.display`. No framework, no external requests.
- Number formatting: `f"{price:.6f}".rstrip("0").rstrip(".")` renders `1.5e-05` → `0.000015` and `1e-06` → `0.000001` (6 decimals covers the census minimum — verified); `f"{sold:,}"` for thousands; em dash `—` for missing values with empty `data-` attr.
- CJK-safe font stack (no webfonts): `system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",sans-serif` + `font-variant-numeric: tabular-nums` on numeric columns.
- Neutral grade colors (muted greens→browns→grey, no alarm red): A `#2f6f4f`, B `#4f7f5f`, C `#6f7f4f`, D `#7f6f4f`, F `#7f5f4f`, NR `#5f6570` (final palette subject to UI-SPEC).
- Methodology section content pulls constants from `scoring.engine`: `WEIGHTS` (import from `scoring.components` via `scoring`), `GRADE_BANDS`, `SCORE_VERSION`, `DISCLAIMER`, `GRADE_DESCRIPTIONS` + derived-category disclosure + "agents cannot pay to alter scores".

**refresh wiring (WEB-03) — preserve the exit-code contract:**
- `web/build.py` exposes `build(db_path: str | Path, out_path: str | Path, base_url: str = "http://localhost:8000") -> int` (returns bytes written; opens its own read-only connection; pure read).
- Import at top of `indexer/refresh.py` (import preferred — locked discretion note) and call in `_persist_records` AFTER the `with conn:` transaction commits and `conn.close()` runs (build reads committed rows via its own connection):

```python
# in _persist_records, after finally: conn.close()
size = web_build(db_path, out_path)          # web.build.build
log.info("leaderboard built: %s (%d agents, %d bytes)", out_path, len(records), size)
```

- Failure taxonomy: wrap the build call in the existing `main()` db-side `except (OSError, sqlite3.Error)` → exit 2 (a build failure is an environment problem, same as a DB failure). `refresh()`/`_persist_records` gain an optional `web_out: Path | None = DEFAULT_WEB_OUT` parameter; **tests pass `tmp_path`-based `web_out`** so the existing determinism tests never write into the repo (also update existing refresh tests' call sites or default to a path derived from `db_path.parent` — planner's choice; the tmp-param approach is cleaner).
- `.gitignore` additions: `web/dist/`.
- Byte-determinism: builder reads only DB values + constants — rerunning refresh must produce byte-identical HTML (extend the existing rerun-hash test to cover the HTML file).

## Badge SVG (WEB-02) — verified endpoint

Deterministic stdlib f-string SVG (~15 lines), shields-style two-panel, `image/svg+xml`, `Cache-Control: max-age=3600`; unknown id → neutral "unknown" badge (never 404 for embeds). Verified 200 + valid SVG for agent 3345 ("A 94"). Registered as a FastAPI route BEFORE the static mount. Width formula `62 + 10 + 7*len(label)` keeps text inside. Embed snippet on the page:

```html
<a href="{BASE_URL}/#agent-AGENT_ID">
  <img src="{BASE_URL}/badge/AGENT_ID.svg" alt="TrustLens score" height="20">
</a>
```

Each leaderboard `<tr>` gets `id="agent-{id}"` so the badge link target resolves (verified in PoC page).

## Docker (OPS-01) — exact files

`docker info` currently fails (engine down) — **start Docker Desktop first**, then verify with `docker info | grep "Server Version"`. Compose v5.1.4 supports `env_file: required: false` (needs ≥2.24). [VERIFIED: CLI versions on this machine; container run NOT executed — engine down]

```dockerfile
# Dockerfile
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml .
COPY indexer/ indexer/
COPY scoring/ scoring/
COPY server/ server/
COPY web/ web/
COPY data/okx-marketplace-census-2026-07-10.csv data/
RUN pip install --no-cache-dir .
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"
CMD ["/bin/sh", "-c", "[ -f data/trustlens.db ] && [ -f web/dist/index.html ] || python -m indexer.refresh; exec uvicorn server.main:app --host 0.0.0.0 --port 8000"]
```

```yaml
# docker-compose.yml
services:
  trustlens:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - path: .env
        required: false        # tolerant of absence (locked); compose >= 2.24
```

```
# .dockerignore
.git
.planning
.claude
.venv
__pycache__
*.py[cod]
.pytest_cache
.coverage
htmlcov
*.egg-info
tests
web/dist
data/*.db
data/*.db-wal
data/*.db-shm
data/cache
.env
```

Notes: `data/*.db` is dockerignored deliberately — the entrypoint's `python -m indexer.refresh` seeds DB **and** leaderboard from the committed census CSV inside the container (offline, ~seconds, byte-deterministic per Phase 2 verification), so images are reproducible and never bake a stale local DB. The dual `[ -f ... ]` guard covers both artifacts (dist is dockerignored too). `--host 0.0.0.0` is mandatory in-container. Windows verification steps for the executor: (1) start Docker Desktop, wait for "Engine running"; (2) `docker compose up --build`; (3) `curl http://localhost:8000/healthz`, browse `http://localhost:8000/`, run the Inspector CLI against `http://localhost:8000/mcp`; (4) `docker compose down`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP protocol/session handling | Custom JSON-RPC router | `mcp.http_app()` (FastMCP) | Session manager, Accept negotiation, protocol-version handling all verified working |
| Output schemas | Hand-written JSON Schema dicts | TypedDict return annotations | Derivation verified; hand-written schemas drift from actual returns and FastMCP validates against them server-side |
| Not-found responses | Custom error envelope dict returned from tool | `raise ToolError(json.dumps(...))` | Nonconforming returns are REJECTED by output validation (verified); ToolError is the spec channel |
| Lifespan combination | Custom asynccontextmanager stack | `fastmcp.utilities.lifespan.combine_lifespans` | Verified working; documented enter-in-order/exit-reverse semantics |
| HTML escaping | Regex/replace chains | stdlib `html.escape(s)` / `html.escape(s, quote=True)` | Agent names contain quotes, `<`, CJK, newlines in taglines |
| SVG badge | Image libs / shields.io dependency | f-string SVG template | Verified deterministic; external badge = external dependency on the credibility artifact |
| Trailing-slash handling | Nginx/proxy rules, client-side `-L` | `McpPathRewrite` ASGI middleware (5 lines) | Verified; keeps one process, no redirect in any client |

## Common Pitfalls (Phase-3-specific, all reproduced or disproven here)

### Pitfall 1: Bare `/mcp` 405s once static is mounted (the 307 trap's worse sibling)
**What goes wrong:** V1 locked pattern + static at `/` → `POST /mcp` = 405 from StaticFiles; no 307 is even issued because static matches first. Inspector pointed at `/mcp` still works (it follows the MCP client redirect/normalization in some paths — but curl/httpx and the OKX check do not).
**How to avoid:** `McpPathRewrite` middleware (verbatim in Code Examples). **Warning sign:** route-order test passes for `/mcp/` but a `curl -i -X POST /mcp` shows 405/307.

### Pitfall 2: Skipping the `with` block on TestClient
**What goes wrong:** `TestClient(app).post("/mcp", ...)` without `with` → 500 `RuntimeError: FastMCP's StreamableHTTPSessionManager task group was not initialized... ensure you are setting lifespan=mcp_app.lifespan` [VERIFIED — exact message].
**How to avoid:** every server test uses `with TestClient(app) as client:` (fixture-ize it); one dedicated test asserts the mounted path works, which simultaneously proves lifespan wiring.

### Pitfall 3: Plain exceptions leak internals to paying clients
**What goes wrong:** FastMCP 3.4.4 forwards non-ToolError exception text verbatim: `Error calling tool 'x': no agent matched 'nope' -- secret internals here` [VERIFIED].
**How to avoid:** tool bodies catch unexpected exceptions and re-raise neutral `ToolError`; not-found path raises `ToolError` with the deterministic JSON message. Add a test asserting an unknown-agent call yields `isError:true` with the neutral envelope and no traceback text.

### Pitfall 4: Violating your own outputSchema
**What goes wrong:** returning a dict missing a declared TypedDict key → `isError:true "Output validation error"` at runtime (e.g. an NR card built without `marketplace` key) [VERIFIED mechanism].
**How to avoid:** one card-builder function produces every ScoreCard (scored, NR, collision) so all required keys are always present; schema tests call each tool through `Client(mcp)` for NR and scored agents.

### Pitfall 5: Inspector scripting on Windows trusts exit codes
**What goes wrong:** libuv teardown assertion → nonzero exit AFTER correct output; `--tool-arg x=3345` silently becomes an int; missing `--cli` hangs the script on UI mode.
**How to avoid:** parse stdout JSON; quote numeric strings `'x="3345"'`; always `--cli`. (Full detail in §MCP Inspector.)

### Pitfall 6: `string.Template.substitute` vs `$` in inline JS/CSS
**What goes wrong:** any `$` in the page template (JS `$(...)`, `${}`, CSS) raises `ValueError: Invalid placeholder`.
**How to avoid:** keep inline JS `$`-free (PoC style: `document.querySelector`, string concat) or use `$$` escapes; a build test that runs the builder catches this instantly.

### Pitfall 7: refresh determinism tests start writing into the repo
**What goes wrong:** wiring `web.build` into `_persist_records` makes every existing refresh test emit `web/dist/index.html` at the repo path.
**How to avoid:** output path is a parameter; tests pass `tmp_path / "index.html"`; default only applies to the CLI.

### Pitfall 8: Windows console cp1252 crashes on CJK
**What goes wrong:** printing agent names / structuredContent in tests or scripts → `UnicodeEncodeError: 'charmap' codec` (hit multiple times during this research).
**How to avoid:** `sys.stdout.reconfigure(encoding="utf-8")` in any script that prints DB content (refresh.py already does); pytest itself is fine (captures without console encoding).

### Pitfall 9: sqlite URI path with spaces
**What goes wrong:** hand-built `f"file:{path}?mode=ro"` breaks on this repo's space-containing absolute path.
**How to avoid:** `Path(db_path).resolve().as_uri() + "?mode=ro"` [VERIFIED working] — percent-encodes spaces correctly; keep relative default `data/trustlens.db` resolved from CWD or env.

## Code Examples

### 1. server composition — VERIFIED VERBATIM (transcribe)

```python
# server/app.py  (source: working PoC, this machine, 2026-07-11)
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastmcp.utilities.lifespan import combine_lifespans

from server.tools import mcp   # FastMCP("TrustLens") + the 4 @mcp.tool functions


class McpPathRewrite:
    """starlette>=1.0 Mount matches only /mcp/*; rewrite exact /mcp -> /mcp/ (no 307/405)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
            scope["raw_path"] = b"/mcp/"
        await self.app(scope, receive, send)


def create_app() -> FastAPI:
    mcp_app = mcp.http_app(path="/", json_response=True)   # Streamable HTTP, JSON bodies

    @asynccontextmanager
    async def app_lifespan(app):
        # startup checks (DB present etc.) go here
        yield

    app = FastAPI(title="TrustLens",
                  lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan))

    @app.get("/healthz")
    def healthz(): ...                                # 200/503 JSON, before mounts

    @app.get("/badge/{agent_id}.svg")
    def badge(agent_id: str) -> Response: ...         # before static

    app.mount("/mcp", mcp_app)                        # before static
    app.mount("/", StaticFiles(directory="web/dist", html=True), name="site")  # LAST
    app.add_middleware(McpPathRewrite)                # AFTER mounts is fine (middleware
    return app                                        # always runs before routing)
```

Run: `uvicorn server.main:app --host 0.0.0.0 --port 8000` (`server/main.py`: `app = create_app()`).

### 2. read-only connection (space-safe URI) — VERIFIED

```python
import sqlite3
from pathlib import Path

def connect_ro(db_path: str | Path) -> sqlite3.Connection:
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"   # handles spaces in repo path
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn
```

### 3. lookup ladder facts — VERIFIED against the DB
- `"3345"` → id exact hit; `"这个能吃吗？"` → name exact hit; NFKC fold handles the ASCII-`?` variant via the indexed `name_key` column (populated at ingest).
- The 2 real collisions [VERIFIED by GROUP BY]: `人生说明书 · life book` → ids **4517, 4353**; `链上任务助手` → ids **2791, 2662**. Deterministic resolution: `ORDER BY id LIMIT 1` (or lowest id) + `ambiguous_matches` disclosure listing all colliding `{agent_id, name}` (shape is Claude's discretion).

### 4. e2e test skeleton (raw JSON-RPC through the mounted app) — VERIFIED sequence

```python
H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

def test_mcp_e2e():
    with TestClient(create_app()) as client:              # `with` = lifespan runs
        r = client.post("/mcp", headers=H, content=json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "e2e", "version": "0"}}}))
        assert r.status_code == 200
        sess = {**H, "mcp-session-id": r.headers["mcp-session-id"],
                "MCP-Protocol-Version": "2025-06-18"}
        client.post("/mcp", headers=sess, content=json.dumps(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}))   # 202
        r = client.post("/mcp", headers=sess, content=json.dumps(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
        tools = mcp_json(r)["result"]["tools"]            # helper from §Wire Protocol
        assert sorted(t["name"] for t in tools) == [
            "category_leaderboard", "compare_agents", "marketplace_stats", "score_agent"]
        assert all(t.get("outputSchema") for t in tools)
```

Route-order test (3 asserts): `/healthz` → JSON 200; `POST /mcp` (bare, no session) → **400 JSON-RPC** (NOT 405/307/HTML — this single assert proves the rewrite works); `/` → HTML 200.

### 5. cheap-tier tests — VERIFIED patterns

```python
# (a) direct call: @mcp.tool returns the plain function (verified: type is `function`)
card = score_agent("3345"); assert card["grade"] == "A" and card["score"] == 94

# (b) server-side introspection (async): exactly 4 tools with schemas
tools = await mcp.list_tools()          # -> list[Tool]; t.name, t.output_schema

# (c) in-memory client (no HTTP, no lifespan wiring needed)
async with Client(mcp) as c:            # from fastmcp import Client
    res = await c.call_tool("score_agent", {"agent_id_or_name": "3345"})
    assert res.is_error is False and res.structured_content["grade"] == "A"
```

pytest async config: FastMCP already depends on `anyio`; simplest is to keep in-memory-Client tests inside `asyncio.run(...)` wrappers OR add `pytest-asyncio` — **NOT currently installed and dev-deps also need approval discipline; prefer `asyncio.run()` in sync tests (zero new deps, verified pattern in this research).**

### 6. timing + Inspector + Docker commands — see §Performance, §MCP Inspector, §Docker (already exact).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Starlette 0.x `Mount` matched bare mount path (with redirect) | starlette 1.x Mount regex requires trailing segment (`^/p/(?P<path>.*)$`) | starlette 1.0 (2025) | THE mount fix in this phase |
| FastMCP v2 `mask_error_details` default behavior assumptions | v3.4.4 forwards plain exception text to clients; ToolError is the safe channel | FastMCP 3.x | Wrap tool exceptions |
| MCP protocol 2025-03-26 | mcp 1.28.1 negotiates up to 2025-11-25; requirement pins 2025-06-18 compliance (supported) | 2025-2026 | Send `protocolVersion: "2025-06-18"` in initialize |
| Inspector needed explicit transport flags | 0.22.0 `--cli <url>` auto-detects Streamable HTTP | 2026 | Simpler MCPS-05 commands |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Inspector GUI (browser mode) connects as cleanly as the verified CLI mode | MCP Inspector | Demo-day friction only; CLI evidence already satisfies MCPS-05; GUI rehearsal happens in Phase 5 demo prep |
| A2 | `python:3.13-slim` container behaves like the local 3.14.2 env for these deps (all ship wheels; STACK.md verified floors) | Docker | Low — pip resolution differences would surface at image build; fallback `python:3.13.14-slim` pin |
| A3 | OKX marketplace clients tolerate stateful sessions (initialize handshake) — same assumption Phase 4's FREE_METHODS design already makes | Wire Protocol | If OKX's runtime is stateless-only, flip to `stateless_http=True` (one line; methods become POST/DELETE; session tests change) |
| A4 | The UI-SPEC (not yet generated) will fit the verified page skeleton (table + controls + methodology + badge sections) | Leaderboard | Visual-only rework; data/JS mechanics unaffected |

## Open Questions

1. **Exact default for `web_out` in `refresh()` signature** — tmp-param approach vs deriving from `--db` parent. Planner picks; both preserve determinism tests (Pitfall 7 shows the constraint).
2. **`json_response=True` vs default SSE** — both fully verified incl. Inspector. Research recommends JSON mode (simpler tests, simpler Phase-4 curl semantics); if the planner keeps default SSE, use the `mcp_json()` helper everywhere. Not a blocker either way.
3. **Docker engine verification** — container run could not be executed (engine down). The files above are assembled from verified primitives (base image facts, compose version, refresh idempotency); first `docker compose up --build` happens in-phase with the executor after starting Docker Desktop.

## Security Domain

### Applicable ASVS Categories (L1)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (x402 IS access control, Phase 4; brief forbids auth) | — |
| V3 Session Management | partial | MCP session ids are transport-level, generated by mcp SDK (verified hex tokens); no user sessions |
| V4 Access Control | no (all Phase-3 routes intentionally public) | Phase 4 adds the payment gate |
| V5 Input Validation | yes | FastMCP/pydantic strict arg validation (verified: wrong type → isError, no crash); SQL always parameterized `?` (existing repo convention); `limit` param bounded in tool code |
| V6 Cryptography | no | — |
| V12 API/Web Service | yes | Neutral `ToolError` envelope — **never leak exception internals (verified leak with plain exceptions — Pitfall 3)**; no stack traces in responses |
| V14 Config | yes | `TRUSTLENS_BASE_URL` env with safe default; no secrets this phase; `.env`/`.dockerignore` hygiene above |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via agent_id_or_name / category | Tampering | Parameterized queries only (repo-wide locked convention; PoC used `?` everywhere) |
| XSS via agent names/taglines in generated HTML | Tampering | `html.escape()` on every interpolated value, `quote=True` in attributes (names really contain quotes + CJK) |
| Info disclosure via tool exceptions | Information Disclosure | ToolError-only error channel; generic wrapper for unexpected exceptions |
| DNS-rebinding on local MCP servers | Spoofing | fastmcp 3.4.4 `host_origin_protection` available; default False verified — acceptable for a public paid API behind HTTPS; do NOT enable blindly (would need `allowed_hosts` for the deploy domain) |
| Badge endpoint as scraping oracle / cache stampede | DoS | Deterministic 200s + `Cache-Control`; 272-id space is tiny; no action needed |

## Sources

### Primary (HIGH confidence — executed on this machine, 2026-07-11)
- Working PoC (scratchpad): FastMCP 3.4.4 + FastAPI 0.139.0 mount matrix (405/307/200), full JSON-RPC handshake via TestClient AND live uvicorn, outputSchema derivation per annotation style, structuredContent wire shapes, ToolError/ValueError/output-validation behavior, `combine_lifespans`, no-lifespan RuntimeError message, timing (39 ms median), leaderboard build (117.8 KiB/272 rows/`node --check`), badge endpoint, sqlite URI-with-spaces, collision rows, cp1252 crashes
- Installed package sources: `fastmcp/tools/function_parsing.py` (schema derivation), `fastmcp/tools/base.py` (ToolResult/structured content), `fastmcp/server/http.py` (exact Route registration, methods, lifespan, host_origin_protection default False), `starlette/routing.py` (Mount regex `^/mcp/(?P<path>.*)$`)
- MCP Inspector 0.22.0 via npx: tools/list + tools/call (id, quoted-string, CJK) against live server; UI-mode hang; libuv teardown assertion; arg JSON-coercion
- Live environment: pip list, node/npx/docker/compose versions, `docker info` engine-down state, real `data/trustlens.db` counts and goldens

### Secondary (HIGH-MEDIUM — official docs/issues, fetched 2026-07-11)
- https://gofastmcp.com/integrations/fastapi — current mount + lifespan + combine_lifespans guidance; doc's own mounted URL shown with trailing slash
- https://github.com/modelcontextprotocol/python-sdk/issues/1168, https://github.com/jlowin/fastmcp/issues/1364, https://github.com/modelcontextprotocol/python-sdk/issues/1367 — upstream 307/trailing-slash reports corroborating the PoC
- `.planning/research/STACK.md`, `PITFALLS.md`, `ARCHITECTURE.md`, `FEATURES.md` (2026-07-10) — version locks, x402 Phase-4 shapes, envelope conventions

### Tertiary
- none required — no unverified WebSearch claims made it into recommendations

## Metadata

**Confidence breakdown:**
- Mount/lifespan/wire protocol: HIGH — executed, both TestClient and live uvicorn
- Structured output pattern: HIGH — executed incl. failure modes
- Inspector (MCPS-05): HIGH — executed with real commands; GUI mode ASSUMED (A1)
- Timing: HIGH — measured; Linux numbers will differ (faster)
- Leaderboard/badge: HIGH — built from real DB and content-verified; visual polish pending UI-SPEC
- Docker: MEDIUM-HIGH — files assembled from verified primitives; container not run (engine down)

**Research date:** 2026-07-11
**Valid until:** 2026-07-25 (pinned versions; recheck only if fastmcp/starlette pins change)
