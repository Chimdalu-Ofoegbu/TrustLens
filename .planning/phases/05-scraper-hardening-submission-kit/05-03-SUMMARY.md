---
phase: 05-scraper-hardening-submission-kit
plan: 03
subsystem: testing
tags: [submission-kit, documentation, pytest, language-gate, banned-vocab, okx-hackathon]

# Dependency graph
requires:
  - phase: 05-scraper-hardening-submission-kit (plan 02)
    provides: README.md (OPS-02) — the language gate also scans it
  - phase: 02-scoring-engine
    provides: the verbatim rating_credibility reason string surfaced in the demo anomaly beat
  - phase: 04-x402-payment-layer
    provides: the 402->paid 0.01 USDT/call flow the demo + listing describe
provides:
  - submission/demo-script.md — 90s storyboard (SUBM-01) with the verified GlassDesk 3465 flagged-not-accused anomaly beat
  - submission/x-post-draft.md — #OKXAI launch thread (SUBM-02), neutral/factual
  - submission/listing-copy.md — ASP listing fields (SUBM-03): 66-char primary tagline, Software Services, 0.01 USDT
  - tests/test_submission_language.py — banned-vocab gate over submission/*.md + README.md, plus <=80-char tagline assertion (OPS-03 hardening)
affects: [milestone-completion, human-submission-checklist, deploy]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Language gate mirrors test_scoring_golden's directory-scan: regex literal lives in tests/, outside the scanned tree, so it never trips on source keyword tables"
    - "Primary tagline is a machine-checkable contract: a single line of the exact form **Tagline:** <text>, asserted <=80 chars"

key-files:
  created:
    - submission/demo-script.md
    - submission/x-post-draft.md
    - submission/listing-copy.md
    - tests/test_submission_language.py
  modified: []

key-decisions:
  - "Primary tagline chosen: 'Deterministic trust scores for OKX.AI agents, in one paid MCP call' (66 chars); other four verified taglines listed as alternates"
  - "Neutral-language meta-commentary must not enumerate the banned tokens literally — the language gate scans the submission text including such lines, so the checklist references 'the banned accusatory vocabulary' instead of spelling it out"
  - "Language gate scans submission/*.md + README.md only (never source dirs) so it cannot trip on indexer/category.py's scam/rug keyword table"

patterns-established:
  - "Outward-text banned-vocab gate: sorted(SUBMISSION.glob('*.md')) + README.md, regex literal in the test file, asserts README is in scope"
  - "Tagline limit enforced via a required **Tagline:** single-line marker parsed and length-checked"

requirements-completed: [SUBM-01, SUBM-02, SUBM-03, OPS-03]

# Metrics
duration: 12min
completed: 2026-07-11
---

# Phase 5 Plan 03: Submission Kit + Language Gate Summary

**Three submission/*.md artifacts (90s demo storyboard, #OKXAI launch thread, ASP listing copy) built from verified real agent data, plus a pytest language gate that mechanically enforces neutral outward wording over submission/ + README.md and the <=80-char tagline limit.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-11T16:20:00Z
- **Completed:** 2026-07-11T16:32:00Z
- **Tasks:** 2
- **Files modified:** 4 (all created)

## Accomplishments

- **submission/demo-script.md (SUBM-01):** a five-beat 90-second storyboard — problem -> live `score_agent("这个能吃吗？")` (A/94/high, 5.0 on 539 sales) -> the money beat `score_agent("GlassDesk")` id 3465 (D/45/low, 5.0 on 1 sale) with the verbatim `rating_credibility.reason` string read aloud -> agent-calling-agent A2MCP flow -> leaderboard (272 agents) + 0.01 USDT/call on-chain settlement. Executable against a clean-clone `docker compose up`; the Docker-engine start is marked **HUMAN-ONLY**. Backup heroes (Token Radar 2991, Thumbnail Maker 4511) noted; Factor Credit Desk explicitly excluded as a subject.
- **submission/x-post-draft.md (SUBM-02):** a 6-tweet launch thread carrying `#OKXAI`, neutral and factual — one-call hiring-trust verdict, determinism (`score_version` + `data_as_of` + pure functions = same call, same bytes), on-chain pay-per-call (0.01 USDT on X Layer, zero gas), and the Factor/TO1/Internet Court differentiation one-liner.
- **submission/listing-copy.md (SUBM-03):** ASP listing fields — Name TrustLens, primary **Tagline** at 66 chars (+4 verified alternates, all <=80, char-counted), a neutral description baking in the four signals and the hiring-trust-vs-Factor/TO1/Internet-Court differentiation, Category "Software Services", Price 0.01 USDT, plus `https://<host>/mcp` endpoint and `<base>/#methodology` placeholders.
- **tests/test_submission_language.py (OPS-03 hardening):** 3 tests — the three kit files exist; the banned-vocab regex `(?i)(fraud|scam|fake|manipulat)` matches nowhere across `submission/*.md` + `README.md` (README proven in scope); and the primary `**Tagline:**` line is non-empty, <=80 chars, and banned-word-clean.
- **Full suite green:** 314 -> **317 passed** (+3), scoring coverage still **100%** (gate >=90% unchanged — the new test is not under `--cov=scoring`).

## Task Commits

Each task was committed atomically:

1. **Task 1: Write the three submission/*.md files** - `d693de9` (feat)
2. **Task 2: Add tests/test_submission_language.py — banned-vocab gate + tagline limit** - `f323e21` (test)

**Plan metadata:** (final docs commit — this SUMMARY + STATE + ROADMAP + REQUIREMENTS)

## Files Created/Modified

- `submission/demo-script.md` - SUBM-01 90-second demo storyboard with the verified GlassDesk 3465 anomaly beat and HUMAN-ONLY Docker marker
- `submission/x-post-draft.md` - SUBM-02 #OKXAI launch thread, neutral/factual, determinism + on-chain angle
- `submission/listing-copy.md` - SUBM-03 ASP listing fields with a 66-char primary tagline, Software Services, 0.01 USDT
- `tests/test_submission_language.py` - OPS-03 banned-vocab gate over submission/ + README.md and the tagline <=80-char assertion

## Decisions Made

- Selected the 66-char tagline "Deterministic trust scores for OKX.AI agents, in one paid MCP call" as primary (shortest, most direct of the five verified options); the other four are documented alternates with char counts.
- The `**Tagline:**` single-line marker is the tested contract for the length assertion, keeping the test self-contained and robust (no fuzzy table parsing).
- The language gate scans `submission/*.md` + `README.md` only, never source directories — so `indexer/category.py`'s legitimate "scam"/"rug" keyword table can never trip it (regex literal lives in `tests/`, matching the canonical `test_scoring_golden.py` pattern).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Neutral-language checklists tripped the banned-vocab gate they described**
- **Found during:** Task 1 (running Task 1's own automated verification)
- **Issue:** The "neutral-language checklist" lines in `demo-script.md` and `x-post-draft.md` literally enumerated the banned tokens ("The words 'fraud', 'scam', 'fake', 'manipulat*' appear nowhere...") — self-defeating, since those files are the exact scan targets. Task 1's verification (and Task 2's gate) matched the regex on `demo-script.md:67` and `x-post-draft.md:67`.
- **Fix:** Rephrased both lines to reference "the banned accusatory vocabulary" and the enforcing test without spelling out the forbidden tokens. `listing-copy.md` had no such line (already clean).
- **Files modified:** submission/demo-script.md, submission/x-post-draft.md
- **Verification:** Task 1's automated command re-run -> "submission kit OK"; full-tree outward-text audit -> "banned hits: NONE"; `tests/test_submission_language.py` -> 3 passed.
- **Committed in:** d693de9 (Task 1 commit — fixed before commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** The fix was necessary for correctness — the copy must satisfy the neutral-language contract it documents. No scope change; both files still convey the same guidance, just without quoting the forbidden tokens.

## Issues Encountered

- The em-dash (`—`) in three taglines renders as `�` on the Windows cp1252 console, but Python counts it as one code point (which is what the test measures), so the 77/78-char counts are correct and the gate reads files as UTF-8. No action needed beyond noting it.

## User Setup Required

None - no external service configuration required. (Recording the demo, posting the thread, and submitting the listing remain HUMAN-ONLY steps for the final checklist, as designed — this plan produces the materials, it does not execute those steps.)

## Next Phase Readiness

- This is the final plan of Phase 5 (3/3) and the last plan of the v1.0 milestone — the submission kit is complete and the outward-language contract is mechanically enforced.
- Ready for `/gsd-complete-milestone`: all SUBM-01..03 + OPS-03 artifacts exist, full suite is green (317 passed, coverage 100%), and the demo script is executable against `docker compose up`.
- Carried human-only items for the final checklist: start the Docker Desktop engine (Phase-3/4 blocker) to rehearse `docker compose up` + the demo end-to-end; then the human-only deploy / ASP registration / X post / hackathon form steps.

## Self-Check: PASSED

- Files verified present: `submission/demo-script.md` (67 lines, min 40), `submission/x-post-draft.md`, `submission/listing-copy.md`, `tests/test_submission_language.py` (60 lines, min 30), `05-03-SUMMARY.md`.
- Commits verified in git log: `d693de9` (Task 1 feat), `f323e21` (Task 2 test).
- `must_haves` artifacts + `contains` tokens all satisfied (GlassDesk, #OKXAI, Software Services); language gate green over submission/ + README; primary tagline 66 chars (<=80).

---
*Phase: 05-scraper-hardening-submission-kit*
*Completed: 2026-07-11*
