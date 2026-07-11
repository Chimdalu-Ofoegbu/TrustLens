---
phase: 04-x402-payment-layer
audit: gsd-secure-phase
asvs_level: 1
block_on: HIGH
threats_total: 14
threats_mitigated: 12
threats_accepted: 2
threats_open: 0
high_findings: 0
result: SECURED
audited: 2026-07-11
scope:
  - server/payments.py
  - server/app.py
  - .env.example
  - tests/test_payments.py
  - tests/test_payments_gate.py
verification:
  full_suite: "283 passed, scoring coverage 100% (gate >=90% intact)"
  payment_subset: "62 passed (35 unit + 18 gate + 9 migrated e2e)"
  address_census: "clean — exactly the 2 public constants across the whole repo"
---

# Phase 4 Security Audit — x402 Payment Layer

**Result: SECURED.** All 14 STRIDE threats in the Phase 4 register resolve: 12 `mitigate`
dispositions are present in the implemented code AND exercised by their named pinned test;
2 `accept` dispositions (T-04-08 mock replay, T-04-11 GET /mcp pass-through) are legitimately
bounded, documented, and not masking a real hole. **0 open threats. 0 HIGH findings.**

Every mitigation was verified against the code at a specific `file:line`, not accepted on
documentation or intent. Every named test was run and confirmed to pass (not merely to exist).

- Full suite: `python -m pytest -q` → **283 passed**, scoring coverage **100%** (gate ≥90%).
- Payment subset: `test_payments.py` + `test_payments_gate.py` + `test_server_app.py` → **62 passed**.
- Whole-repo address census: exactly `0x0000…0000` (placeholder) + `0x779ded…713736` (X Layer
  USDT). No hardcoded wallet or secret anywhere. (`0x1111…1111` appears once as an env-only
  carry-through **test literal** in `test_payments.py:107`, not a secret.)

## Per-Threat Verification

| Threat ID | Category | Disposition | Verified | Code Evidence (file:line) | Test Evidence (confirmed passing) |
|-----------|----------|-------------|----------|---------------------------|-----------------------------------|
| T-04-01 | Tampering — method classification | mitigate | ✅ | `payments.py:323-324` gate keys on `jsonrpc_method(body)` (reads `method` only; id-presence never consulted — `jsonrpc_method` at :249-266 ignores `id`) | `test_threat_notification_form_tools_call` (id_=None tools/call → 402) |
| T-04-02 | Tampering — JSON arrays / batches | mitigate | ✅ | `payments.py:263` `if not isinstance(msg, dict): return None` → array → None → paid path → 402 | `test_threat_batch_smuggling` + unit `test_jsonrpc_method_classification` (`[1,2,3]` → None) |
| T-04-03 | Tampering — duplicate-key smuggling | mitigate | ✅ | `payments.py:260` gate uses `json.loads`; MCP server uses the same stdlib `json.loads` — both last-key-wins, cannot diverge | `test_threat_duplicate_keys_both_directions` (both directions) + unit last-key-wins case (`…"method":"a","method":"b"` == "b") |
| T-04-04 | Tampering — content-type tricks | mitigate | ✅ | `payments.py:321-323` classification reads raw buffered `body` bytes; Content-Type header never read | `test_threat_content_type_tricks` (text/plain tools/call → 402) |
| T-04-05 | DoS — body-buffer cap | mitigate | ✅ | `payments.py:311-316` `if size > MAX_BODY_BYTES: return … 413` — checked **during** the receive loop, before `json.loads`; never an unbounded read | `test_threat_oversized_body_413` (413 + `{"error":"payload_too_large","max_bytes":65536}`) |
| T-04-06 | DoS — fail-closed parse | mitigate | ✅ | `payments.py:259-266` `except (ValueError, UnicodeDecodeError): return None` → paid path → 402, never 500 | `test_threat_garbage_never_500` (4 garbage payloads + trailing-slash path → all 402) |
| T-04-07 | Elevation/Revenue — allowlist default-paid | mitigate | ✅ | `payments.py:54-55` `is_free` = membership-or-prefix allowlist; `:324` only frees when `is_free(method)` is true — unknown/`tools/call` fall through to paid | `test_threat_unknown_method_paid` (tools/execute_all + completion/complete → 402) + unit `test_free_methods_allowlist` |
| T-04-08 | Spoofing/Revenue — mock replay | **accept** | ✅ | Bounded: activation gated by exact `"1"` (`payments.py:81`); loud banner `:217`; documented as accepted limitation in `MockVerifier` docstring `:178-183`; real facilitator enforces on-chain nonces at the deploy seam | `test_mock_replay_accepted_documented_limitation` (pins the documented behavior); activation guarded by `test_x402_mock_exact_one_fail_closed` |
| T-04-09 | Injection — response headers | mitigate | ✅ | `payments.py:334-335` receipt is `settle()` output (server constants + config only, `:193-200`); no request data echoed. 402 headers precomputed in `__init__` `:289-290` | receipt shape asserted server-constructed in `test_unpaid_tools_call_402_then_paid_retry_same_session` |
| T-04-10 | Spoofing — resource.url derivation | mitigate | ✅ | `payments.py:130` `cfg.base_url.rstrip("/") + "/mcp"` — from config, never the request Host header (gate never reads Host) | unit `test_requirements_locked_fields` (config-derived URL incl. rstrip case) |
| T-04-11 | Info disclosure — GET /mcp pass-through | **accept** | ✅ | Bounded: `_gated` at `payments.py:294` returns true only for `method == "POST"`; GET carries only server-initiated notifications for an existing session; tool results flow exclusively on gated POST `tools/call` | `test_get_delete_pass_gate` (GET/DELETE /mcp → not 402; money path proven paid-only) |
| T-04-12 | Tampering — path predicate vs encoding | mitigate | ✅ | `payments.py:293-295` predicate matches decoded `scope["path"]` (uvicorn/TestClient decode before ASGI); tight `== "/mcp" or startswith("/mcp/")` — `/mcpfoo` NOT gated | `test_threat_percent_encoded_path` (`/mcp%2Ffoo` → 402; `/mcpfoo` → 404/405, not 402) + unit `test_gated_predicate` |
| T-04-13 | Spoofing — mock-mode activation | mitigate | ✅ | `payments.py:81` `env.get("X402_MOCK") == "1"` — the ONLY parse (grep-confirmed 1/1); single selection point `make_verifier` `:215-220` with startup banner | unit `test_x402_mock_exact_one_fail_closed` (9-case matrix) + `test_make_verifier_selection_and_banners` + `test_unconfigured_fail_closed_even_with_signature` |
| T-04-14 | Info disclosure/Repudiation — secrets/config | mitigate | ✅ | Env-only (`from_env` `:73-89`); `.env` git+docker-ignored (1/1 each); `.env.example` placeholders only; whole-repo address census = exactly 2 public constants; placeholder-payTo warning `:84-88` | unit `test_placeholder_payto_warning` + `test_from_env_reads_all_five_vars` + 04-01 address-census grep gate |

## Special-Attention Items (explicitly requested)

| Item | Verdict | Evidence |
|------|---------|----------|
| X402_MOCK cannot enable by accident — only exact `"1"` | ✅ PASS | `env.get("X402_MOCK") == "1"` is the sole parse (`payments.py:81`, grep `-Fc` = 1). No `bool()`, no truthiness, no case-fold, no strip. 9-case matrix pins `"0"/"true"/"TRUE"/"yes"/" 1"/"1 "/""`/unset all → `mock is False`. |
| UnconfiguredVerifier fails closed 402 even WITH a signature | ✅ PASS | `UnconfiguredVerifier.verify` returns `False` unconditionally (`payments.py:208-209`); gate 402s when `verify` is false (`:329-332`). `test_unconfigured_verifier_fail_closed` (unit) + `test_unconfigured_fail_closed_even_with_signature` (wire: signature present → 402). Default (no creds) yields this verifier via `make_verifier` `:219-220`. |
| No hardcoded secrets/addresses beyond the 2 public constants | ✅ PASS | Whole-repo census (all `.py/.md/.example/.json/.yml/.toml/.html/.js/.svg`): only `0x0000…0000` and `0x779ded…713736`. `0x1111…1111` is an env-only carry-through test literal (`test_payments.py:107`). No private keys, no wallet literals. |
| Body-buffer DoS cap enforced (413, never unbounded read) | ✅ PASS | Cap checked inside the receive loop before parse (`payments.py:311-316`); returns 413 and stops reading. `test_threat_oversized_body_413`. |
| Gate cannot be bypassed — notification-form, batch, dup-key, content-type, path-encoding | ✅ PASS | Each has both a code path and a passing test: T-04-01, T-04-02, T-04-03, T-04-04, T-04-12 above. All keyed on the same-parser `method`-only classification of raw bytes. |
| Determinism of requirements bytes; no Host-derived resource.url | ✅ PASS | `canonical_json` sorts keys + compact + ASCII (`payments.py:150-158`); golden bytes pinned (`test_requirements_golden_bytes`); 402 header/body precomputed once in `__init__` (`:289-290`); `resource.url` from `cfg.base_url`, never Host (T-04-10). |

## Accepted-Risk Register

Both ACCEPT dispositions were verified legitimate — documented, bounded, and not concealing an
exploitable gap in the paid path.

### T-04-08 — MockVerifier replay (accept)
- **Bound:** Only reachable when `X402_MOCK == "1"` (exact string; grep-confirmed single parse).
  Production default is `UnconfiguredVerifier`, which 402s everything.
- **Documented:** `MockVerifier` docstring (`payments.py:178-183`) states replay is not detected;
  `make_verifier` emits `"X402_MOCK=1 - payments are NOT verified (mock mode)"` at startup (`:217`).
- **Transferred at deploy:** the real `okxweb3-app-x402` facilitator enforces authorization
  nonces + validBefore on-chain at the same verifier seam (`UnconfiguredVerifier` swap-in point).
- **Not masking a hole:** mock mode is non-production by construction and cannot activate by accident.

### T-04-11 — GET /mcp (SSE channel) pass-through (accept)
- **Bound:** `_gated` returns true only for POST (`payments.py:294`); GET/DELETE pass untouched.
- **Rationale:** GET delivers only server-initiated notifications for an already-established
  session; tool *results* (the paid product) flow exclusively on gated POST `tools/call`.
- **Not masking a hole:** the revenue path is provably paid-only (`test_unpaid_tools_call_402_
  then_paid_retry_same_session`); GET cannot invoke a tool.

## Unregistered Flags (new attack surface with no threat mapping)

**None.**
- 04-02-SUMMARY `## Threat Flags`: "None — adds tests only; no new endpoints, auth paths, file
  access, or trust-boundary schema changes."
- 04-01-SUMMARY documents dispositions under `## Security Notes (threat_model dispositions
  honored)` and states "No new threat surface introduced beyond the plan's `<threat_model>`."
- Independent read of `server/payments.py` and the `server/app.py` middleware wiring surfaced no
  endpoint, header echo, or config path outside the 14-threat register.

## Files Audited (read-only — none modified)

- `server/payments.py` — the x402 gate, verifiers, config, conversion, canonical serializer
- `server/app.py` — middleware ordering (X402Middleware outermost via LIFO after McpPathRewrite)
- `.env.example` — 5 documented vars, placeholders only, no real values
- `tests/test_payments.py` — 15 unit proof functions (35 parametrized cases)
- `tests/test_payments_gate.py` — 18 wire proof functions
- `tests/test_server_app.py` — 9 migrated Phase 3 e2e tests (mock-paid flow)

*Audit disposition: SECURED. No blockers. Safe to ship Phase 4.*
