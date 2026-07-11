---
phase: 03-mcp-server-leaderboard
plan: 04
subsystem: api
tags: [fastapi, fastmcp, starlette, asgi, streamable-http, json-rpc, sqlite, svg, testclient]

# Dependency graph
requires:
  - phase: 03-01
    provides: "web/badge.py badge_svg(grade, score) neutral-N/A generator + web/build.py build() for the test fixture"
  - phase: 03-02
    provides: "server/tools.py mcp (FastMCP TrustLens, 4 tools) + server/db.py connect_ro/DEFAULT_DB + tests/conftest.py real_db"
  - phase: 03-03
    provides: "packages installed editable incl. server/web; data/trustlens.db + web/dist/index.html staged at repo defaults"
provides:
  - "server/app.py create_app(db_path, static_dir) — PoC-verified V3 composition: McpPathRewrite + http_app(path='/', json_response=True) mounted at /mcp with combine_lifespans, /healthz and /badge/{id}.svg registered first, StaticFiles at / LAST"
  - "server/main.py module-level app — uvicorn server.main:app --host 0.0.0.0 --port 8000"
  - "Bare /mcp AND /mcp/ both answer JSON-RPC (no 405/307) with static mounted — proven in-process"
  - "MCPS-03 healthz 200/503 contract, MCPS-04 <500ms timed proof, WEB-02 badge endpoint with caching"
  - "tests/test_server_app.py — the e2e harness Phase 4 wraps with x402 (handshake, session headers, negative asserts)"
affects: [03-05, phase-04-payments, docker]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "McpPathRewrite pure-ASGI scope rewrite (/mcp -> /mcp/) added LAST so Phase-4 X402Middleware registered after it runs BEFORE it and matches scope['path'].startswith('/mcp')"
    - "combine_lifespans(app_lifespan, mcp_app.lifespan) — MCP session manager always initialized; app lifespan warns (never raises) on missing artifacts"
    - "Guarded connection-per-request routes: entire body in try/except (sqlite3.Error, OSError) returning fixed bodies — no exception text ever serialized"
    - "App-level tests: with TestClient(create_app(db_path=..., static_dir=...)) — parameterized paths keep the suite off the repo's real artifacts"

key-files:
  created:
    - server/app.py
    - server/main.py
    - tests/test_server_app.py
  modified: []

key-decisions:
  - "%2F traversal probe asserts the verified starlette 1.3.1 behavior (404 route-miss via StaticFiles guard, no secret/500) instead of the plan-expected 200 N/A; a %5C backslash variant reaches the route and exercises the T-03-13 allowlist -> 200 neutral badge"
  - "Badge DB lookup guarded like healthz (degrade to neutral badge on sqlite3.Error/OSError) — the embed contract is 'always renders', so a missing DB must not 500"

patterns-established:
  - "JSON-RPC over plain application/json (json_response=True): tests read r.json() directly — no SSE parsing anywhere"
  - "Handshake helper returns {**H, mcp-session-id, MCP-Protocol-Version} headers — the reusable session recipe for Phase-4 paid-call tests"

requirements-completed: [MCPS-03, MCPS-04, WEB-02]

# Metrics
duration: 12min
completed: 2026-07-11
---

# Phase 3 Plan 04: One-Port Composition Summary

**create_app() serves FastMCP at /mcp (bare and trailing-slash, via the verified McpPathRewrite), /healthz 200/503, cached badge SVGs, and the 272-agent static leaderboard on one port — proven in-process with a full JSON-RPC handshake and both MCPS-04 lookups timed under 500ms**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-11T11:56:51Z
- **Completed:** 2026-07-11T12:08:44Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- The starlette 1.3.1 mount defect is fixed in OUR app: bare `POST /mcp` returns 400 JSON-RPC "Missing session ID" (never 405 from StaticFiles, never 307) and `/mcp/` behaves identically — the single assert that proves the PoC correction holds with static mounted
- Full e2e over the in-process HTTP stack: initialize (protocolVersion 2025-06-18, serverInfo.name TrustLens) -> session id -> notifications/initialized 202 -> tools/list (exactly 4 tools, all with outputSchema) -> tools/call with the CJK arg returning the golden 3345/94/A card in structuredContent
- MCPS-04 pinned by `test_score_agent_under_500ms`: one warm-up, then `这个能吃吗？` and `3345` each timed <0.5s through middleware + mount + session manager (observed ~40ms locally)
- MCPS-03 healthz contract: 200 `{status, agents:272, scores:272, score_version:1.0.0, data_as_of}` on the seeded DB; fixed 503 `unavailable` body (exact locked field set, no exception text) when the DB is missing
- WEB-02 badge endpoint: `A 94` SVG with `Cache-Control: max-age=3600` for 3345, neutral `N/A` badge (200, never 404) for unknown ids, allowlist regex before any DB touch, `>NR<` badge for not-rated agents
- Full suite: 229 passed (221 + 8 new), scoring coverage gate at 100%

## Task Commits

Each task was committed atomically:

1. **Task 1: server/app.py + server/main.py — verified composition** - `c6b588c` (feat)
2. **Task 2: tests/test_server_app.py — route order, handshake, perf, healthz, badge** - `f12f61a` (test)

## Files Created/Modified

- `server/app.py` - create_app() factory: McpPathRewrite (research-verbatim), json_response=True http_app mounted at /mcp, combine_lifespans, guarded /healthz + /badge/{agent_id}.svg, StaticFiles at / registered LAST, Phase-4 LIFO middleware comment
- `server/main.py` - module-level `app = create_app()` for `uvicorn server.main:app`
- `tests/test_server_app.py` - 8 app-level tests: route order (the 3-assert rewrite proof), /mcp/ parity, full JSON-RPC handshake, MCPS-04 timing, not-found neutrality over HTTP, healthz 503 shape, badge matrix (known/unknown/%2F/%5C/NR), static integrity (272 rows + 404 pass-through)

## Decisions Made

- `%2F` traversal test asserts verified behavior (404, no secret, no 500) rather than the plan's assumed 200 — see deviations
- Badge route degrades to the neutral badge on DB errors instead of 500 — see deviations

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Planned %2F traversal assertion contradicted verified starlette 1.3.1 routing**
- **Found during:** Task 2 (badge route tests) — probed before writing the test
- **Issue:** Plan expected `GET /badge/..%2F..%2Fsecret.svg` -> 200 neutral N/A via the allowlist regex. Verified reality: the ASGI path is percent-decoded before routing, so `/badge/../../secret.svg` contains slashes, never matches `{agent_id}` ([^/]+), falls through to StaticFiles whose anti-traversal guard returns 404 JSON — the request never reaches the badge route at all
- **Fix:** Test asserts the verified secure outcome for %2F (404, body contains no "secret", no 500) AND adds a `..%5C..%5Csecret` backslash variant that DOES reach the route and is rejected by the allowlist regex before any DB touch (200 neutral N/A) — exercising STRIDE T-03-13's mitigation exactly as intended
- **Files modified:** tests/test_server_app.py
- **Verification:** Both probes pass; traversal is impossible via either encoding (no DB touch, no filesystem read, no error leak)
- **Committed in:** f12f61a (Task 2 commit)

**2. [Rule 2 - Missing critical] Badge DB lookup guarded against sqlite3.Error/OSError**
- **Found during:** Task 1 (badge route implementation)
- **Issue:** Plan mandated the try/except only for /healthz; an unguarded badge lookup would 500 on a missing/unreadable DB, violating the route's own "never 404 (or error) for embeds — always renders" contract
- **Fix:** Wrapped the lookup in try/except (sqlite3.Error, OSError) degrading to the neutral N/A badge with the exception logged server-side only
- **Files modified:** server/app.py
- **Verification:** Route always returns 200 image/svg+xml; healthz 503 test covers the missing-DB scenario end-to-end
- **Committed in:** c6b588c (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 bug in planned assertion, 1 missing error handling)
**Impact on plan:** Both preserve the plan's security intent (T-03-13/T-03-14) against verified framework behavior. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The exact composition Phase 4 wraps: X402Middleware registers AFTER `add_middleware(McpPathRewrite)` (LIFO — runs before the rewrite) and matches `scope["path"].startswith("/mcp")`; free routes /healthz, /, /badge/* untouched by the rewrite
- Plan 03-05 can run the live smoke immediately: `python -m uvicorn server.main:app --port 8000` serves healthz/leaderboard/badges/MCP from the staged repo-default artifacts
- Handshake/session helpers in tests/test_server_app.py are the reusable recipe for Inspector-fallback and Phase-4 402 tests

## Self-Check: PASSED

All created files exist on disk; task commits c6b588c and f12f61a present in git log.

---
*Phase: 03-mcp-server-leaderboard*
*Completed: 2026-07-11*
