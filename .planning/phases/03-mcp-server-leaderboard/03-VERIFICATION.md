---
phase: 03-mcp-server-leaderboard
verified: 2026-07-11T12:55:04Z
status: human_needed
score: 25/26 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Docker container smoke test (OPS-01 runtime): start Docker Desktop and wait for 'Engine running', then in trustlens/ run `docker compose up --build`; `curl http://localhost:8000/healthz` expecting \"status\":\"ok\" with \"agents\":272; browse http://localhost:8000/ (272-row leaderboard); `npx --yes @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/list` (4 tools); `docker compose down`"
    expected: "Leaderboard (/), MCP endpoint (/mcp), and /healthz all served from the single published port 8000; container self-seeds db + page via indexer.refresh on first start"
    why_human: "Docker Desktop engine will not start on this machine (verified again during this verification: `docker info` fails with 'open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified'). The 03-05 plan's locked 2-attempt stop rule was exhausted; engine startup is a user-environment action. All static evidence verified: compose config parses, Dockerfile/compose/.dockerignore are research-verbatim, every COPY path exists, and the exact entrypoint command sequence was proven locally against a live server."
---

# Phase 3: MCP Server & Leaderboard Verification Report

**Phase Goal:** Anyone can call all 4 trust tools over MCP and browse the ranked leaderboard — free and ungated — from a single dockerized port
**Verified:** 2026-07-11T12:55:04Z
**Status:** human_needed (single outstanding item: Docker container smoke test)
**Re-verification:** No — initial verification

All evidence below was produced by running commands against the actual codebase during this verification (full pytest suite, direct tool calls, in-process TestClient e2e with timed calls, refresh CLI reruns into temp dirs, and a live uvicorn + MCP Inspector CLI session on port 8123, killed afterward). SUMMARY claims were treated as hypotheses, not evidence.

## Goal Achievement

### ROADMAP Success Criteria

| # | Success Criterion | Status | Evidence |
|---|-------------------|--------|----------|
| 1 | Inspector lists exactly 4 tools and calls each; every response deterministic JSON with `generated_at` + `methodology_url` | ✓ VERIFIED | **Independently re-run live** (not just the 03-05 recorded proofs): `npx --yes @modelcontextprotocol/inspector --cli http://127.0.0.1:8123/mcp --method tools/list` → exactly category_leaderboard, compare_agents, marketplace_stats, score_agent, all with outputSchema; all four tools called via Inspector (5 invocations incl. quoted `'agent_id_or_name="3345"'` and CJK) — all parsed-stdout asserts passed. Envelope verified on all 4 tools: generated_at/data_as_of = 2026-07-10T00:00:00Z (stored values), methodology_url ends /#methodology, score_version 1.0.0, disclaimer verbatim. Repeat calls byte-identical JSON |
| 2 | `score_agent("这个能吃吗？")` and `score_agent("3345")` <500ms warm | ✓ VERIFIED | Timed through the full in-process HTTP stack (middleware + mount + session manager) after one warm-up: CJK 51.6ms, id 45.6ms — ~10x margin. `test_score_agent_under_500ms` inspected (really times both args, asserts <0.5s) and passes |
| 3 | Page at `/` ranks all agents with TrustScore + grade badges, sortable + category filter, <2s, methodology section + badge snippet, regenerates from SQLite on refresh | ✓ VERIFIED | GET / served 272 `<tr id="agent-` rows; `python -m indexer.refresh --db … --web-out …` exit 0 twice → sha256-identical 175,113-byte page (≤300KB budget → <2s trivial; zero external requests confirmed); `id="methodology"` + "About the methodology" + `id="badge"` + HTML/MD snippet blocks + "Copy badge snippet" present; sort/filter DOM hooks (data-k/data-v/select#cat/aria-sort) present and inline JS passes `node --check` with zero `$` |
| 4 | `docker compose up` serves leaderboard, MCP endpoint, /healthz on one port | ? HUMAN NEEDED | Runtime honestly DEFERRED in 03-05 per the locked 2-attempt stop rule — **deferral corroborated**: `docker info` still fails with the identical npipe error recorded in the SUMMARY. Static evidence all verified: `docker compose config` exit 0; one port only (8000:8000); Dockerfile/compose/.dockerignore match research verbatim; every COPY path exists; entrypoint command sequence proven locally (refresh seeds both artifacts offline; uvicorn serves /, /healthz, /badge/*, /mcp). See human verification item |

### Observable Truths (merged plan must_haves, deduplicated)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `mcp.list_tools()` reports exactly 4 tools, each with derived outputSchema (03-02) | ✓ VERIFIED | Direct run: 4 names sorted match, all output_schema non-empty; `grep -c '@mcp.tool' server/tools.py` = 4 |
| 2 | score_agent resolves '3345' (id), '这个能吃吗？' (exact name), '这个能吃吗?' (NFKC name_key) to same agent, 94/A (03-02) | ✓ VERIFIED | All three lookups returned agent_id 3345, score 94, grade A, confidence high, category Lifestyle & Health |
| 3 | Every tool response carries stored-value envelope, never wall clock (03-02) | ✓ VERIFIED | All 4 tools: generated_at = data_as_of = 2026-07-10T00:00:00Z (the seed timestamp — proof values are served from scores table, not computed) |
| 4 | Unknown agent raises ToolError with deterministic neutral JSON (03-02) | ✓ VERIFIED | `score_agent("no-such-agent-xyz")` raised ToolError; payload parsed as `{"error":"not_found","query":…}`; no Traceback/sqlite3 text |
| 5 | NR agents return full valid card: score null, grade NR, confidence low (03-02) | ✓ VERIFIED | Agent 1888 (first NR by id): score None, grade NR, confidence low, components + marketplace keys present |
| 6 | name_key collisions resolve to lowest id with ambiguous_matches disclosure (03-02) | ✓ VERIFIED | "人生说明书 · life book" → 4353 with ambiguous_matches {4353, 4517} |
| 7 | build() writes ONE self-contained HTML: 272 agents ranked desc, NR after scored, ties by id (03-01) | ✓ VERIFIED | Temp build: 272 rows; rank-sequence test (1..121 then 151 em-dashes) in passing suite; no `<link>`/`<script src>`/`@import`/`url(http`/fonts.googleapis |
| 8 | Page contains id="methodology" ("About the methodology") and id="badge" with embed snippet (03-01) | ✓ VERIFIED | Both anchors + snippet-html/snippet-md ids + instruction line confirmed in generated bytes |
| 9 | Hostile names/taglines render escaped, never live markup (03-01) | ✓ VERIFIED | XSS fixture test inspected (lines 186–213: `<script>alert` absent, `&lt;script&gt;alert` present, `"onmouseover` neutralized) and passes |
| 10 | badge_svg() UI-SPEC-conformant for A/B/C/D/F, NR, unknown (03-01) | ✓ VERIFIED | 13 badge contract tests pass; live route returned `viewBox="0 0 110 20"` + "A 94"; unknown id → neutral "N/A" |
| 11 | Building twice from same DB → byte-identical HTML (03-01) | ✓ VERIFIED | sha256 identical across two full CLI reruns |
| 12 | CLI refresh regenerates web/dist/index.html in the same run that indexes and scores (03-03) | ✓ VERIFIED | `main(['--db',…,'--web-out',…])` rc=0, "leaderboard built:" INFO line, 175,113 bytes |
| 13 | Rerunning CLI produces byte-identical HTML end-to-end (03-03) | ✓ VERIFIED | Same run as #11 (full pipeline rerun, not just build) |
| 14 | Exit-code taxonomy unchanged: 0/1/2; failed page build exits 2 (03-03) | ✓ VERIFIED | `test_page_build_failure_exits_2` body inspected (asserts rc 2 AND db still committed with 272 agents) and passes |
| 15 | Library refresh without web_out writes NO page; tests never write into repo (03-03) | ✓ VERIFIED | Library call into temp dir produced zero .html files; `git status --porcelain` empty after full suite |
| 16 | RefreshSummary frozen contract (03-03) | ✓ VERIFIED | "refresh complete: 272 agents, 272 snapshots appended, 1 field warning(s), source=census" log unchanged; test_refresh_scores suite green |
| 17 | POST to BOTH /mcp and /mcp/ reaches the MCP app — 400 JSON-RPC bare, never 405/307/HTML (03-04) | ✓ VERIFIED | Both paths returned 400 JSON-RPC with static mounted (McpPathRewrite works) |
| 18 | /healthz 200 JSON {status, agents, scores, score_version, data_as_of} seeded; 503 when DB missing (03-04) | ✓ VERIFIED | 200 `{"status":"ok","agents":272,"scores":272,"score_version":"1.0.0","data_as_of":"2026-07-10T00:00:00Z"}`; missing DB → 503 `{"status":"unavailable"}` with no exception text in body |
| 19 | GET / serves generated leaderboard (static mounted LAST) (03-04) | ✓ VERIFIED | 200 text/html, 272 rows; `grep -n 'app.mount'` shows /mcp (line 153) before / (line 154) |
| 20 | /badge/{id}.svg image/svg+xml + Cache-Control known; neutral 200 for unknown (03-04) | ✓ VERIFIED | 3345 → "A 94", Cache-Control: max-age=3600; 999999999 → 200 "N/A" |
| 21 | Full e2e JSON-RPC handshake: initialize → session → initialized 202 → tools/list (4 w/ outputSchema) → tools/call CJK (03-04) | ✓ VERIFIED | Executed live in-process: protocolVersion 2025-06-18, serverInfo.name TrustLens, all 4 tools on the wire, CJK call returned 3345/94/A structuredContent |
| 22 | Inspector CLI lists 4 tools and calls ALL FOUR against live server — parsed stdout (03-05) | ✓ VERIFIED | Re-run independently this verification (see SC1) |
| 23 | score_agent via Inspector with quoted '3345' and CJK name (03-05) | ✓ VERIFIED | Both quirk paths exercised; both resolve to 3345 A 94 |
| 24 | Container self-seeds: entrypoint runs indexer.refresh when db or page missing (03-05) | ✓ VERIFIED (static) | Dual `[ -f … ]` guard CMD verbatim in Dockerfile; census CSV copied into image; data/*.db + web/dist dockerignored (never bakes stale state); the exact command sequence proven locally. In-container execution is part of the human smoke test |
| 25 | docker compose up serves /, /healthz, /mcp on ONE port — or honest documented deferral (03-05) | ? HUMAN NEEDED | The truth's deferral branch is satisfied (verbatim engine error + 6 manual steps in 03-05-SUMMARY); the runtime branch needs the human smoke test. Never faked — engine-down state independently re-confirmed |
| 26 | FULL pytest suite passes with scoring coverage gate active (03-05, phase exit gate) | ✓ VERIFIED | Re-run this verification: **229 passed, 0 failed in 26.48s; scoring coverage 100.00% (gate ≥90%)** |

**Score:** 25/26 truths verified (1 pending the single human Docker smoke test)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `web/build.py` | build(db_path, out_path, base_url) → int; ≥300 lines | ✓ VERIFIED | 617 lines; mode=ro URI, `from scoring import`, badge_svg inlined, data-v attrs, zero localeCompare |
| `web/badge.py` | badge_svg + GRADE_BADGE_COLORS; ≥30 lines | ✓ VERIFIED | 58 lines; pure stdlib; served live by badge route |
| `server/db.py` | connect_ro, lookup ladder, queries; ≥60 lines | ✓ VERIFIED | 177 lines; mode=ro ×2, name_key import, zero f-string SQL, ESCAPE clause |
| `server/tools.py` | FastMCP + exactly 4 tools, TypedDict returns; ≥200 lines | ✓ VERIFIED | 350 lines; 4 @mcp.tool, 13 ToolError raise sites, banned vocab 0 |
| `server/app.py` | create_app factory, McpPathRewrite, route order; ≥100 lines | ✓ VERIFIED | 161 lines; json_response=True, combine_lifespans, raw_path rewrite, mounts ordered |
| `server/main.py` | module-level app for uvicorn | ✓ VERIFIED | 4 lines; served the live Inspector session |
| `indexer/refresh.py` | web_out threading + --web-out; contains DEFAULT_WEB_OUT | ✓ VERIFIED | DEFAULT_WEB_OUT ×4, web.build import ×1, default web/dist/index.html |
| `pyproject.toml` | packages incl. "server", "web" | ✓ VERIFIED | `packages = ["indexer", "scoring", "server", "web"]` (line 25) |
| `.gitignore` | web/dist/ | ✓ VERIFIED | Line 22 |
| `Dockerfile` | python:3.13-slim, self-seed CMD, HEALTHCHECK | ✓ VERIFIED | Research-verbatim (15 lines, read in full) |
| `docker-compose.yml` | one service, 8000:8000, required: false | ✓ VERIFIED | Research-verbatim |
| `.dockerignore` | data/*.db, .env excluded | ✓ VERIFIED | Research-verbatim (17 lines) |
| Test files (5) | test_web_badge/build, test_server_tools/app, test_refresh_web, conftest | ✓ VERIFIED | 92/231/260/279/89/19 lines; all named tests from plans exist and run in the 229-green suite |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| web/build.py | data/trustlens.db | read-only mode=ro URI | ✓ WIRED | Pattern present; real 272-row page built from it live |
| web/build.py | scoring constants | `from scoring import` | ✓ WIRED | DISCLAIMER ×2, weights, bands, descriptions all render in page |
| web/build.py | web/badge.py | inline rank-1 badge | ✓ WIRED | badge_svg ×3; viewBox in page |
| indexer/refresh.py | web/build.py | import, called after commit/close | ✓ WIRED | Executed: "leaderboard built:" after "scores computed:" in the same CLI run |
| server/tools.py | data/trustlens.db | server.db.connect_ro | ✓ WIRED | Live cards from real DB (Level 4 data-flow: real stored scores, not static returns) |
| server/tools.py | fastmcp ToolError | error channel | ✓ WIRED | ToolError raised and observed; neutral JSON on the wire |
| server/db.py | indexer.parse.name_key | NFKC normalization | ✓ WIRED | Import at line 18; NFKC lookup resolved live |
| server/app.py | server/tools.py mcp | http_app(json_response=True) + combine_lifespans mounted at /mcp | ✓ WIRED | Handshake + tools/call succeeded through the mount |
| server/app.py | web/dist/index.html | StaticFiles at / LAST | ✓ WIRED | GET / served 272 rows; mount order confirmed |
| server/app.py badge route | web/badge.py | badge_svg from DB grade/score | ✓ WIRED | Live "A 94" SVG for 3345 |
| McpPathRewrite | bare /mcp | ASGI scope + raw_path rewrite | ✓ WIRED | Bare POST /mcp → 400 JSON-RPC (not 405/307) |
| Dockerfile CMD | indexer.refresh + uvicorn | sh dual-guard | ✓ WIRED (static) | Verbatim CMD; sequence proven locally; container run = human item |
| docker-compose.yml | Dockerfile | build: . | ✓ WIRED (static) | `docker compose config` exit 0 |
| Inspector CLI | live /mcp | npx --cli | ✓ WIRED | Re-run live this verification |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| Leaderboard page rows | 272 `<tr>` rows | agents JOIN scores (SQLite) | Yes — real census-derived scores (94/A for 3345; 0.000015 price edge; 1,550 sold edge in page) | ✓ FLOWING |
| MCP tool responses | structuredContent | scores table via connect_ro | Yes — stored envelope timestamps (not wall clock), real grade distribution {A:12,B:9,C:19,D:54,F:27,NR:151} | ✓ FLOWING |
| /healthz body | agents/scores counts | live COUNT queries | Yes — 272/272 from seeded DB, 503 when missing | ✓ FLOWING |
| /badge/{id}.svg | grade/score | scores SELECT | Yes — "A 94" from DB; N/A only for unknown ids | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full suite + coverage gate | `python -m pytest` | 229 passed, coverage 100.00% | ✓ PASS |
| MCP goldens direct | verify_mcp_core.py (8 asserts groups) | ALL MCP CORE TRUTHS VERIFIED | ✓ PASS |
| Refresh CLI + HTTP stack | verify_http_stack.py (W1-W2, H1-H7) | ALL HTTP-STACK TRUTHS VERIFIED | ✓ PASS |
| MCPS-04 timing (warm) | timed tools/call ×2 | 51.6ms / 45.6ms < 500ms | ✓ PASS |
| Inspector tools/list live | npx …inspector --cli …tools/list | 4 tools, all outputSchema | ✓ PASS |
| Inspector tools/call ×5 live | all four tools incl. CJK + quoted-numeric | all parsed-stdout asserts pass | ✓ PASS |
| Inline JS parses | node --check on extracted `<script>` | exit 0, zero `$` | ✓ PASS |
| Compose parses | `docker compose config` | exit 0 | ✓ PASS |
| Container run | `docker compose up --build` | engine down (npipe error re-confirmed) | ? SKIP → human |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| MCPS-01 | 03-02 | Exactly 4 tools | ✓ SATISFIED | 4 decorators, list_tools = 4, on the wire = 4, Inspector = 4 |
| MCPS-02 | 03-02 | Deterministic JSON w/ generated_at + methodology_url | ✓ SATISFIED | Envelope on all 4; repeat-call byte identity |
| MCPS-03 | 03-04 | /healthz service health | ✓ SATISFIED | 200/503 contract executed live |
| MCPS-04 | 03-04 | Both lookups <500ms warm | ✓ SATISFIED | 51.6/45.6ms measured; pinned by test |
| MCPS-05 | 03-05 | Inspector lists and calls all 4 tools | ✓ SATISFIED | Independently re-proven live this verification |
| WEB-01 | 03-01 | Ranked sortable filtered page at /, <2s | ✓ SATISFIED | 272 rows served; hooks + parsing JS; 175KB static self-contained |
| WEB-02 | 03-01, 03-04 | Methodology section + badge embed snippet | ✓ SATISFIED | Anchors, snippets, live /badge/{id}.svg endpoint |
| WEB-03 | 03-03 | Page auto-regenerates on refresh | ✓ SATISFIED | CLI rerun byte-identical, temp-dir proof |
| OPS-01 | 03-05 | docker compose up serves everything on one port | ? NEEDS HUMAN | Static evidence complete + honest deferral; container run pending (REQUIREMENTS.md correctly still shows OPS-01 Pending) |

No orphaned requirements: REQUIREMENTS.md maps exactly MCPS-01..05, WEB-01..03, OPS-01 to Phase 3, and every ID is claimed by a plan.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No TODO/FIXME/stub/empty-return/print-handler patterns in any phase file | — | The only "placeholder" grep hits are documentation of string.Template placeholders and the em-dash missing-value glyph — not stubs |

Also audited (project rules): banned vocabulary (fraud/scam/fake/manipulat) = 0 matches across server/ and web/ source; git log has zero AI-attribution trailers, single author identity; working tree clean after the full suite (no repo pollution from tests).

### Human Verification Required

#### 1. Docker container smoke test (OPS-01 runtime — the only outstanding item)

**Test:** Start Docker Desktop and wait for "Engine running", then in `trustlens/`:
1. `docker compose up --build` (first build takes minutes)
2. `curl http://localhost:8000/healthz` → expect `"status":"ok"` with `"agents":272`
3. Browse `http://localhost:8000/` → 272-row leaderboard renders
4. `npx --yes @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/list` → 4 tools
5. `docker compose down`

**Expected:** Leaderboard, MCP endpoint, and /healthz all on the single published port 8000; container self-seeds db + page on first start.

**Why human:** Docker Desktop's engine will not start on this machine (re-confirmed during verification: `docker info` → "open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified"). The 03-05 locked 2-attempt stop rule was already exhausted; engine startup is a user-environment action. Everything the container executes (`python -m indexer.refresh`; `uvicorn server.main:app --host 0.0.0.0 --port 8000`) was proven working locally, and all three Docker files parse and match the PoC-verified research verbatim — so residual risk is confined to the Docker environment itself, not the code. Note: Phase 5's submission gate (demo executed against a clean-clone `docker compose up`) will also force this check if not done earlier.

### Gaps Summary

No code gaps. All 5 plans' must_haves are present, substantive, wired, and carrying real data; all 26 merged truths verified except the single container-runtime confirmation, which is environment-blocked, honestly documented in 03-05-SUMMARY with the verbatim engine error and exact manual steps, and independently corroborated during this verification. The phase goal — 4 MCP tools + leaderboard + /healthz free from one port — is demonstrably achieved on the local one-port server; the dockerized delivery of that same composition awaits the 5-step human smoke test above.

---

_Verified: 2026-07-11T12:55:04Z_
_Verifier: Claude (gsd-verifier)_
