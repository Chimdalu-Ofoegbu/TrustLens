# Phase 4: x402 Payment Layer - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning
**Source:** PRD Express Path (../trustlens-claude-code-prompt.md) + OKX docs fetched 2026-07-10 + Phase 3 composition

<domain>
## Phase Boundary

Wrap the working Phase 3 service in the x402 v2 payment gate: unpaid MCP tool calls get HTTP 402 with payment requirements; mock-verified calls succeed under `X402_MOCK=1`; verification is a pluggable seam for the real OKX SDK at deploy time. Requirements: PAYX-01, PAYX-02, PAYX-03. Real on-chain settlement (PAYX-04) stays v2/deploy-time — OKX API creds are a human stop condition.

</domain>

<decisions>
## Implementation Decisions

### Wire format (locked — from OKX A2MCP docs + verified x402 v2 ecosystem facts)
- 402 response carries BOTH: (a) the `PAYMENT-REQUIRED` header whose value is base64-encoded JSON of the payment requirements (x402 v2, Dec 2025 revision), and (b) the same JSON as the response body (human-debuggable; matches OKX A2MCP doc example)
- Payment requirements JSON shape (locked from the OKX doc example):
  `{"x402Version": 2, "resource": {"url": "<endpoint url>", "description": "<service description>", "mimeType": "application/json"}, "accepts": [{"scheme": "exact", "network": "eip155:196", "asset": "0x779ded0c9e1022225f8e0630b35a9b54be713736", "amount": "10000", "payTo": "<TRUSTLENS_PAY_TO>", "maxTimeoutSeconds": 300}]}`
- `amount` is an atomic-unit STRING: USDT on X Layer has 6 decimals → 0.01 USDT = `"10000"`; derive from `TRUSTLENS_PRICE_USDT` (e.g. "0.01") deterministically — never float math (use Decimal), never hardcode the amount
- Payment proof arrives on retry in the `PAYMENT-SIGNATURE` header; after verification the response includes a `PAYMENT-RESPONSE` header (settlement receipt echo — mock value in mock mode)
- The OKX pre-registration compliance check MUST pass by construction: bare `curl -i -X POST https://host/mcp` (no body, no session) → HTTP 402 + `PAYMENT-REQUIRED` header

### Gating policy (locked — from architecture research + Phase 3 composition)
- Pure-ASGI middleware (NOT BaseHTTPMiddleware) wrapping the app at the position marked by the Phase-3 LIFO comment in `server/app.py`
- PAID: MCP `tools/call` requests (the product)
- FREE: `/healthz`, `/` (leaderboard), `/badge/*`, and MCP protocol plumbing — `initialize`, `notifications/*`, `tools/list` — via a configurable `FREE_METHODS` set (one-line flip to gate everything, per the observed live OKX ASP that gates all methods)
- Bodyless or unparseable POSTs to /mcp → 402 with requirements (this is what makes the OKX curl check pass; never 500 on garbage)
- The gate inspects the JSON-RPC method WITHOUT consuming the body destructively (buffer & replay in pure ASGI — the reason BaseHTTPMiddleware is banned)

### Verifier seam (locked)
- `PaymentVerifier` Protocol with two methods (verify + settle semantics per architecture research); implementations:
  - `MockVerifier` — active ONLY when `X402_MOCK == "1"` (exact string compare, fail-closed parse); accepts a documented mock token format in `PAYMENT-SIGNATURE` (e.g. any non-empty value or a fixed test token — planner picks, must be deterministic and documented), returns a mock `PAYMENT-RESPONSE`
  - Production default when `X402_MOCK` unset/≠"1": fail-closed `UnconfiguredVerifier` that 402s every paid request with the requirements (service is safe-by-default without creds) — the README (Phase 5) documents swapping in `okxweb3-app-x402`'s facilitator/x402ResourceServer at exactly this seam
- Startup log line states the active verifier mode loudly; mock mode must be impossible to enable by accident (exact "1" only)

### Config (locked — PAYX-03 verbatim + brief)
- Environment variables ONLY: `TRUSTLENS_PAY_TO` (0x wallet, placeholder default "0x0000000000000000000000000000000000000000" with a startup warning when unset), `TRUSTLENS_PRICE_USDT` (default "0.01"), `X_LAYER_RPC` (default "https://rpc.xlayer.tech", used by the real SDK at deploy time — carried in config now), `X402_MOCK` (default unset)
- NEVER hardcode keys/addresses in code; `.env` stays gitignored; `.env.example` created THIS phase documenting every var with placeholder values and comments (fulfills the PAYX-03 acceptance surface; README section lands Phase 5)
- Config read once at app creation (env → dataclass), injectable for tests

### Tests (locked — PAYX-01/02 acceptance verbatim)
- Without payment → 402: assert status, PAYMENT-REQUIRED header present and base64-decodes to the exact requirements JSON (eip155:196, "10000", scheme exact), body JSON matches, applies to tools/call
- With X402_MOCK=1 + mock PAYMENT-SIGNATURE → tools/call returns the full scored result + PAYMENT-RESPONSE header
- FREE set proven: healthz, /, badge, initialize, tools/list all pass unpaid in mock AND unconfigured modes
- Bare `curl`-equivalent test: bodyless POST /mcp → 402 + header (the OKX pre-registration check, in-process)
- Determinism: requirements JSON byte-stable (sorted keys where applicable, fixed serialization)
- Full suite green (230 existing); scoring coverage gate unaffected
- e2e "one paid call" test through the HTTP app with x402 mocked — this satisfies the brief's OPS-03 e2e clause early (formal OPS-03 sign-off remains Phase 5)

### Git & conduct (locked)
- Commits authored by the user's git identity only; NEVER any AI attribution; conventional commits `feat(04-XX): ...`
- No new runtime deps (stdlib base64/json/hmac suffice); 2-attempt stop rule
- After execution this phase gets a security audit (gsd-secure-phase) — write threat models accordingly

### Claude's Discretion
- Module layout (`server/payments.py` vs package), exact FREE_METHODS constant shape
- Mock token format details (documented + deterministic)
- Requirements `resource.url` derivation (TRUSTLENS_BASE_URL + /mcp)
- PAYMENT-RESPONSE mock receipt shape

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/PROJECT.md` — x402 facts from OKX docs (challenge shape, SDK names, ASP registration), stop conditions
- `.planning/REQUIREMENTS.md` — PAYX-01..03 verbatim
- `.planning/research/ARCHITECTURE.md` — payment middleware placement, FREE_METHODS design, PaymentVerifier protocol, atomic-amount facts
- `.planning/research/PITFALLS.md` — x402 v2 base64 header, PAYMENT-SIGNATURE/PAYMENT-RESPONSE, mock fail-closed design, body buffer/replay
- `server/app.py` — the Phase-4 middleware position comment; McpPathRewrite interplay (gate must see rewritten paths consistently — decide order deliberately)
- `.planning/phases/03-mcp-server-leaderboard/03-RESEARCH.md` — wire sequence (session headers, json_response mode) the gate must not break
- `.env.example` — created this phase

</canonical_refs>

<specifics>
## Specific Ideas

- Brief verbatim: "respond 402 with payment requirements, verify settlement, then serve"; "Config … via environment variables only: TRUSTLENS_PAY_TO, TRUSTLENS_PRICE_USDT, X_LAYER_RPC"; "NEVER hardcode keys or addresses"; acceptance "With X402_MOCK=1, a call without payment returns 402 with payment requirements; a mock-paid call returns the score"
- OKX doc verbatim (pre-registration): "curl -i -X POST https://your-domain/your-path — Paid type: Expect HTTP 402 + PAYMENT-REQUIRED header"
- Demo (Phase 5) will show the 402→pay→result flow — keep the mock flow demo-friendly (clear headers, readable JSON)
</specifics>

<deferred>
## Deferred Ideas

- PAYX-04 real settlement via `okxweb3-app-x402` (OKX API creds = human stop condition) — the verifier seam + README docs are the v1 deliverable
- README/deploy/registration docs — Phase 5 (OPS-02)
</deferred>

---

*Phase: 04-x402-payment-layer*
*Context gathered: 2026-07-11 via PRD Express Path*
