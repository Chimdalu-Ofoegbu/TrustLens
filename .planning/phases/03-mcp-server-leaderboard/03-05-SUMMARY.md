---
phase: 03-mcp-server-leaderboard
plan: 05
subsystem: infra
tags: [docker, docker-compose, dockerignore, mcp-inspector, npx, uvicorn, pytest]

# Dependency graph
requires:
  - phase: 03-mcp-server-leaderboard (plans 03-03, 03-04)
    provides: "python -m indexer.refresh seeds db + web/dist/index.html offline; uvicorn server.main:app serves /, /healthz, /badge/*.svg, /mcp on one port; pyproject packages include server + web"
provides:
  - "Dockerfile (python:3.13-slim, pip install ., HEALTHCHECK, self-seeding CMD via indexer.refresh)"
  - "docker-compose.yml (one service, one port 8000:8000, env_file tolerant of absence)"
  - ".dockerignore (excludes .env, data/*.db(+wal/shm), web/dist, tests, .planning, .git)"
  - "MCPS-05 runtime proof: Inspector CLI tools/list (4 tools) + tools/call for all 4 tools against live server, asserted on parsed stdout"
  - "Phase exit gate: full suite 229 passed, scoring coverage 100% (gate >= 90%)"
affects: [04-x402-payment-layer, 05-scraper-hardening-submission, deploy, README]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Container self-seeding: dual [ -f ... ] guard in CMD runs python -m indexer.refresh when db or page missing — images never bake a stale local DB"
    - "Inspector CLI scripting on Windows: assert on parsed stdout JSON prefix (raw_decode), never on npx exit codes; always --cli; numeric-looking string args need embedded JSON quotes"

key-files:
  created:
    - Dockerfile
    - docker-compose.yml
    - .dockerignore
  modified: []

key-decisions:
  - "OPS-01 container run DEFERRED honestly after 2 failed Docker Desktop engine-start attempts (locked stop rule); files verified statically + entrypoint command proven locally"
  - "Docker files transcribed verbatim from PoC-verified research primitives — no volumes, no extra services, one port"

patterns-established:
  - "Engine-start stop rule: 2 attempts (Start-Process exe + docker desktop start, 120s poll each), then honest DEFERRED with verbatim error and manual steps"

requirements-completed: [MCPS-05]

# Metrics
duration: 26min
completed: 2026-07-11
---

# Phase 3 Plan 05: Docker Packaging + MCP Inspector Proof + Phase Gate Summary

**MCPS-05 proven live — Inspector CLI lists 4 tools and calls all four against the running server (stdout-parsed, CJK + quoted-numeric quirks exercised); Docker files land research-verbatim with OPS-01 container run honestly DEFERRED after the engine refused to start twice; full suite 229 passed with scoring coverage at 100%.**

## Performance

- **Duration:** ~26 min
- **Started:** 2026-07-11T12:16:12Z
- **Completed:** 2026-07-11T12:42:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Dockerfile, docker-compose.yml, .dockerignore created exactly per research §Docker: python:3.13-slim, `pip install .`, HEALTHCHECK on /healthz, self-seeding CMD, one published port 8000, `.env`/local DBs never baked into the image
- MCPS-05 runtime proof against live `uvicorn server.main:app --port 8000`: Inspector 0.22.0 CLI tools/list returned exactly the 4 tools (all with outputSchema) and all four tools/call invocations succeeded — assertions on parsed stdout only
- Phase exit gate green: `python -m pytest` -> 229 passed, 0 failed; scoring coverage 100.00% (gate >= 90% active)
- No repo pollution: `git status --porcelain` clean after all runtime work (scratch outputs kept in session scratchpad)

## Task Commits

Each task was committed atomically:

1. **Task 1: Dockerfile, docker-compose.yml, .dockerignore — research-verbatim** - `af15cbd` (feat)
2. **Task 2: Runtime proof — Inspector CLI, docker compose, full-suite gate** - no repo files (runtime verification; evidence below)

**Plan metadata:** this SUMMARY commit (docs)

## Files Created/Modified

- `Dockerfile` - python:3.13-slim image; COPY pyproject + indexer/scoring/server/web + census CSV; `pip install --no-cache-dir .`; HEALTHCHECK (30s interval, 15s start-period); CMD with dual `[ -f ... ]` guard self-seeding db + leaderboard via `python -m indexer.refresh`, then `exec uvicorn server.main:app --host 0.0.0.0 --port 8000`
- `docker-compose.yml` - single `trustlens` service, `build: .`, one port mapping `8000:8000`, `env_file` with `required: false` (tolerant of absent .env; compose >= 2.24)
- `.dockerignore` - excludes `.git`, `.planning`, `.claude`, `.venv`, caches, `tests`, `web/dist`, `data/*.db(+wal/shm)`, `data/cache`, `.env`

## MCPS-05 Runtime Verification Record (Part B — PASSED)

Server: `python -m indexer.refresh` (exit 0; 272 agents, leaderboard 175,113 bytes) then `python -m uvicorn server.main:app --port 8000`; `/healthz` -> 200 `{"status":"ok","agents":272,"scores":272,"score_version":"1.0.0","data_as_of":"2026-07-10T00:00:00Z"}`.

Inspector: `npx --yes @modelcontextprotocol/inspector --cli http://127.0.0.1:8000/mcp ...` — all assertions on parsed stdout JSON (exit codes unreliable on Windows; `--cli` always passed; numeric-looking string quoted as `'agent_id_or_name="3345"'`):

```
MCPS-05 tools/list OK                       (4 tools: category_leaderboard, compare_agents,
                                             marketplace_stats, score_agent — all with outputSchema)
MCPS-05 score_agent("3345") OK              - agent_id 3345, grade A, score 94
MCPS-05 score_agent(CJK name) OK            - 这个能吃吗？ resolves to agent_id 3345, grade A, score 94
MCPS-05 compare_agents OK                   - 2 cards, component_winners has 5 keys
MCPS-05 category_leaderboard OK             - category 'Trading & DeFi', 5 entries (<= 5)
MCPS-05 marketplace_stats OK                - agents_total 272
ALL FIVE INSPECTOR PROOFS PASSED
```

Server process terminated after the proofs; port 8000 released.

## OPS-01 Runtime Verification: DEFERRED (Part C — locked 2-attempt stop rule)

**OPS-01 runtime verification DEFERRED — files verified statically (`docker compose config` passes; every referenced path exists; entrypoint command proven locally in Part A).**

Engine-start attempts (both failed):

1. **Attempt 1:** `powershell -Command "Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'"`, then `docker info` polled every 10s for 120s — engine never came up.
2. **Attempt 2:** `docker desktop start` + repeat `Start-Process`, polled a further ~210s — the `docker desktop start` helper (docker-desktop.exe) remained blocked without effect and no Docker Desktop backend process ever persisted in the process list.

Verbatim `docker info` error (identical throughout):

```
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine; check if the path is correct and if the daemon is running: open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

Static verification evidence:
- `docker compose config` exits 0 (compose file parses without the engine)
- Every Dockerfile COPY path exists: `pyproject.toml`, `indexer/`, `scoring/`, `server/`, `web/`, `data/okx-marketplace-census-2026-07-10.csv`
- The container entrypoint command sequence was proven locally in Part A: `python -m indexer.refresh` exit 0 seeds both artifacts; `uvicorn server.main:app --port 8000` serves `/healthz` ok, `/`, and `/mcp` (Inspector proofs above)

**Manual verification steps (run once Docker Desktop is healthy):**

1. Start Docker Desktop; wait for the whale icon to report "Engine running"
2. `docker compose up --build` (first build takes minutes)
3. `curl http://localhost:8000/healthz` — expect `"status":"ok"` with `"agents":272`
4. Browse `http://localhost:8000/` — 272-row leaderboard renders
5. `npx --yes @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/list` — stdout lists 4 tools
6. `docker compose down`

## Phase Exit Gate (Part D — PASSED)

`python -m pytest` (full suite, coverage gate ACTIVE): **229 passed, 0 failed** in 28.92s. Scoring coverage **100.00%** (`Required test coverage of 90% reached.` — all of scoring/__init__, components, engine, persist, stats at 100%).

## Decisions Made

- OPS-01 container run deferred honestly per the orchestrator-locked 2-attempt stop rule; never faked. The requirement's checkbox stays open pending the 6-step manual run above.
- No extra retries, restart-service hacks, or WSL pokes beyond the locked procedure — engine startup is a user-environment action.

## Deviations from Plan

None - plan executed exactly as written (the OPS-01 deferral IS the plan's prescribed fallback path, not a deviation).

## Issues Encountered

- Docker Desktop engine would not start from the CLI (both `Start-Process` of the exe and `docker desktop start`); backend process exits immediately without error output. Handled via the plan's locked DEFERRED path — verbatim error and manual steps recorded above.
- Background `docker desktop start` helper process stayed blocked after the stop rule triggered; terminated explicitly (taskkill) so no orphan processes remain.

## User Setup Required

**OPS-01 manual container verification pending:** start Docker Desktop manually and run the 6 steps listed above. Everything else is fully verified.

## Next Phase Readiness

- Phase 3 exit gate green: all 5 plans complete, 229 tests passing, scoring gate intact
- Phase 4 (x402) wraps this working one-port service; the bare-path `/mcp` curl shape for the OKX pre-registration check is documented in this plan's Part C and already proven in-process by tests/test_server_app.py
- Docker files are ready for the Phase 4/5 deploy story; only the live container smoke-run remains (blocked on Docker Desktop engine health on this machine)

## Self-Check: PASSED

- FOUND: Dockerfile, docker-compose.yml, .dockerignore, 03-05-SUMMARY.md
- FOUND commit: af15cbd (Task 1)
- Working tree clean before SUMMARY (no scratch files, no *.db / web/dist entries)

---
*Phase: 03-mcp-server-leaderboard*
*Completed: 2026-07-11*
