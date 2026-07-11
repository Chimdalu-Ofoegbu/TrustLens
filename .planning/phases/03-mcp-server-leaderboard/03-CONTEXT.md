# Phase 3: MCP Server & Leaderboard - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning
**Source:** PRD Express Path (../trustlens-claude-code-prompt.md) + Phases 1-2 reality

<domain>
## Phase Boundary

Deliver the online product surface: a FastAPI app hosting the FastMCP server (exactly 4 tools), `/healthz`, and the static leaderboard page at `/` — all on ONE port, dockerized (`docker compose up`). Serves precomputed scores from the Phase 2 `scores` table read-only; NO payment gating yet (Phase 4 wraps this working service). Requirements: MCPS-01..05, WEB-01..03, OPS-01.

</domain>

<decisions>
## Implementation Decisions

### App composition (locked — from verified STACK/ARCHITECTURE research)
- `server/` package with a `create_app()` factory: FastMCP 3.4.4 (`from fastmcp import FastMCP`), `mcp_app = mcp.http_app(path="/")`, mounted at `/mcp`, with the MCP app's lifespan passed to FastAPI (the #1 documented mounting mistake is omitting it) — combine lifespans if the app needs its own
- Route registration order: `/healthz` and `/mcp` BEFORE the static mount at `/` (Starlette matches in registration order; static-at-/ registered last)
- One port (default 8000), plain `uvicorn`; Streamable HTTP transport only (never SSE); test both `/mcp` and `/mcp/` for the 307 trailing-slash edge
- Read-only DB access: connection-per-request against `data/trustlens.db` (WAL), sqlite3 stdlib; the server NEVER writes and NEVER recomputes scores

### The 4 tools (locked verbatim from the brief — no more, no fewer)
1. `score_agent(agent_id_or_name)` — full score card
2. `compare_agents(ids: list)` — cards + per-component winners
3. `category_leaderboard(category, limit=10)` — ranked slice
4. `marketplace_stats()` — aggregate stats
- Every response: deterministic JSON including `generated_at`, `methodology_url`, plus the Phase 2 envelope (score_version, data_as_of, confidence, disclaimer) — values read from the scores/agents tables, not recomputed
- MCP 2025-06-18 compliance: tools declare `outputSchema` and return conforming `structuredContent` (FastMCP v3 derives schemas from type annotations — researcher verifies the exact pattern)
- Lookup semantics for `score_agent`: id exact match → name exact → NFKC-casefolded `name_key` match; MUST resolve both `"3345"` and `"这个能吃吗？"`; name_key collisions (2 real ones exist) resolve deterministically with the ambiguity disclosed in the response
- Unknown agent → structured not-found error JSON (neutral wording), never a crash
- NR agents: score card with grade "NR", score null, confidence low, honest reasons — a valid, sellable answer

### Leaderboard (locked — WEB-01..03 + brief verbatim)
- Single static HTML page, inline CSS/JS, NO framework, NO external requests (fonts/CDNs) — self-contained bytes
- Generated from SQLite by the refresh pipeline (stdlib `string.Template` or f-string templating — Jinja2 is NOT an allowed dep): builder module (`web/build.py`) invoked at the end of `indexer.refresh` (WEB-03) writing `web/dist/index.html` (gitignored)
- Content: ranked table of ALL agents (sortable columns incl. score, sold, rating, price, category; ranked by TrustScore desc, NR agents listed after scored ones), grade badges, category filter dropdown, "About the methodology" section (`id="methodology"` anchor: component weights, grade bands, NR rule, score_version, data_as_of, disclaimer, derived-category disclosure), "TrustLens Verified" badge embed snippet (self-hosted SVG endpoint `/badge/{agent_id}.svg` + copyable HTML snippet)
- Loads <2s: trivial for a static file — keep total page weight sane (no images beyond inline SVG)
- Neutral presentation: grade colors neutral/analytic (no alarmist red "danger" styling), all copy factual with methodology links; NO dark mode (brief exclusion)
- `methodology_url` = `{TRUSTLENS_BASE_URL}/#methodology` with env `TRUSTLENS_BASE_URL` defaulting to `http://localhost:8000`

### /healthz (locked — MCPS-03)
- JSON: status, agent count, score count, score_version, data_as_of; 200 when DB present with scores, 503 otherwise; never payment-gated (Phase 4 must keep it free)

### Docker (locked — OPS-01)
- `Dockerfile` on `python:3.13-slim`; `docker-compose.yml` serving everything on one port
- Container start: entrypoint ensures DB exists (runs `python -m indexer.refresh` if `data/trustlens.db` missing — offline CSV seed works in-image), then `uvicorn server.main:app`
- `.env` optional at this phase (compose `env_file` wired but tolerant of absence); full `.env.example` lands in Phase 4 with the payment vars

### Performance (locked — MCPS-04)
- `score_agent("这个能吃吗？")` and `score_agent("3345")` return full score cards in <500ms from a warm DB — enforce with a timed test (generous CI margin, e.g. assert < 500ms after one warm-up call)

### Tests (locked)
- MCP tool schema tests: `tools/list` returns exactly 4 tools with expected names/schemas; tool calls return the envelope fields; direct function-call unit tests (FastMCP v3 `@mcp.tool` returns the plain function) + one in-process e2e through the HTTP app (`with TestClient(app):` — lifespan context REQUIRED)
- healthz, leaderboard build (all 272 rows present, filter/sort hooks in DOM, methodology anchor, badge snippet), lookup edge cases (CJK, id, collision, not-found), perf smoke
- Full suite green; scoring/ coverage gate unaffected (server tests run with the gate active — measure scoring only, per existing pyproject)
- MCPS-05 (MCP Inspector lists/calls all 4 tools): node 24 + npx available — verify via Inspector CLI against the running server if feasible (`npx @modelcontextprotocol/inspector --cli`), else document the exact Inspector command in README and prove tools/list + tools/call over raw HTTP in the e2e test; README instructions land in Phase 5 regardless

### Git & conduct (locked)
- Commits authored by the user's git identity only; NEVER any AI attribution; conventional commits `feat(03-XX): ...`
- No new runtime deps beyond the locked set (fastapi/fastmcp/uvicorn already pinned); 2-attempt stop rule

### Claude's Discretion
- server/ module layout (main.py/app.py/tools.py/db.py split), exact healthz field names
- Sort/filter vanilla-JS implementation details; visual design within the UI-SPEC (generated by gsd-ui-phase for this phase)
- Badge SVG styling; collision-disclosure response shape
- Whether `web/build.py` is imported by refresh or shells out (import preferred — keep refresh's exit-code contract)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project & requirements
- `.planning/PROJECT.md` — constraints, stop conditions
- `.planning/REQUIREMENTS.md` — MCPS-01..05, WEB-01..03, OPS-01

### Research (verified 2026-07-10)
- `.planning/research/STACK.md` — FastMCP 3.4.4 mount pattern (verbatim code), what NOT to use, Docker base
- `.planning/research/ARCHITECTURE.md` — app composition, free-route set, one-port layout
- `.planning/research/PITFALLS.md` — lifespan/`/mcp/mcp`/307 traps, TestClient lifespan, MCP Inspector gotchas
- `.planning/research/FEATURES.md` — outputSchema/structuredContent MUST, badge conventions, methodology-page norms

### Phase 1-2 outputs (the substrate)
- `indexer/db.py` (connect/init_db), `indexer/refresh.py` (wire web build at the end; preserve exit-code contract + determinism tests), `scoring/engine.py` (DISCLAIMER, SCORE_VERSION, GRADE_BANDS constants for the methodology section), `scoring/persist.py` (scores table shape)
- `.planning/phases/02-scoring-engine/02-VERIFICATION.md` — the served contract: 272 rows, 121 scored/151 NR, distribution pins
- UI-SPEC.md in this phase directory (once generated) — visual/interaction contract for the leaderboard

</canonical_refs>

<specifics>
## Specific Ideas

- Brief verbatim: "exactly 4 tools"; "All return deterministic JSON with a `generated_at` field and a `methodology_url`"; "single static HTML page (inline CSS/JS, no framework) served by FastAPI at `/`"; "Auto-regenerated from SQLite on indexer refresh"; "`docker compose up` serves everything on one port"
- compare_agents: include per-component winner ids (differentiator from FEATURES research)
- marketplace_stats: totals (agents, scored/NR split), grade distribution, category counts, median price, data_as_of — all derivable via SQL
- The demo (Phase 5) will screen-record this leaderboard + a live Claude MCP call — visual quality matters for judging

</specifics>

<deferred>
## Deferred Ideas

- x402 payment gating — Phase 4 (design composition so ASGI middleware wraps cleanly; FREE set will be /healthz, /, /badge/*, MCP initialize/tools/list)
- README/deploy docs — Phase 5 (OPS-02)
- Scraper — Phase 5

</deferred>

---

*Phase: 03-mcp-server-leaderboard*
*Context gathered: 2026-07-11 via PRD Express Path*
