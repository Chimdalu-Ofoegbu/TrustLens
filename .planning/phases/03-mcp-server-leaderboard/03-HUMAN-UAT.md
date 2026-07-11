---
status: partial
phase: 03-mcp-server-leaderboard
source: [03-VERIFICATION.md]
started: 2026-07-11T13:30:00Z
updated: 2026-07-11T13:30:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Docker container smoke test (OPS-01 runtime verification)

expected: Start Docker Desktop and wait for "Engine running". Then from the `trustlens/` repo root:
1. `docker compose up --build`
2. `curl http://localhost:8000/healthz` → 200 with `"agents": 272` (container self-seeds from the bundled census on first start)
3. Browse `http://localhost:8000/` → leaderboard renders 272 rows, sortable, category filter works
4. `npx --yes @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/list` → exactly 4 tools
5. `docker compose down`

All static evidence already verified (compose config parses; Dockerfile paths exist; entrypoint sequence proven locally; the same app stack passed the live Inspector proof on the host). This item exists solely because the Docker Desktop engine would not start on this machine during the build (npipe error recorded verbatim in 03-05-SUMMARY.md and re-confirmed during verification).

result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
