---
phase: 05-scraper-hardening-submission-kit
plan: 02
subsystem: infra
tags: [readme, docs, ops, x402, mcp, onchain-os, okx-asp]

# Dependency graph
requires:
  - phase: 03-mcp-server-leaderboard
    provides: verified MCP Inspector commands (tools/list, score_agent CJK call) + one-port app (/, /healthz, /mcp) + Docker self-seed CMD
  - phase: 04-x402-payment-layer
    provides: verified `curl -i -X POST` 402 pre-registration check + PAYMENT-REQUIRED header + make_verifier/PaymentVerifier/UnconfiguredVerifier seam + .env.example (5 vars)
  - phase: 05-scraper-hardening-submission-kit
    provides: the `--scrape` refresh path documented in the README's optional-enrichment section
provides:
  - "README.md (OPS-02): operator + OKX ASP registration guide with verified commands and both agent prompts quoted verbatim"
  - "Marked HUMAN-ONLY stop conditions (deploy, wallet login, registration/listing submission, real creds, Docker-engine start)"
  - "Neutral, banned-vocab-clean outward-facing operator doc ready for the Plan 03 language gate"
affects: [05-03-submission-kit, final-human-checklist, deploy, okx-asp-registration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Verified-commands-only doc policy: every command in the README is transcribed byte-for-byte from a command verified in an earlier phase or in 05-RESEARCH.md"
    - "HUMAN-ONLY inline marking convention for stop-condition steps"

key-files:
  created:
    - "README.md"
  modified:
    - ".planning/STATE.md"
    - ".planning/ROADMAP.md"
    - ".planning/REQUIREMENTS.md"

key-decisions:
  - "H1 intro block serves as locked section 1 (what-it-is + 4 tools); the remaining 10 required sections are ## headings in the locked CONTEXT order"
  - "Both ASP prompts placed each in their own fenced ```text block so the exact string is unambiguous (no smart-quote or trailing-punctuation drift)"
  - "Placeholder-only secrets throughout (0x0000...0000, <host>, https://rpc.xlayer.tech) — no real wallet/key/domain anywhere"

patterns-established:
  - "Verified-commands-only README: no command appears that has not been run/proven in an earlier phase or the phase research"
  - "Stop conditions surfaced twice: inline [HUMAN-ONLY] marks per step + a closing one-line HUMAN-ONLY summary"

requirements-completed: [OPS-02]

# Metrics
duration: 9min
completed: 2026-07-11
---

# Phase 5 Plan 02: README (OPS-02) Summary

**Repo-root README.md operator + OKX ASP registration guide — 11 locked sections, both OKX ASP agent prompts quoted verbatim, every command transcribed byte-for-byte from a prior-phase/research-verified source, all HUMAN-ONLY stop conditions marked, zero banned vocabulary.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-07-11T15:52:00Z
- **Completed:** 2026-07-11T16:01:00Z
- **Tasks:** 1
- **Files modified:** 4 (1 created, 3 state/roadmap/requirements)

## Accomplishments

- Wrote `README.md` (149 lines, ≥120 min) with all 11 locked sections in order: (1) what TrustLens is + the 4 tools; (2) Local run; (3) Tests & coverage gate; (4) Docker; (5) Optional `--scrape` refresh; (6) MCP Inspector; (7) x402 pre-registration check; (8) Configuration (env vars); (9) Mock → real payment SDK; (10) Deploy; (11) Register on OKX.AI (ASP).
- Quoted **both** OKX ASP agent prompts VERBATIM, each in its own fenced `text` block: "Help me register an A2MCP ASP on OKX.AI using Onchain OS" and "Help me list my ASP on OKX.AI using Onchain OS".
- Transcribed every verified command exactly: `pip install -e .[dev]`, `python -m indexer.refresh`, `uvicorn server.main:app --host 0.0.0.0 --port 8000`, `python -m pytest` (+ the `--no-cov` subset footgun), `docker compose up`, the four MCP Inspector `npx --yes @modelcontextprotocol/inspector` invocations (including the CJK `score_agent` call → 3345/A/94), the `curl -i -X POST https://<host>/mcp` 402 check, and `npx skills add okx/onchainos-skills --yes -g`.
- Documented the 5 env vars as a placeholder-only table pointing at `.env.example`, and named the `make_verifier` / `PaymentVerifier` seam (with `UnconfiguredVerifier` as the exact `okxweb3-app-x402` swap point) in `server/payments.py`.
- Marked every HUMAN-ONLY step: Docker-engine start, wallet login, ASP registration submission, ASP listing submission, real OKX creds, and remote deploy.

## Task Commits

Executed as a single doc task (README + plan metadata committed together per the sequential-executor SUMMARY→commit rule):

1. **Task 1: Write README.md with verified commands + verbatim ASP prompts + marked human steps** — committed with the plan metadata as `docs(05-02): ...`

**Plan metadata:** same commit (README.md + 05-02-SUMMARY.md + STATE.md + ROADMAP.md + REQUIREMENTS.md)

## Files Created/Modified

- `README.md` — the OPS-02 operator + OKX ASP registration guide (created).
- `.planning/STATE.md` — advanced position to 05-02 complete (2 of 3), decisions/session updated.
- `.planning/ROADMAP.md` — Phase 5 plan progress 2/3, 05-02 checkbox marked.
- `.planning/REQUIREMENTS.md` — OPS-02 marked complete.

## Decisions Made

- The `# TrustLens` H1 intro paragraph + "The 4 MCP tools" list is section 1 of the locked ordering (what-it-is + tools); the other 10 required sections are `##` headings, keeping the CONTEXT order exactly (Local run → … → Register on OKX.AI). Verified by section-order scan.
- Each ASP prompt is isolated in its own fenced `text` block rather than an inline code span, so the exact string can be copy-pasted with zero risk of smart-quote or trailing-punctuation drift.
- Kept the differentiation line (hiring-trust vs Factor/TO1/Internet Court) and the methodology link in the intro to satisfy the neutral-framing requirement without any accusatory vocabulary.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The plan's second verification helper (a Python one-liner printing section headings) crashed on the Windows cp1252 console when printing the `→` character — the exact Pitfall 5 (CJK/Unicode console crash) documented in 05-RESEARCH.md. Resolved by re-running with `sys.stdout.reconfigure(encoding="utf-8")`; the check then passed (all 11 sections in order, seam named, 5 env vars, human-only marks). This affected only the verification harness, not README.md content. The plan's own required assertion (`python -c "... print('README OPS-02 OK')"`) passed on the first run.

## User Setup Required

None - no external service configuration required. (All deploy/registration/wallet steps are HUMAN-ONLY stop conditions documented in the README for the final human checklist, not build-time setup.)

## Next Phase Readiness

- README.md is complete and banned-vocab-clean, ready for Plan 05-03's language gate (which re-scans README.md for `fraud|scam|fake|manipulat`) and the ≤80-char tagline check.
- Plan 05-03 (submission kit: demo-script, x-post, listing-copy) is the last plan in the phase and the milestone; it can proceed in Wave 2.
- No blockers. The carried Docker-engine-start and deploy/registration items remain HUMAN-ONLY and are now documented in the README for the final checklist.

## Self-Check: PASSED

- `README.md` — FOUND
- `.planning/phases/05-scraper-hardening-submission-kit/05-02-SUMMARY.md` — FOUND
- Commit `2aedbf3` — FOUND in git log
- Deletions in commit — none
- AI attribution scan — clean (no Co-Authored-By / Claude / Anthropic / "generated with")
- Plan verification assertion (`python -c "... print('README OPS-02 OK')"`) — PASSED
- README ≥120 lines (149), all 11 sections in locked order, both ASP prompts verbatim, 5 env vars, seam named, HUMAN-ONLY marks, no banned vocab — verified

---
*Phase: 05-scraper-hardening-submission-kit*
*Completed: 2026-07-11*
