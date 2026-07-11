---
phase: 04-x402-payment-layer
plan: 02
subsystem: testing
tags: [x402, pytest, asgi, payments, fastmcp, testclient, threat-model, security-audit]

# Dependency graph
requires:
  - phase: 04-01
    provides: server/payments.py (X402Middleware, PaymentConfig, verifier seam), create_app(payment_config=) injection, migrated Phase 3 e2e
  - phase: 03-mcp-server-leaderboard
    provides: create_app() composition, web.build.build, MCP tools, tests/conftest.py real_db fixture
provides:
  - "tests/test_payments.py — 15 unit proofs (conversion table, golden requirement bytes, X402_MOCK 9-case fail-closed matrix, verifier seam, allowlist, predicate, last-key-wins classifier)"
  - "tests/test_payments_gate.py — 18 wire proofs through create_app(): OKX pre-registration check (both paths, both verifier modes), free handshake, mock-paid one-session e2e (3345/A/94 + receipt), threat probes T-04-01..07 + T-04-12 + 64KiB->413"
  - "Test-mapped STRIDE threat register (T-04-01..14) ready for the gsd-secure-phase audit — every research-proven probe is a named permanent test"
affects: [05-hardening-submission, gsd-secure-phase, phase-5-readme-registration, ops-03-e2e-signoff]

# Tech tracking
tech-stack:
  added: []  # zero new deps — asyncio.run for async verifier methods (no pytest-asyncio)
  patterns:
    - "Hermetic gate tests: config injected via create_app(payment_config=PaymentConfig(...)); never os.environ/monkeypatch"
    - "Both-paths assertion (Pitfall 8): every gated-path test covers /mcp AND /mcp/ (raw vs rewritten code routes)"
    - "Golden-byte regeneration identity: encode_header(canonical_json(build_requirements(cfg))) pinned against research golden"
    - "Async verifier tested via asyncio.run inside sync tests (no pytest-asyncio dependency added)"

key-files:
  created:
    - tests/test_payments.py
    - tests/test_payments_gate.py
  modified: []

key-decisions:
  - "Transcribed the PoC proof suite (69/69) verbatim into pytest form — a failing test signals implementation regression, not a wrong expectation"
  - "Folded the TypeError-on-float and X402_MOCK-unset cases into their parent parametrized tests to keep exactly 15 named unit functions (plan acceptance grep gate)"

patterns-established:
  - "Threat register is test-mapped: each STRIDE row (T-04-01..14) names the exact test that verifies it — the deliverable format for the security audit"
  - "Full-suite runs enforce the scoring coverage gate; payment-only subset runs use --no-cov (Pitfall 6)"

requirements-completed: [PAYX-01, PAYX-02, PAYX-03]

# Metrics
duration: 7min
completed: 2026-07-11
---

# Phase 4 Plan 02: Payment Proof Matrix Summary

**33 permanent pytest proofs pin the entire x402 PoC (69/69) — unit conversion/golden/config/verifier layer + wire OKX-check/paid-e2e/threat matrix through create_app() — with a test-mapped STRIDE register for the upcoming security audit; full suite 283 green, scoring coverage 100%.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-11T14:23:53Z
- **Completed:** 2026-07-11T14:31:17Z
- **Tasks:** 2
- **Files modified:** 2 (both created)

## Accomplishments
- **PAYX-01 pinned:** zero-header bodyless POST -> 402 + `PAYMENT-REQUIRED` decoding byte-for-byte to the locked requirements JSON, on both `/mcp` and `/mcp/`, in both mock and unconfigured modes; golden requirement bytes pinned.
- **PAYX-02 pinned:** the money e2e — unpaid `tools/call` -> 402, then the SAME session with `PAYMENT-SIGNATURE` -> real 3345/A/94 card + `PAYMENT-RESPONSE` receipt; `UnconfiguredVerifier` 402s everything paid even WITH a signature (fail-closed).
- **PAYX-03 pinned:** `X402_MOCK` exact-"1" 9-case fail-closed matrix, all-5-env-vars read test, placeholder-payTo startup warning (fires when unset, silent for a real address).
- **Security audit prep:** all 8 research threat probes + the 413 body cap + percent-encoding probe are permanent tests, each mapped to a STRIDE row (T-04-01..14).
- **Live corroboration:** live-uvicorn OKX curl (both paths) + Inspector CLI mock-paid e2e reproduced the research transcripts exactly (below).

## Task Commits

Each task was committed atomically:

1. **Task 1: tests/test_payments.py — unit proof matrix** - `6b7ff14` (test)
2. **Task 2: tests/test_payments_gate.py — wire proofs, threat matrix, mock-paid e2e** - `86d7687` (test)

**Plan metadata:** (this SUMMARY + STATE/ROADMAP/REQUIREMENTS) — see final `docs(04-02)` commit.

## Files Created/Modified
- `tests/test_payments.py` - 15 unit proofs (35 pytest cases w/ parametrization): 7-case conversion table + 8 rejections (incl. NaN/Infinity/float-TypeError), byte-stable + golden requirement bytes, b64 round-trip, X402_MOCK 9-case matrix, all-5-env read, placeholder warning, make_verifier banners, Mock/Unconfigured verifier semantics via `asyncio.run`, exact 7-member `FREE_METHODS` allowlist (default-paid), `_gated` predicate, last-key-wins `jsonrpc_method`.
- `tests/test_payments_gate.py` - 18 wire proofs through `create_app()`: OKX pre-registration check (both paths, both verifier modes), free handshake + unpaid tools/list, Inspector bootstrap plumbing free, unpaid-402-then-paid-retry-one-session e2e (3345/A/94 + receipt), CJK replay fidelity, mock replay (documented limitation), free routes + GET/DELETE pass-through in both modes, unconfigured fail-closed even with signature, threat probes T-04-01..07 + T-04-12 + 413 cap.

## Decisions Made
- **Transcribed, not re-derived:** the tests are the pytest form of the proven PoC suite; every expectation was already executed (69/69), so green-on-first-run was the expected and observed outcome.
- **Kept exactly 15 unit test functions** to satisfy the plan's `grep -c "^def test_"` acceptance gate: the float→TypeError case lives as a second assert inside `test_usdt_to_atomic_rejections`, and the X402_MOCK-unset case as a trailing assert inside `test_x402_mock_exact_one_fail_closed` (both as the plan text specifies — "separate assert" / "ninth case as a separate line").

## Deviations from Plan

None - plan executed exactly as written.

The x402 module was PoC-proven (69/69) before this plan, so no threat/property test surfaced a real bug in `server/payments.py`; no Rule 1-4 deviations were triggered. Every acceptance criterion (isolated runs, all grep gates, full-suite green with coverage) passed on the first run.

**Note on test counts:** the plan estimated ~245 / ~263 passing at the function level; pytest counts parametrized cases individually, so Task 1's parametrized property tables expand the raw total. Observed: 265 after Task 1, 283 after Task 2 (230 baseline + 35 + 18 pytest cases). The binding invariant — full suite exits 0 with the scoring coverage gate ≥90% intact — holds throughout.

## Issues Encountered
None. The pre-existing cosmetic `StarletteDeprecationWarning` (httpx/testclient, Pitfall 7) was left untouched by design — `httpx2` would be a forbidden new dependency.

## Verification Evidence

### Test suite
- `python -m pytest tests/test_payments.py -q --no-cov` -> 35 passed
- `python -m pytest tests/test_payments_gate.py -q --no-cov` -> 18 passed
- `python -m pytest -q` -> **283 passed, 1 warning**; scoring coverage **100.00%** (gate ≥90% intact)
- All acceptance grep gates green: unit `def_count=15 / loadbearing=4 / eip155=3 / envmutation=0`; gate `def_count=18 / loadbearing=4 / bothpaths=3 / cfg_inject=2 / envmutation=0 / score94=1`.

### Live-uvicorn rehearsal (`X402_MOCK=1 python -m uvicorn server.main:app --port 8402`)
Startup banners fired at boot (proving the mode-selection + config warning paths):
```
TRUSTLENS_PAY_TO is unset - using the placeholder address; real payments CANNOT settle until it is configured
X402_MOCK=1 - payments are NOT verified (mock mode)
```
The OKX pre-registration check, both paths:
```
$ curl -s -i -X POST http://127.0.0.1:8402/mcp | head -8
HTTP/1.1 402 Payment Required
date: Sat, 11 Jul 2026 14:29:38 GMT
server: uvicorn
content-type: application/json
content-length: 389
PAYMENT-REQUIRED: eyJhY2NlcHRzIjpb...(base64 of the exact body bytes)...

{"accepts":[{"amount":"10000","asset":"0x779ded0c9e...","maxTimeoutSeconds":300,"network":"eip155:196","payTo":"0x0000...0000","scheme":"exact"}],"resource":{...,"url":"http://localhost:8000/mcp"},"x402Version":2}

$ curl -s -i -X POST http://127.0.0.1:8402/mcp/ | head -3
HTTP/1.1 402 Payment Required          # byte-identical 402 on the rewritten path
```
Verified: the `PAYMENT-REQUIRED` header base64-decodes to **exactly** the response body (`MATCH`).

### Inspector CLI mock-paid e2e (MCPS-05 continuity — asserted on stdout, Windows quirk)
```
tools/list (FREE, no header)  -> category_leaderboard, compare_agents, marketplace_stats, score_agent
tools/call score_agent 3345 (PAID via --header "PAYMENT-SIGNATURE: demo")
                              -> "agent_id":"3345", "grade":"A", "score":94
```

## STRIDE Threat Register (test-mapped — deliverable for gsd-secure-phase)

Every disposition from the plan's `<threat_model>` is now backed by a named permanent test:

| Threat ID | Category | Disposition | Verified By (test) |
|-----------|----------|-------------|--------------------|
| T-04-01 | Tampering | mitigate | `test_threat_notification_form_tools_call` |
| T-04-02 | Tampering | mitigate | `test_threat_batch_smuggling` + unit `test_jsonrpc_method_classification` |
| T-04-03 | Tampering | mitigate | `test_threat_duplicate_keys_both_directions` + unit last-key-wins case |
| T-04-04 | Tampering | mitigate | `test_threat_content_type_tricks` |
| T-04-05 | DoS | mitigate | `test_threat_oversized_body_413` |
| T-04-06 | DoS | mitigate | `test_threat_garbage_never_500` |
| T-04-07 | Elevation/Revenue | mitigate | `test_threat_unknown_method_paid` + unit `test_free_methods_allowlist` |
| T-04-08 | Spoofing/Revenue | accept | `test_mock_replay_accepted_documented_limitation` (guarded by `test_x402_mock_exact_one_fail_closed`) |
| T-04-09 | Injection | mitigate | receipt shape asserted server-constructed in `test_unpaid_tools_call_402_then_paid_retry_same_session` |
| T-04-10 | Spoofing | mitigate | unit `test_requirements_locked_fields` (config-derived URL incl. rstrip; never Host) |
| T-04-11 | Info disclosure | accept | `test_get_delete_pass_gate` |
| T-04-12 | Tampering | mitigate | `test_threat_percent_encoded_path` + unit `test_gated_predicate` |
| T-04-13 | Spoofing | mitigate | unit `test_x402_mock_exact_one_fail_closed` + `test_make_verifier_selection_and_banners` + `test_unconfigured_fail_closed_even_with_signature` |
| T-04-14 | Info disclosure | mitigate | unit `test_placeholder_payto_warning` + `test_from_env_reads_all_five_vars` (+ 04-01 address-census grep gate) |

## Threat Flags
None — this plan adds tests only; it introduces no new network endpoints, auth paths, file access, or trust-boundary schema changes beyond the surface already pinned by the register above.

## Known Stubs
None — both files are complete test suites wired to the real `server.payments` exports and the real `create_app()` + seeded `data/trustlens.db` (agent 3345 -> A/94). No placeholder data, no unwired components.

## User Setup Required
None - no external service configuration required for the tests. The one standing HUMAN step for the phase goal's "against local Docker" clause is unchanged: start the Docker Desktop engine and run the 6 manual steps in `03-05-SUMMARY.md`, then the same OKX curl (verified here in-process and against live uvicorn) against the container port completes the registration rehearsal. All code-side proofs are covered by the in-process + live-uvicorn evidence above.

## Next Phase Readiness
- Phase 4 is code-complete and fully proof-pinned: 33 new tests, full suite 283 green, scoring coverage 100%.
- The test-mapped STRIDE register (T-04-01..14) is ready for the `gsd-secure-phase` audit — every threat names its verifying test.
- Standing for Phase 5: README/deploy/ASP-registration docs (OPS-02); the deploy-time `okxweb3-app-x402` facilitator drops into the `UnconfiguredVerifier` seam (PAYX-04, human-gated); the Docker curl rehearsal awaits a working Docker engine (03-05 human step).

## Self-Check: PASSED

- FOUND: `tests/test_payments.py`
- FOUND: `tests/test_payments_gate.py`
- FOUND: `.planning/phases/04-x402-payment-layer/04-02-SUMMARY.md`
- FOUND commit: `6b7ff14` (Task 1)
- FOUND commit: `86d7687` (Task 2)

---
*Phase: 04-x402-payment-layer*
*Completed: 2026-07-11*
