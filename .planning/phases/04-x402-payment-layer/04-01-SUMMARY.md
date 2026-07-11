---
phase: 04-x402-payment-layer
plan: 01
subsystem: payments
tags: [x402, asgi-middleware, fastapi, starlette, mcp, usdt, x-layer, base64, decimal]

# Dependency graph
requires:
  - phase: 03-mcp-server-leaderboard
    provides: create_app() one-port composition (McpPathRewrite, /mcp mount, /healthz, /badge, static), tools/call scoring path, test_server_app e2e suite
provides:
  - server/payments.py — x402 v2 payment layer (PaymentConfig, requirements JSON, PaymentVerifier seam, X402Middleware ASGI gate)
  - create_app(payment_config=None) with X402Middleware registered outermost (LIFO after McpPathRewrite)
  - Bodyless POST /mcp and /mcp/ -> HTTP 402 + PAYMENT-REQUIRED (OKX pre-registration check passes by construction)
  - MockVerifier / UnconfiguredVerifier fail-closed seam (exact X402_MOCK="1") for the deploy-time okxweb3-app-x402 facilitator swap
  - .env.example documenting all 5 payment env vars
affects: [05-hardening-launch, README ASP registration, OPS-03 e2e sign-off, gsd-secure-phase audit, PAYX-04 facilitator integration]

# Tech tracking
tech-stack:
  added: []  # stdlib only (base64/json/decimal/dataclasses/typing) — no new runtime deps
  patterns:
    - "Pure-ASGI middleware (NOT BaseHTTPMiddleware) — buffer-and-replay so the gate reads the JSON-RPC method without destructively consuming the body"
    - "add_middleware LIFO ordering: register the outermost wrapper LAST so it sees raw paths before McpPathRewrite"
    - "Config injection mirrors db_path/static_dir: payment_config=None -> PaymentConfig.from_env(); tests inject without mutating os.environ"
    - "Byte-stable canonical_json (sorted keys, compact separators, ASCII) reused for BOTH the 402 body and the base64 PAYMENT-REQUIRED header"
    - "Fail-closed allowlist: FREE_METHODS enumerates plumbing; every unknown/future method (incl. tools/call, completion/complete) is PAID by default"

key-files:
  created:
    - server/payments.py — x402 v2 config, requirements, verifier seam, ASGI gate (373 lines)
    - .env.example — 5 payment env vars with placeholders + comments (PAYX-03)
  modified:
    - server/app.py — import + create_app(payment_config=None) + X402Middleware registered after McpPathRewrite
    - tests/test_server_app.py — mock-paid e2e migration (PaymentConfig(mock=True) fixture, PAYMENT-SIGNATURE in shared H, hermetic PaymentConfig() in healthz-503)

key-decisions:
  - "payments.py transcribed PoC-verbatim; only deltas are the production docstring and logger name payments -> server.payments"
  - "Mock token is any non-empty PAYMENT-SIGNATURE value (documented; demo token 'demo-mock-token')"
  - "X402Middleware outermost via add_middleware AFTER McpPathRewrite — prefix predicate (path=='/mcp' or startswith '/mcp/') answers the bare OKX curl; exact-match gate provably fails it"
  - "Phase 3 e2e tests migrated to mock-paid flow: unpaid tools/call now 402s by design, so the client fixture injects PaymentConfig(mock=True) and free methods ignore the signature header"

patterns-established:
  - "Verifier seam (Protocol + Mock/Unconfigured + make_verifier single selection point) is the exact swap-in point for the real facilitator at deploy"
  - "64 KiB body cap enforced BEFORE JSON parsing -> 413 payload_too_large (DoS guard); garbage/invalid bytes -> 402 never 500"

requirements-completed: [PAYX-01, PAYX-02, PAYX-03]

# Metrics
duration: 17min
completed: 2026-07-11
---

# Phase 4 Plan 01: x402 Payment Layer Summary

**x402 v2 payment gate live: bodyless POST /mcp answers HTTP 402 + PAYMENT-REQUIRED (base64 of the requirements JSON), a mock-verified tools/call returns the real score card + PAYMENT-RESPONSE receipt, and the whole thing rides pure-ASGI middleware wired outermost in create_app() with the Phase 3 e2e suite migrated to the mock-paid flow.**

## Performance

- **Duration:** ~17 min
- **Started:** 2026-07-11T14:00Z
- **Completed:** 2026-07-11T14:17Z
- **Tasks:** 2
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `server/payments.py` transcribed PoC-verbatim (69/69 proof assertions preserved) — PaymentConfig, usdt_to_atomic (Decimal, never float), build_requirements/canonical_json/encode_header, PaymentVerifier Protocol, MockVerifier/UnconfiguredVerifier/make_verifier, and the X402Middleware pure-ASGI gate.
- X402Middleware wired into `create_app(payment_config=None)`, registered AFTER McpPathRewrite so LIFO makes it the OUTERMOST middleware (sees raw `/mcp` and `/mcp/`).
- OKX pre-registration check passes by construction: bodyless POST to both `/mcp` and `/mcp/` return byte-identical 402s whose PAYMENT-REQUIRED header base64-decodes to exactly the body (`scheme=exact`, `network=eip155:196`, `amount=10000`).
- `.env.example` created documenting all 5 payment env vars with placeholders and comments; `.env` stays git+docker-ignored; address census in `server/*.py` is exactly the two allowed public constants.
- Phase 3 e2e tests migrated to the mock-paid flow (unpaid tools/call now 402s by design) — full suite stays at 230 passed with the scoring coverage gate at 100%.

## Task Commits

Each task was committed atomically:

1. **Task 1: Transcribe server/payments.py from the PoC + create .env.example** - `fab1ee8` (feat)
2. **Task 2: Wire the gate into create_app() and migrate the Phase 3 e2e tests** - `647dc66` (feat)

**Plan metadata:** (this commit) (docs: complete plan)

## Files Created/Modified
- `server/payments.py` (created) - x402 v2 payment layer: config, atomic-amount conversion, byte-stable requirements JSON, verifier seam, and the pure-ASGI 402 gate.
- `.env.example` (created) - TRUSTLENS_PAY_TO, TRUSTLENS_PRICE_USDT, X_LAYER_RPC, X402_MOCK, TRUSTLENS_BASE_URL with placeholders + comments.
- `server/app.py` (modified) - import PaymentConfig/X402Middleware; add `payment_config` param to create_app; register `X402Middleware` after `McpPathRewrite` (LIFO outermost).
- `tests/test_server_app.py` (modified) - inject `PaymentConfig(mock=True)` in the client fixture, add `PAYMENT-SIGNATURE` to the shared `H` dict, and use a hermetic `PaymentConfig()` in the healthz-503 test.

## Decisions Made
- **Two transcription deltas only.** `server/payments.py` is the research PoC (`x402_poc.py`) verbatim; the only intentional changes are (1) the production module docstring and (2) the logger name `"payments"` -> `"server.payments"` (matches the `server.app` convention; the caplog tests in plan 04-02 assert this name). Verified by `diff` against the PoC — nothing else differs.
- **Middleware ordering proof.** `add_middleware` is LIFO, so registering `X402Middleware` AFTER `McpPathRewrite` makes it `user_middleware[0]` (outermost). It therefore sees raw paths and its prefix predicate answers the bare `POST /mcp`. `[m.cls.__name__ for m in app.user_middleware] == ['X402Middleware', 'McpPathRewrite']` is pinned in Task 2 AC2. An exact-match gate provably fails the OKX check (04-RESEARCH negative proof).
- **e2e migration rationale.** Under the env-derived `UnconfiguredVerifier`, an unpaid HTTP `tools/call` now 402s — which is correct-by-design but would break the Phase 3 tests. The migration switches the client fixture to `PaymentConfig(mock=True)` and adds a mock `PAYMENT-SIGNATURE` to the shared header dict; free methods (initialize, notifications/initialized, tools/list) ignore the signature, and paid tools/call consumes it (proven Inspector behavior). `test_route_order`'s sessionless tools/list still expects 400 (FREE -> replayed to the MCP app, which rejects the missing session exactly as before). The healthz-503 test injects a hermetic `PaymentConfig()` so it never reads a demo shell's ambient `X402_MOCK`.
- **Mock token format.** Documented as any non-empty `PAYMENT-SIGNATURE` value; the tests use `"demo-mock-token"`. Replay is accepted in mock mode (documented limitation; the real facilitator enforces nonces on-chain).

## Deviations from Plan

None - plan executed exactly as written. Both tasks followed the plan's embedded content and edit specs verbatim; every acceptance criterion and the plan-level verification block passed on the first run.

## Issues Encountered
None. The PoC source in the scratchpad was still present and diffed clean (only the two documented deltas). Baseline was 230 passed before and after each task. Git line-ending normalization warnings (LF -> CRLF on Windows) are cosmetic, not errors.

## TDD Gate Compliance
N/A - plan type is `execute`, not `tdd`. Tests for the payment module's unit/property/threat surface land in plan 04-02; this plan preserves the existing 230-test suite green (the Phase 3 e2e tests were migrated, not removed) and proves the wire behavior via the in-process OKX pre-registration check.

## Security Notes (threat_model dispositions honored)
- T-04-05 DoS: 64 KiB body cap enforced before JSON parsing -> 413 (present in X402Middleware).
- T-04-06 fail-closed parse: garbage/invalid bytes -> 402, never 500 (jsonrpc_method returns None -> paid path -> 402).
- T-04-07 revenue: FREE_METHODS is an allowlist; tools/call and unknown methods (completion/complete, tools/execute_all) are PAID by default — asserted in Task 1 AC3.
- T-04-13 mode selection: `env.get("X402_MOCK") == "1"` exact-string parse, single selection point in make_verifier with a loud startup banner.
- T-04-14 secrets: env-only config; `.env` git+docker-ignored (verified 1/1); `.env.example` placeholders only; address census clean (exactly the two public constants); placeholder payTo fires a startup warning.
- No new threat surface introduced beyond the plan's `<threat_model>`.

## Next Phase Readiness
- PAYX-01/02/03 satisfied; the verifier seam is the documented swap-in point for `okxweb3-app-x402` at deploy (PAYX-04, human-gated).
- The in-process OKX pre-registration check passes, so the live `curl -i -X POST https://domain/mcp` rehearsal (against local Docker, once Docker Desktop starts — carried blocker from 03-05) is expected to pass.
- Plan 04-02 (payment module unit/property/threat tests) can proceed; the logger name `server.payments` is in place for its caplog assertions.
- README ASP registration section and formal OPS-03 sign-off remain Phase 5.

## Self-Check: PASSED

- FOUND: server/payments.py
- FOUND: .env.example
- FOUND: .planning/phases/04-x402-payment-layer/04-01-SUMMARY.md
- FOUND commit: fab1ee8 (Task 1)
- FOUND commit: 647dc66 (Task 2)

---
*Phase: 04-x402-payment-layer*
*Completed: 2026-07-11*
