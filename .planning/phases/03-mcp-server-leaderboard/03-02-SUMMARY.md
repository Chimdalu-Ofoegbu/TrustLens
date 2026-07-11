---
phase: 03-mcp-server-leaderboard
plan: 02
subsystem: api
tags: [fastmcp, mcp, sqlite, typeddict, pytest, structured-output]

# Dependency graph
requires:
  - phase: 01-foundation-data-indexer
    provides: agents table, indexer.parse.name_key (NFKC-casefold), indexer.category.CATEGORIES, indexer.refresh seeding
  - phase: 02-scoring-engine
    provides: scores table (score/grade/confidence/components + envelope columns), scoring.DISCLAIMER, SCORE_VERSION 1.0.0
provides:
  - FastMCP("TrustLens") instance with exactly 4 tools (score_agent, compare_agents, category_leaderboard, marketplace_stats), TypedDict-derived outputSchemas
  - server/db.py read-only access layer: connect_ro (mode=ro URI), lookup ladder (id -> name -> name_key, lowest-id collision resolution), slice/stats/envelope queries
  - ToolError-only error channel with deterministic neutral JSON (not_found/invalid_argument/unavailable/internal)
  - tests/conftest.py session fixture seeding data/trustlens.db from the committed census when absent
affects: [03-03 (pyproject packages + refresh wiring), 03-04 (mounts this mcp instance in FastAPI), 04-payments (x402 wraps these tools), 05-hardening]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ToolError-only error channel: every failure is raise _err(payload) with compact sorted deterministic JSON; plain exceptions never reach clients"
    - "Connection-per-call read-only sqlite via Path.as_uri() + ?mode=ro (space-safe)"
    - "TypedDict return annotations drive FastMCP outputSchema derivation + server-side validation; one _card builder keeps all required keys present"
    - "asyncio.run() wrappers for in-memory Client tests inside sync pytest (no async plugin)"

key-files:
  created:
    - server/__init__.py
    - server/db.py
    - server/tools.py
    - tests/conftest.py
    - tests/test_server_tools.py
  modified: []

key-decisions:
  - "Explicit try/except guard in each tool body (plan-sanctioned option) instead of a decorator — keeps FastMCP schema derivation on pristine annotated functions"
  - "Error payload builder helpers (_not_found_payload/_unavailable_payload/_internal_payload) so every failure path routes through _err and stays deterministic"
  - "Envelope test deletes TRUSTLENS_BASE_URL before asserting the default methodology_url so a user env var cannot flip the golden"

patterns-established:
  - "MCP tool shape: validate args -> connect_ro in try/finally -> stored-value envelope -> TypedDict-conforming dict"
  - "Collision disclosure: lowest id wins, ambiguous_matches (NotRequired) lists all {agent_id, name} matches when 2+ collide"

requirements-completed: [MCPS-01, MCPS-02]

# Metrics
duration: 12min
completed: 2026-07-11
---

# Phase 3 Plan 02: MCP Core — Read-Only DB Layer + Exactly 4 Tools Summary

**FastMCP("TrustLens") serving exactly 4 TypedDict-schema tools over a read-only sqlite layer with a deterministic id/name/NFKC-name_key lookup ladder, stored-value envelopes, and a ToolError-only error channel — pinned by 16 tests against the real 272-agent DB**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-11T11:23:50Z
- **Completed:** 2026-07-11T11:35:23Z
- **Tasks:** 3
- **Files modified:** 5 created

## Accomplishments

- `mcp.list_tools()` reports exactly 4 tools (MCPS-01), each with a non-empty derived outputSchema; FastMCP's server-side output validation passes for scored, NR, and collision cards (single `_card` builder)
- Lookup ladder resolves `"3345"` (id), `"这个能吃吗？"` (exact name), and `"这个能吃吗?"` (NFKC name_key) to the same 94/A/high card; both real collisions resolve to the lowest id (4353, 2662) with all matches disclosed in `ambiguous_matches`
- Every response carries `generated_at`/`data_as_of` = `2026-07-10T00:00:00Z`, `score_version` = `1.0.0`, `methodology_url`, and the scoring DISCLAIMER verbatim — all SERVED from the scores table, never recomputed, never wall clock (MCPS-02)
- Error hygiene proven through the in-memory Client: not_found/invalid_argument are deterministic neutral JSON with no Traceback/module/sqlite3 text; injection probes leave the agents table intact (272); ids capped 2–10, limit capped 1–50
- Full suite green: 216 passed (200 existing + 16 new), scoring coverage gate at 100% (>= 90%)

## Task Commits

Each task was committed atomically:

1. **Task 1: server/db.py — read-only access layer with the lookup ladder** - `b7c2eaa` (feat)
2. **Task 2: server/tools.py — FastMCP instance + exactly 4 tools with TypedDict structured output** - `889a3bd` (feat)
3. **Task 3: tests — conftest DB seed + tool suite (goldens, errors, injection, determinism)** - `c95c1f6` (test)

## Files Created/Modified

- `server/__init__.py` - Package docstring (MCP server + FastAPI host app, read-only)
- `server/db.py` - connect_ro (mode=ro URI), lookup_agent ladder, closest_candidates (LIKE-escaped), category_slice/category_total, stats aggregates, envelope_values — all parameterized, never writes
- `server/tools.py` - FastMCP("TrustLens"), 4 TypedDicts (ScoreCard/CompareResult/CategoryLeaderboard/MarketplaceStats), envelope helpers, `_card` builder, the 4 `@mcp.tool` functions with explicit ToolError guards
- `tests/conftest.py` - Session-scoped `real_db` fixture seeding data/trustlens.db from the committed census when absent
- `tests/test_server_tools.py` - 16 tests: tool count/schemas, goldens, ladder, envelope, determinism, collisions, NR validity via Client, error-leak checks, injection, caps, compare winners, leaderboard shape, stats goldens, strict input validation, banned-vocab scan, env-driven methodology_url

## Decisions Made

- Explicit try/except guard per tool body rather than a shared decorator (both plan-sanctioned): zero risk of wrapper interference with FastMCP's annotation-based schema derivation on Python 3.14
- Error payloads built by small helper functions and always raised as `raise _err(...)` — 12 raise sites all route through the single deterministic JSON serializer
- `test_envelope_on_all_four_tools` deletes `TRUSTLENS_BASE_URL` (raising=False) so the default-URL golden is robust to ambient environment

## Deviations from Plan

None - plan executed exactly as written.

## Authentication Gates

None encountered.

## Issues Encountered

None.

## Known Stubs

None — no placeholder values, empty-data wirings, or TODO markers in any created file.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The `mcp` instance in `server/tools.py` is ready for plan 03-04 to mount via `mcp.http_app(path="/", json_response=True)` inside the FastAPI factory
- Plan 03-03 (wave 1 sibling) extends pyproject packages and wires `web.build` into refresh; imports currently work via `python -m pytest` CWD semantics as planned
- Read-only layer and envelope queries are the substrate for `/healthz` (03-04) and the x402 gating (Phase 4) — no payment surface touched here

## Self-Check: PASSED

- All 5 created files verified on disk (`[ -f ]`)
- All 3 task commits found in git log (b7c2eaa, 889a3bd, c95c1f6)
- Plan verification re-run: subset 16 passed (--no-cov); full suite 216 passed, coverage gate 100%; `len(mcp.list_tools())` prints 4
- min_lines gates: server/tools.py 350 (>= 200), server/db.py 177 (>= 60)

---
*Phase: 03-mcp-server-leaderboard*
*Completed: 2026-07-11*
