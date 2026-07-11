# Phase 4: x402 Payment Layer - Research

**Researched:** 2026-07-11
**Domain:** x402 v2 payment gate (pure ASGI) wrapped around the Phase 3 FastMCP/FastAPI composition; mock verifier seam for the OKX facilitator SDK
**Confidence:** HIGH — the entire payment flow was proven with a working PoC on THIS machine (Python 3.14.2, fastmcp 3.4.4, starlette 1.3.1, uvicorn 0.51.0, Inspector 0.22.0) wrapped around the REAL `create_app()` and the real 272-agent `data/trustlens.db`. 69/69 proof assertions passed; the OKX curl check, the full curl session flow, and the Inspector CLI mock-paid e2e were all executed against live uvicorn. Code shapes below are transcribed from the working PoC.

## Summary

The pure-ASGI gate design from ARCHITECTURE.md works exactly as planned around the real Phase 3 app: bodyless `POST /mcp` → 402 + `PAYMENT-REQUIRED` (the OKX pre-registration check, verified with live curl on both `/mcp` and `/mcp/`), the unpaid MCP handshake passes free with session headers intact, unpaid `tools/call` 402s without consuming the session, and a mock-paid retry on the SAME session returns the real 3345/A/94 score card with a `PAYMENT-RESPONSE` receipt header. The `add_middleware(X402Middleware, ...)` registration form (the exact mechanism Phase 4 will use at the position marked in `server/app.py`) was proven equivalent to the external wrap.

**The one deviation research forces on the locked CONTEXT:** the locked FREE set (`initialize`, `notifications/*`, `tools/list`) **breaks MCP Inspector** — proven by request sniffing. Inspector 0.22.0's connect sequence sends `logging/setLevel` immediately after the handshake (because FastMCP advertises the `logging` capability), gets 402'd, and aborts the connection before ever calling `tools/list`. The fix stays inside the locked design ("configurable FREE_METHODS set"): extend the allowlist with client-bootstrap plumbing (`logging/setLevel`, `ping`, `resources/list`, `resources/templates/list`, `prompts/list`). With the extended set, Inspector CLI works end-to-end through the gate in mock mode — including a paid `tools/call` via its `--header "PAYMENT-SIGNATURE: demo"` flag (verified live). Unknown methods still default to PAID (allowlist semantics preserved; `tools/call` is the only revenue method and is never free).

Wire facts verified live: uvicorn/h11 sends response header names with the exact byte casing we set, so `PAYMENT-REQUIRED:` appears uppercase on the wire matching the OKX doc convention verbatim; the header value is standard RFC 4648 base64 (with padding, no newlines) of the byte-identical canonical JSON also served as the body; `Decimal("0.01").scaleb(6)` → `"10000"` with property-tested rejections for every malformed price. Threat probes all held: notification-form `tools/call` (no id) 402s, JSON-RPC batches 402, duplicate-key smuggling is impossible (gate and server share `json.loads` last-key-wins semantics — proven in both directions), content-type tricks do nothing, a 64 KiB body cap turns oversized bodies into 413 before JSON parsing, and garbage bytes always produce 402, never 500.

**Primary recommendation:** transcribe the PoC module below into `server/payments.py` (one module, zero pyproject/Dockerfile changes), register it with `app.add_middleware(X402Middleware)` immediately after the existing `McpPathRewrite` line in `create_app()`, use the EXTENDED free-methods allowlist, and add the proof matrix below as the phase's test suite.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Wire format (locked — from OKX A2MCP docs + verified x402 v2 ecosystem facts)**
- 402 response carries BOTH: (a) the `PAYMENT-REQUIRED` header whose value is base64-encoded JSON of the payment requirements (x402 v2, Dec 2025 revision), and (b) the same JSON as the response body (human-debuggable; matches OKX A2MCP doc example)
- Payment requirements JSON shape (locked from the OKX doc example):
  `{"x402Version": 2, "resource": {"url": "<endpoint url>", "description": "<service description>", "mimeType": "application/json"}, "accepts": [{"scheme": "exact", "network": "eip155:196", "asset": "0x779ded0c9e1022225f8e0630b35a9b54be713736", "amount": "10000", "payTo": "<TRUSTLENS_PAY_TO>", "maxTimeoutSeconds": 300}]}`
- `amount` is an atomic-unit STRING: USDT on X Layer has 6 decimals → 0.01 USDT = `"10000"`; derive from `TRUSTLENS_PRICE_USDT` (e.g. "0.01") deterministically — never float math (use Decimal), never hardcode the amount
- Payment proof arrives on retry in the `PAYMENT-SIGNATURE` header; after verification the response includes a `PAYMENT-RESPONSE` header (settlement receipt echo — mock value in mock mode)
- The OKX pre-registration compliance check MUST pass by construction: bare `curl -i -X POST https://host/mcp` (no body, no session) → HTTP 402 + `PAYMENT-REQUIRED` header

**Gating policy (locked — from architecture research + Phase 3 composition)**
- Pure-ASGI middleware (NOT BaseHTTPMiddleware) wrapping the app at the position marked by the Phase-3 LIFO comment in `server/app.py`
- PAID: MCP `tools/call` requests (the product)
- FREE: `/healthz`, `/` (leaderboard), `/badge/*`, and MCP protocol plumbing — `initialize`, `notifications/*`, `tools/list` — via a configurable `FREE_METHODS` set (one-line flip to gate everything, per the observed live OKX ASP that gates all methods)
- Bodyless or unparseable POSTs to /mcp → 402 with requirements (this is what makes the OKX curl check pass; never 500 on garbage)
- The gate inspects the JSON-RPC method WITHOUT consuming the body destructively (buffer & replay in pure ASGI — the reason BaseHTTPMiddleware is banned)

**Verifier seam (locked)**
- `PaymentVerifier` Protocol with two methods (verify + settle semantics per architecture research); implementations:
  - `MockVerifier` — active ONLY when `X402_MOCK == "1"` (exact string compare, fail-closed parse); accepts a documented mock token format in `PAYMENT-SIGNATURE` (e.g. any non-empty value or a fixed test token — planner picks, must be deterministic and documented), returns a mock `PAYMENT-RESPONSE`
  - Production default when `X402_MOCK` unset/≠"1": fail-closed `UnconfiguredVerifier` that 402s every paid request with the requirements (service is safe-by-default without creds) — the README (Phase 5) documents swapping in `okxweb3-app-x402`'s facilitator/x402ResourceServer at exactly this seam
- Startup log line states the active verifier mode loudly; mock mode must be impossible to enable by accident (exact "1" only)

**Config (locked — PAYX-03 verbatim + brief)**
- Environment variables ONLY: `TRUSTLENS_PAY_TO` (0x wallet, placeholder default "0x0000000000000000000000000000000000000000" with a startup warning when unset), `TRUSTLENS_PRICE_USDT` (default "0.01"), `X_LAYER_RPC` (default "https://rpc.xlayer.tech", used by the real SDK at deploy time — carried in config now), `X402_MOCK` (default unset)
- NEVER hardcode keys/addresses in code; `.env` stays gitignored; `.env.example` created THIS phase documenting every var with placeholder values and comments (fulfills the PAYX-03 acceptance surface; README section lands Phase 5)
- Config read once at app creation (env → dataclass), injectable for tests

**Tests (locked — PAYX-01/02 acceptance verbatim)**
- Without payment → 402: assert status, PAYMENT-REQUIRED header present and base64-decodes to the exact requirements JSON (eip155:196, "10000", scheme exact), body JSON matches, applies to tools/call
- With X402_MOCK=1 + mock PAYMENT-SIGNATURE → tools/call returns the full scored result + PAYMENT-RESPONSE header
- FREE set proven: healthz, /, badge, initialize, tools/list all pass unpaid in mock AND unconfigured modes
- Bare `curl`-equivalent test: bodyless POST /mcp → 402 + header (the OKX pre-registration check, in-process)
- Determinism: requirements JSON byte-stable (sorted keys where applicable, fixed serialization)
- Full suite green (230 existing); scoring coverage gate unaffected
- e2e "one paid call" test through the HTTP app with x402 mocked — this satisfies the brief's OPS-03 e2e clause early (formal OPS-03 sign-off remains Phase 5)

**Git & conduct (locked)**
- Commits authored by the user's git identity only; NEVER any AI attribution; conventional commits `feat(04-XX): ...`
- No new runtime deps (stdlib base64/json/hmac suffice); 2-attempt stop rule
- After execution this phase gets a security audit (gsd-secure-phase) — write threat models accordingly

### Claude's Discretion
- Module layout (`server/payments.py` vs package), exact FREE_METHODS constant shape
- Mock token format details (documented + deterministic)
- Requirements `resource.url` derivation (TRUSTLENS_BASE_URL + /mcp)
- PAYMENT-RESPONSE mock receipt shape

### Deferred Ideas (OUT OF SCOPE)
- PAYX-04 real settlement via `okxweb3-app-x402` (OKX API creds = human stop condition) — the verifier seam + README docs are the v1 deliverable
- README/deploy/registration docs — Phase 5 (OPS-02)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PAYX-01 | Call without payment returns HTTP 402 with x402 v2 payment-requirements JSON (scheme `exact`, network `eip155:196`, `payTo`, atomic `amount`) and the `PAYMENT-REQUIRED` header | Verified live: bare curl → `HTTP/1.1 402 Payment Required` + uppercase `PAYMENT-REQUIRED` header that b64-decodes to the exact locked JSON; body byte-identical to canonical bytes; both `/mcp` and `/mcp/`; golden bytes + b64 in §Requirements JSON |
| PAYX-02 | With `X402_MOCK=1`, a mock-paid call returns the scored result; verification is a pluggable interface so `okxweb3-app-x402` can drop in at deploy time | Verified: mock-paid `tools/call` on the same session → real card (3345/A/94) + `PAYMENT-RESPONSE` receipt; `PaymentVerifier` Protocol + Mock/Unconfigured implementations proven; deploy-time adapter sketch matches PyPI `x402` 2.15.0 / `okxweb3-app-x402` 0.1.1 API names (§Verifier Seam) |
| PAYX-03 | Payment config via env vars only (`TRUSTLENS_PAY_TO`, `TRUSTLENS_PRICE_USDT`, `X_LAYER_RPC`, `X402_MOCK`); no hardcoded keys/addresses; `.env` gitignored; `.env.example` documents every var | `PaymentConfig.from_env()` dataclass proven (read-once, injectable, placeholder warning fires at startup, X402_MOCK exact-"1" fail-closed across 9 property cases); exact `.env.example` content in §Config |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- No new runtime deps: the entire payment layer is stdlib (`base64`, `json`, `decimal`, `dataclasses`, `typing`) — zero `pip install` this phase.
- Secrets via env only; `.env` gitignored; `.env.example` created this phase; never hardcode keys/addresses (the USDT asset contract address and network id are public chain constants from the locked OKX doc shape, not secrets — they live in code as defaults per the locked requirements JSON; `payTo` is env-only).
- Scope discipline: no auth/accounts — x402 IS the access control.
- Stop conditions: real wallets/OKX creds are human-gated (why `UnconfiguredVerifier` is the production default); any error unresolved after 2 attempts → human review.
- Git: user identity only, no AI attribution, conventional commits `feat(04-XX): ...`.
- GSD workflow: file changes go through `/gsd-execute-phase`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Payment gating (402 challenge, method classification) | API/Backend — pure ASGI middleware (`server/payments.py`) | — | Must run BEFORE the MCP app so bodyless POSTs get 402 not 400/406; sees HTTP scope + JSON-RPC method names only |
| Payment verification/settlement | API/Backend — `PaymentVerifier` seam | External (OKX facilitator at deploy) | Mock in v1; real SDK swap happens at exactly this Protocol boundary |
| Requirements JSON + amount conversion | API/Backend — pure functions in the same module | — | Deterministic, byte-stable, unit-testable without HTTP |
| Payment config | API/Backend — env → frozen dataclass at app creation | Ops (`.env.example`) | Read once, injectable for tests |
| Free-route serving (/healthz, /, /badge/*) | API/Backend — existing Phase 3 routes | — | Gate never touches non-POST-/mcp traffic (proven) |
| MCP protocol/session handling | fastmcp/mcp SDK (unchanged) | — | Gate replays buffered bodies; session headers pass through untouched (proven) |
| Real on-chain settlement | DEFERRED (PAYX-04, v2) | X Layer via OKX facilitator | Human stop condition |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | everything | ✓ | 3.14.2 (repo editable-installed) | — |
| fastmcp / mcp / starlette / fastapi / uvicorn | host app | ✓ | 3.4.4 / 1.28.1 / 1.3.1 / 0.139.0 / 0.51.0 | — |
| stdlib base64/json/decimal/dataclasses | payment layer | ✓ | stdlib | — (no new deps) |
| `data/trustlens.db` | paid-call proofs | ✓ warm | 272 agents; 3345 → 94/A | rebuild: `python -m indexer.refresh` |
| node / npx / Inspector | mock e2e demo | ✓ | v24.15.0 / 11.12.1 / 0.22.0 | raw curl flow (verified, §Wire Proofs) |
| `okxweb3-app-x402` | PAYX-04 only (v2) | not installed (deliberate) | 0.1.1 on PyPI [VERIFIED: pypi.org 2026-07-11] | UnconfiguredVerifier fail-closed default |
| web3.okx.com (OKX docs) | doc re-verification | ✗ DNS unreachable from this env | — | PROJECT.md capture (fetched 2026-07-10) is the OKX authority |

**Missing dependencies with no fallback:** none.

## Standard Stack

### Core (no installation needed — all stdlib or already pinned)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| stdlib `base64` | 3.14 stdlib | RFC 4648 standard base64 for header values | x402 v2 HTTP transport uses standard base64 with padding [CITED: github.com/coinbase/x402 specs/transports-v2/http.md] |
| stdlib `json` | 3.14 stdlib | canonical serialization + JSON-RPC method sniffing | Same parser family as the MCP server → no gate/server parse divergence (proven, §Threats T3) |
| stdlib `decimal.Decimal` | 3.14 stdlib | price → atomic units | Exact arithmetic; float math is the documented ecosystem pitfall |
| stdlib `dataclasses` | 3.14 stdlib | frozen `PaymentConfig` | Read-once env, injectable |
| starlette (transitive) | 1.3.1 [VERIFIED: pip list] | ASGI contract the middleware implements | Already installed; gate is plain ASGI, imports nothing from starlette |

**Installation:** none. `hmac` (mentioned in CONTEXT) turned out unnecessary — the mock accepts a documented token without cryptography, and real crypto belongs to the deploy-time SDK.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `server/payments.py` (one module) | `payments/` package (protocol/verifier/middleware split per ARCHITECTURE.md) | Package requires adding `"payments"` to `[tool.setuptools] packages` AND a new `COPY payments/ payments/` line in the committed Dockerfile; `server/payments.py` rides the existing `server/` packaging and Docker COPY for free. ~330 cohesive lines fit one module. **Recommend `server/payments.py`** |
| 413 for oversized bodies | 402 for oversized bodies | 413 is honest and standard; 402 would keep a single "gate only ever 402s or passes" invariant. Either satisfies "never 500 on garbage" (OKX check sends no body — unaffected). PoC proves 413; one-line change if planner prefers 402 |
| Mock token = any non-empty value | Fixed literal token (e.g. `x402-mock`) | Any-non-empty is demo-friendliest (`-H "PAYMENT-SIGNATURE: demo"` just works, Inspector `--header` too) and cannot leak into production because the verifier — not the token — is mode-gated (fail-closed proven). Fixed token adds a failure mode to the demo with zero security gain in a mode that is by definition unverified. **Recommend any-non-empty, documented** |
| Config-derived `resource.url` | Request-Host-derived URL | Host-derived breaks byte-stability AND opens Host-header poisoning of the advertised payment endpoint (§Security). Config-derived proven |

## The Gate — Verified Composition and Ordering

### Middleware order vs `McpPathRewrite` (PROVEN)

`app.add_middleware` is LIFO — the LAST-added middleware is OUTERMOST. `create_app()` already ends with `app.add_middleware(McpPathRewrite)`. Phase 4 adds the gate **after** that line, exactly as the existing comment in `server/app.py` says:

```python
    app.add_middleware(McpPathRewrite)
    app.add_middleware(X402Middleware)      # Phase 4: LIFO -> gate runs FIRST,
    return app                              # sees RAW paths /mcp AND /mcp/
```

| Ordering | POST /mcp (bodyless) | POST /mcp/ (bodyless) | Verdict |
|----------|---------------------|----------------------|---------|
| **Order A: gate outermost** (`add_middleware(X402Middleware)` after the rewrite line) + `startswith` match | **402** | **402** | **RECOMMENDED — proven in both external-wrap and `add_middleware` forms** |
| Order B: rewrite outermost (gate sees only normalized `/mcp/`) | 402 | 402 | Also works — the rewrite normalizes before the gate; acceptable fallback |
| NEGATIVE: gate matching exact `"/mcp/"` only, Order A | **400 (NOT 402 — OKX check FAILS)** | 402 | The ungated bare `/mcp` slips past the gate, gets rewritten, and the MCP app answers 400 Parse error. **This is why the match MUST be `path == "/mcp" or path.startswith("/mcp/")`** |

The path predicate `path == "/mcp" or path.startswith("/mcp/")` is deliberately tighter than a bare `startswith("/mcp")` — it cannot accidentally gate a hypothetical `/mcpfoo` route.

### Session/JSON-RPC interplay (the phase's core risk — PROVEN safe)

Verified sequence against the real app (TestClient AND live uvicorn, `json_response=True` mode):

```
initialize (no payment)              -> 200 + mcp-session-id header intact through the gate
notifications/initialized            -> 202
tools/list (no payment)              -> 200, 4 tools with schemas
tools/call (no payment, session S)   -> 402 + PAYMENT-REQUIRED   [gate answers; MCP app never sees it]
tools/call (PAYMENT-SIGNATURE, S)    -> 200 + PAYMENT-RESPONSE   [SAME session S still valid]
```

Key mechanics proven:
- The 402 is emitted by the gate without touching the MCP app, so the stateful session is never invalidated by an unpaid attempt — the retry-with-payment flow works on one session.
- Response headers from the MCP app (`mcp-session-id`, content-type) pass through the gate unmodified on free calls; on paid calls the gate appends `PAYMENT-RESPONSE` by rewriting only the `http.response.start` message.
- `json_response=True` means every response the gate passes through is plain `application/json` — no SSE frames anywhere in the paid flow.
- GET /mcp (SSE notification channel) and DELETE /mcp (session close) pass the gate untouched (only POST is gated) — Inspector's post-connect GET works (sniffed live).
- CJK arguments (`"这个能吃吗？"`) flow through buffer-and-replay byte-perfectly (paid call resolves to 3345).

## FREE_METHODS — the critical empirical correction

**Finding [VERIFIED: live request sniffing]:** Inspector 0.22.0's connect sequence is:

```
POST initialize (protocolVersion 2025-11-25)   -> 200
POST notifications/initialized                  -> 202
POST logging/setLevel {"level":"debug"}         -> 402 with the locked FREE set  ← CONNECTION ABORTS HERE
GET  /mcp (SSE channel)                         -> (never reached in CLI failure path)
```

FastMCP advertises the `logging` capability in InitializeResult, so SDK-based clients set a log level as part of bootstrap. With CONTEXT's literal example set (`initialize`, `notifications/*`, `tools/list`), **Inspector cannot even connect** — `--method tools/list` fails with "Failed to connect to MCP server ... Error POSTing to endpoint: {requirements JSON}". This would silently regress MCPS-05 and kill the Phase 5 demo.

**Resolution (stays within the locked "configurable FREE_METHODS set" design):**

```python
FREE_METHODS = frozenset({
    "initialize", "ping", "tools/list",
    # client bootstrap plumbing — Inspector 0.22.0 sends logging/setLevel on
    # connect (proven by sniffer); discovery lists are free so marketplace/
    # Inspector introspection works. tools/call is NEVER here.
    "logging/setLevel", "resources/list", "resources/templates/list",
    "prompts/list",
})
FREE_METHOD_PREFIXES = ("notifications/",)
```

Semantics preserved: this is still an **allowlist** — unknown/future methods default to PAID (proven: `tools/execute_all` → 402), and the one-line flip to gate-everything remains (`FREE_METHODS = frozenset()`). With this set, Inspector CLI `tools/list` (unpaid) and `tools/call` (paid via `--header`) both work end-to-end through the gate (verified live). `resources/list`/`prompts/list` were added defensively for Inspector UI mode and other SDK clients that enumerate all capabilities on connect; they cost nothing (FastMCP returns empty lists) and leak no paid data.

## Wire Proofs (live uvicorn transcripts)

### The OKX pre-registration check — exact output

```
$ curl -s -i -X POST http://127.0.0.1:8402/mcp
HTTP/1.1 402 Payment Required
date: Sat, 11 Jul 2026 13:21:32 GMT
server: uvicorn
content-type: application/json
content-length: 389
PAYMENT-REQUIRED: eyJhY2NlcHRzIjpb...(base64 of the exact body bytes)...

{"accepts":[{"amount":"10000","asset":"0x779ded0c9e1022225f8e0630b35a9b54be713736","maxTimeoutSeconds":300,"network":"eip155:196","payTo":"0x1111111111111111111111111111111111111111","scheme":"exact"}],"resource":{"description":"TrustLens: evidence-based trust scores for OKX.AI marketplace agents over MCP","mimeType":"application/json","url":"http://localhost:8000/mcp"},"x402Version":2}
```

`POST /mcp/` (trailing slash) returns byte-identical 402 + header. The same check passed in-process via TestClient with zero request headers.

### Header casing on the wire [VERIFIED live]

uvicorn/h11 emits response header names **with the exact byte casing the ASGI app sets** — setting `b"PAYMENT-REQUIRED"` produces literal `PAYMENT-REQUIRED:` in the HTTP/1.1 response, matching the OKX doc convention character-for-character. Set the constants as uppercase bytes:

```python
HDR_PAYMENT_REQUIRED = b"PAYMENT-REQUIRED"
HDR_PAYMENT_RESPONSE = b"PAYMENT-RESPONSE"
HDR_PAYMENT_SIGNATURE = b"payment-signature"   # REQUEST header lookup: ASGI
# delivers request header names lowercased, so the gate matches lowercase.
```

Caveat for deploy (documented, not actionable now): if the production host terminates TLS with HTTP/2, header names are lowercased on the wire by protocol rule (RFC 9113); header-name matching is case-insensitive per RFC 9110 §5.1, so any conformant checker accepts either. HTTP/1.1 origins preserve our uppercase.

### Full paid flow over live HTTP (curl + httpx, transcripted)

```
initialize                          -> 200, mcp-session-id: 99ab96cd5e264dc6bf55b4d2878f779e
notifications/initialized           -> 202
tools/call unpaid  (same session)   -> HTTP/1.1 402 Payment Required + PAYMENT-REQUIRED
tools/call + "PAYMENT-SIGNATURE: demo" (same session)
                                    -> HTTP/1.1 200 OK
                                       mcp-session-id: 99ab96cd5e264dc6bf55b4d2878f779e
                                       PAYMENT-RESPONSE: eyJtb2NrIjp0cnVlLC...
   body.result.structuredContent: {"agent_id":"3345","grade":"A","score":94,...}
   PAYMENT-RESPONSE decodes to:
   {"mock":true,"network":"eip155:196","payer":"0x0000...0000","success":true,"transaction":"0x0000...0000"}
```

## Requirements JSON — canonical serialization (byte-stable)

**Decision:** one canonical serializer produces the bytes used for BOTH the 402 body and (base64'd) the header value — the header always decodes to exactly the body:

```python
def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")

def encode_header(payload: bytes) -> bytes:
    return base64.b64encode(payload)   # RFC 4648 standard alphabet, WITH padding
```

- `sort_keys=True` + compact separators = byte-stable across runs/versions (locked determinism requirement). Key order is semantically irrelevant to any JSON consumer; the x402 v2 spec transmits protocol data via the header, and the body is "a server implementation concern" [CITED: coinbase/x402 transports-v2/http.md].
- Standard base64 with padding is what the x402 v2 HTTP transport uses [CITED: same]. `b64encode` emits no newlines (proven).
- `ensure_ascii=True` keeps both body and header value pure ASCII (header values must be latin-1-safe).

**Golden values with default config** (placeholder payTo, price "0.01", base_url `http://localhost:8000`) — transcribe into a golden-file test:

```
body bytes (389 chars w/ real payTo; sorted keys):
{"accepts":[{"amount":"10000","asset":"0x779ded0c9e1022225f8e0630b35a9b54be713736","maxTimeoutSeconds":300,"network":"eip155:196","payTo":"0x0000000000000000000000000000000000000000","scheme":"exact"}],"resource":{"description":"TrustLens: evidence-based trust scores for OKX.AI marketplace agents over MCP","mimeType":"application/json","url":"http://localhost:8000/mcp"},"x402Version":2}
```

(Header b64 of those bytes begins `eyJhY2NlcHRzIjpb...` and round-trips to identical bytes — proven; regenerate the golden in-test via `encode_header(canonical_json(build_requirements(cfg)))` rather than hardcoding, since `resource.description` wording is Claude's discretion.)

`resource.url` derivation (discretion resolved): `cfg.base_url.rstrip("/") + "/mcp"` from `TRUSTLENS_BASE_URL` — NEVER from the request Host header (byte-stability + Host-poisoning immunity, §Security). At deploy, setting `TRUSTLENS_BASE_URL=https://domain` makes the 402 advertise the real endpoint.

## Decimal → Atomic Conversion (exact code + property table)

```python
def usdt_to_atomic(price: str, decimals: int = 6) -> str:
    """"0.01" -> "10000" (USDT on X Layer: 6 decimals). Never float."""
    if not isinstance(price, str):
        raise TypeError(f"price must be a string, got {type(price).__name__}")
    try:
        d = Decimal(price)
    except InvalidOperation as exc:
        raise ValueError(f"invalid price: {price!r}") from exc
    if not d.is_finite():
        raise ValueError(f"price must be finite: {price!r}")
    if d <= 0:
        raise ValueError(f"price must be positive: {price!r}")
    atomic = d.scaleb(decimals)          # exponent shift — exact, no rounding
    if atomic != atomic.to_integral_value():
        raise ValueError(f"price {price!r} has more precision than {decimals} decimals")
    return str(int(atomic))
```

All cases executed (69-assertion suite):

| Input | Result |
|-------|--------|
| `"0.01"` | `"10000"` |
| `"0.001"` | `"1000"` |
| `"1"` | `"1000000"` |
| `"0.000001"` | `"1"` |
| `"2.5"` | `"2500000"` |
| `"0.010000"` | `"10000"` (trailing zeros normalize) |
| `"1e2"` | `"100000000"` (Decimal accepts scientific notation — exact, accepted) |
| `"0.0000001"` | ValueError (sub-atomic precision) |
| `"-0.01"`, `"0"` | ValueError (non-positive) |
| `"NaN"`, `"Infinity"`, `"-Infinity"` | ValueError (Decimal parses these WITHOUT error — the `is_finite()` check is mandatory) |
| `"abc"`, `""` | ValueError (InvalidOperation) |

## Config (PAYX-03) — dataclass + `.env.example`

```python
@dataclass(frozen=True)
class PaymentConfig:
    pay_to: str = "0x0000000000000000000000000000000000000000"
    price_usdt: str = "0.01"
    x_layer_rpc: str = "https://rpc.xlayer.tech"
    mock: bool = False
    base_url: str = "http://localhost:8000"
    network: str = "eip155:196"
    asset: str = "0x779ded0c9e1022225f8e0630b35a9b54be713736"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "PaymentConfig":
        env = os.environ if env is None else env
        cfg = cls(
            pay_to=env.get("TRUSTLENS_PAY_TO", PLACEHOLDER_PAY_TO),
            price_usdt=env.get("TRUSTLENS_PRICE_USDT", "0.01"),
            x_layer_rpc=env.get("X_LAYER_RPC", "https://rpc.xlayer.tech"),
            mock=env.get("X402_MOCK") == "1",   # fail-closed: EXACT "1" only
            base_url=env.get("TRUSTLENS_BASE_URL", "http://localhost:8000"),
        )
        if cfg.pay_to == PLACEHOLDER_PAY_TO:
            log.warning("TRUSTLENS_PAY_TO is unset - using the placeholder "
                        "address; real payments CANNOT settle until it is configured")
        return cfg
```

Proven behavior:
- **Exact-"1" fail-closed** (9 property cases executed): `"1"`→mock; `"0"`, `"true"`, `"TRUE"`, `"yes"`, `" 1"`, `"1 "`, `""`, unset → NOT mock.
- **Injectable:** every TestClient proof passed `PaymentConfig(mock=True)` directly — no env mutation in tests.
- **Startup banners fire at boot** (live uvicorn log, before first request): `TRUSTLENS_PAY_TO is unset - using the placeholder address...` and `X402_MOCK=1 - payments are NOT verified (mock mode)` (from `make_verifier`, which is the single mode-selection point).

`.env.example` (created this phase; every var, placeholders, comments):

```bash
# TrustLens payment configuration (x402 v2 on X Layer) — copy to .env and fill in.
# .env is gitignored and dockerignored; never commit real values.

# Wallet that receives 0.01 USDT per tools/call. REQUIRED for real payments.
# Placeholder default keeps the server bootable but unsettleable (startup warning).
TRUSTLENS_PAY_TO=0x0000000000000000000000000000000000000000

# Price per paid MCP call, in human USDT units (string; converted to atomic
# 6-decimal units internally with Decimal — "0.01" -> "10000").
TRUSTLENS_PRICE_USDT=0.01

# X Layer RPC endpoint. Unused by the mock verifier; carried for the
# deploy-time okxweb3-app-x402 facilitator swap (PAYX-04).
X_LAYER_RPC=https://rpc.xlayer.tech

# Mock payment mode. EXACTLY "1" enables MockVerifier (any non-empty
# PAYMENT-SIGNATURE accepted, mock PAYMENT-RESPONSE receipt). Any other
# value (or unset) = fail closed: every paid request answers 402.
# NEVER set to 1 in production.
X402_MOCK=

# Public base URL advertised in payment requirements (resource.url = BASE/mcp)
# and in methodology links. Set to the HTTPS domain at deploy.
TRUSTLENS_BASE_URL=http://localhost:8000
```

(`TRUSTLENS_BASE_URL` predates this phase — server/tools.py already reads it; documenting it here completes the file.)

## Verifier Seam (PAYX-02) — mock now, OKX facilitator later

```python
class PaymentVerifier(Protocol):
    async def verify(self, payment_b64: str, requirements: dict) -> bool: ...
    async def settle(self, payment_b64: str, requirements: dict) -> dict: ...

class MockVerifier:
    """Active ONLY under X402_MOCK == "1".
    Documented mock token: ANY non-empty PAYMENT-SIGNATURE value
    (demo: -H "PAYMENT-SIGNATURE: demo"). Deterministic receipt below.
    Replay is NOT detected in mock mode — accepted, documented limitation."""
    async def verify(self, payment_b64, requirements): return bool(payment_b64.strip())
    async def settle(self, payment_b64, requirements):
        return {"success": True, "transaction": "0x" + "0" * 64,
                "network": self.cfg.network, "payer": "0x" + "0" * 40, "mock": True}

class UnconfiguredVerifier:
    """Production default without creds: verify() is always False -> every
    paid request 402s with the requirements. settle() raises (unreachable)."""
```

The mock receipt follows the x402 v2 settlement-response shape `{success, transaction, network, payer}` [CITED: coinbase/x402 transports-v2/http.md] plus an explicit `"mock": true` marker; it is base64'd with the same `canonical_json` and emitted as `PAYMENT-RESPONSE` (decoded transcript in §Wire Proofs).

**What the REAL `PAYMENT-SIGNATURE` contains** (so the seam's types survive the swap) [CITED: coinbase/x402 transports-v2/http.md]: base64 JSON `{"x402Version": 2, "resource": {...}, "accepted": {...}, "payload": {"signature": "0x...", "authorization": {"from", "to", "value", "validAfter", "validBefore", "nonce"}}}`. The Protocol deliberately takes the RAW header string — decoding to SDK types is the adapter's job.

**Deploy-time adapter sketch** (README content for Phase 5; NOT implemented in v1):

```python
# pip install okxweb3-app-x402   (0.1.1 on PyPI, authored by Coinbase,
# repo github.com/coinbase/x402 — OKX's packaging of the x402 Python SDK,
# extras: fastapi, mcp) [VERIFIED: pypi.org, 2026-07-11]
# The underlying x402 SDK (PyPI `x402` 2.15.0) exposes x402ResourceServer /
# HTTPFacilitatorClient with async verify(payload, requirements) and
# settle(payload, requirements) [VERIFIED: pypi.org project page].
class OkxFacilitatorVerifier:                      # drops into the same seam
    def __init__(self, facilitator):               # needs OKX_API_KEY/SECRET/
        self.facilitator = facilitator              # PASSPHRASE — HUMAN STOP CONDITION
    async def verify(self, payment_b64, requirements):
        payload = decode_payment_payload(payment_b64)      # SDK type from b64 JSON
        return (await self.facilitator.verify(payload, requirements)).is_valid
    async def settle(self, payment_b64, requirements):
        payload = decode_payment_payload(payment_b64)
        return (await self.facilitator.settle(payload, requirements)).to_dict()
```

Exact SDK method/attribute names are MEDIUM confidence (PyPI page verified the classes and the `verify`/`settle` call pattern; the package was not installed — unlisted dep). Alternatively OKX documents replacing the whole middleware with `x402ResourceServer(facilitator)` at the same app layer — either way the seam position is correct.

## Code Examples — the gate (verbatim transcription source)

Full working module: scratchpad `x402_poc.py` (69/69 proofs). The load-bearing parts:

### Body buffer with cap + replay (pure ASGI — BaseHTTPMiddleware banned)

```python
# inside __call__, after the _gated(scope) path/method check:
chunks: list[bytes] = []
size = 0
while True:
    message = await receive()
    if message["type"] == "http.disconnect":
        return                                # client gone; answer nothing
    chunk = message.get("body", b"")
    size += len(chunk)
    if size > MAX_BODY_BYTES:                 # 64 KiB — tool calls are <1 KiB
        return await self._send_json(send, 413,
            {"error": "payload_too_large", "max_bytes": MAX_BODY_BYTES})
    if chunk:
        chunks.append(chunk)
    if not message.get("more_body", False):
        break
body = b"".join(chunks)

def _replay(body: bytes):                     # downstream receive()
    sent = False
    async def receive() -> dict:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}
    return receive
```

### Method classification (fail-closed on anything non-standard)

```python
def jsonrpc_method(body: bytes) -> str | None:
    """None => unparseable => 402. Covers: empty body, invalid JSON/UTF-8,
    non-object payloads (batch arrays — removed in MCP 2025-06-18),
    missing/non-string method. json.loads last-key-wins matches the MCP
    server's parser, so gate classification never diverges from execution."""
    if not body:
        return None
    try:
        msg = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(msg, dict):
        return None
    method = msg.get("method")
    return method if isinstance(method, str) else None
```

### Decision core + receipt header injection

```python
method = jsonrpc_method(body)
if method is not None and is_free(method):
    return await self.app(scope, _replay(body), send)

signature = _get_header(scope, HDR_PAYMENT_SIGNATURE)      # lowercase lookup
if signature is None or not await self.verifier.verify(signature, self.requirements):
    return await self._send_402(send)                      # precomputed body+b64

receipt = await self.verifier.settle(signature, self.requirements)  # settle BEFORE serving
receipt_b64 = encode_header(canonical_json(receipt))

async def send_with_receipt(message: dict) -> None:
    if message["type"] == "http.response.start":
        headers = list(message.get("headers", []))
        headers.append((HDR_PAYMENT_RESPONSE, receipt_b64))
        message = {**message, "headers": headers}
    await send(message)

return await self.app(scope, _replay(body), send_with_receipt)
```

### 402 response (requirements precomputed once in `__init__`)

```python
async def _send_402(self, send) -> None:
    await send({"type": "http.response.start", "status": 402, "headers": [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(self._req_body)).encode("ascii")),
        (HDR_PAYMENT_REQUIRED, self._req_b64),
    ]})
    await send({"type": "http.response.body", "body": self._req_body})
```

### Registration (the exact Phase-4 edit to `server/app.py`)

```python
    app.add_middleware(McpPathRewrite)        # existing line
    app.add_middleware(X402Middleware)        # NEW — LIFO: gate outermost
```

`X402Middleware.__init__(self, app, config=None, verifier=None)` — Starlette passes kwargs through `add_middleware`, so tests can register `add_middleware(X402Middleware, config=cfg, verifier=MockVerifier(cfg))`; production omits kwargs → `PaymentConfig.from_env()` + `make_verifier` (banners fire at middleware-stack build, i.e. startup — proven in live log). Recommend a `create_app(payment_config: PaymentConfig | None = None)` parameter for test injection, mirroring the existing `db_path`/`static_dir` pattern.

## MCP Inspector — mock-mode e2e commands (verified live)

```bash
# server (mock mode)
X402_MOCK=1 uvicorn server.main:app --port 8000

# FREE discovery through the gate (no payment header) — lists all 4 tools
npx --yes @modelcontextprotocol/inspector --cli http://127.0.0.1:8000/mcp --method tools/list

# PAID call through the gate — Inspector sends the header on every request;
# free methods ignore it, tools/call consumes it
npx --yes @modelcontextprotocol/inspector --cli http://127.0.0.1:8000/mcp \
  --header "PAYMENT-SIGNATURE: demo" \
  --method tools/call --tool-name score_agent --tool-arg 'agent_id_or_name="3345"'
# -> structuredContent {"agent_id":"3345","grade":"A","score":94,...}

# UNPAID tools/call error surface (demo-friendly — shows the price quote):
# "Failed to call tool score_agent: ... Error POSTing to endpoint: {requirements JSON}"
```

Phase 3's Windows quirks still apply (assert on stdout not exit code — libuv teardown assertion; quote numeric strings; always `--cli`). The `--header "HeaderName: Value"` flag is documented in `--cli --help` [VERIFIED].

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Request-body middleware | `BaseHTTPMiddleware` + `request.body()` | Pure ASGI buffer-and-replay (above) | Known Starlette footgun: consumed streams hang/double-read; breaks streaming responses (locked ban) |
| Payment crypto in v1 | EIP-712 signature verification | `UnconfiguredVerifier` (fail-closed) + deploy-time SDK | Real verification needs the OKX facilitator (creds = stop condition); hand-rolled sig checks would be security theater |
| Decimal parsing | float math / string splitting | `decimal.Decimal` + `scaleb` | `"NaN"`/`"Infinity"` parse as valid Decimals — the property suite catches what ad-hoc code misses |
| Canonical JSON | manual key ordering | `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=True)` | Byte-stable by construction; one function feeds body AND header |
| JSON-RPC method sniffing | regex over the body | `json.loads` + isinstance checks | Regex parsers diverge from the server's parser → smuggling surface; json.loads is provably consistent (T3) |
| Trailing-slash gating | nginx rules / duplicate routes | `path == "/mcp" or path.startswith("/mcp/")` predicate | Proven: exact-match variants fail the OKX check (400 not 402) |

## Common Pitfalls (Phase-4-specific, all reproduced or disproven in the PoC)

### Pitfall 1: FREE_METHODS without `logging/setLevel` bricks Inspector
**What goes wrong:** Inspector 0.22.0 aborts at connect ("Failed to connect to MCP server") because its bootstrap `logging/setLevel` gets 402'd. tools/list never happens. MCPS-05 regresses silently; the demo dies.
**How to avoid:** the extended allowlist (§FREE_METHODS). **Warning sign:** Inspector fails against the gated server but raw curl handshake works.

### Pitfall 2: Exact-path matching fails the OKX check
**What goes wrong:** gate matches only `/mcp/` (the rewritten form) → bare `POST /mcp` slips through ungated → MCP app answers 400 Parse error → pre-registration check fails. Proven (negative test: 400 not 402).
**How to avoid:** `path == "/mcp" or path.startswith("/mcp/")`; register the gate AFTER the `McpPathRewrite` line (LIFO → outermost).

### Pitfall 3: Session death assumed after 402
**What goes wrong:** planners add re-initialize logic to the paid retry flow, complicating tests and the demo script.
**Reality (proven):** the gate answers 402 without touching the MCP app; the same `mcp-session-id` works on the paid retry. No re-handshake needed.

### Pitfall 4: Mock verifier selected by anything other than exact `"1"`
**What goes wrong:** `bool(os.getenv("X402_MOCK"))` makes `"0"`/`"false"` enable mock in prod (serves paid data free).
**How to avoid:** `env.get("X402_MOCK") == "1"` — 9 property cases proven; single selection point (`make_verifier`) logs the mode loudly at startup (live-log proven).

### Pitfall 5: Requirements built per-request from the Host header
**What goes wrong:** breaks byte-determinism AND lets an attacker with a spoofed Host poison the advertised payment endpoint.
**How to avoid:** requirements precomputed ONCE in `__init__` from config (`TRUSTLENS_BASE_URL`); the PoC's 402 latency is header-lookup + two sends.

### Pitfall 6: Coverage gate trips on payment-only test runs
**What goes wrong:** `pytest tests/test_payments.py` alone fails — pyproject's `--cov=scoring --cov-fail-under=90` measures 0% when scoring tests don't run.
**How to avoid:** full-suite runs are unaffected (scoring tests run too); partial runs need `--no-cov` (existing documented footgun in pyproject.toml).

### Pitfall 7: starlette 1.3.1 TestClient deprecation noise
**What goes wrong:** `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead` on every TestClient import.
**How to avoid:** ignore — cosmetic, pre-existing in Phase 3 tests; `httpx2` would be a NEW dep (forbidden without asking). Do not "fix" this.

### Pitfall 8: Testing only `/mcp` or only `/mcp/`
**What goes wrong:** the two paths take different code routes (raw vs rewritten); a regression in one is invisible if tests cover the other.
**How to avoid:** every gate test asserts BOTH paths (PoC pattern: byte-identical 402s).

## Threat Sketch (for the post-phase gsd-secure-phase audit)

Proven-by-execution matrix (all against the real wrapped app):

| # | Threat | STRIDE | Result | Disposition |
|---|--------|--------|--------|-------------|
| T1 | `tools/call` smuggled as a notification (no `id`) | Tampering/Revenue | **402** — gate keys on `method`, not id-presence | Mitigated (proven) |
| T2 | JSON-RPC batch `[initialize, tools/call]` | Tampering/Revenue | **402** — arrays are unparseable-by-policy (batches removed in MCP 2025-06-18 anyway) | Mitigated (proven) |
| T3 | Duplicate-key smuggling `{"method":"tools/call","method":"initialize"}` (and reverse) | Tampering | **No divergence possible** — gate and server both use Python `json.loads` (last key wins). Last=initialize → free-pass AND server executes initialize (200 InitializeResult, no tool run); last=tools/call → 402. Proven both directions | Mitigated (proven) |
| T4 | Content-Type tricks (`text/plain` etc.) | Tampering | **402** — gate classifies raw bytes, ignores Content-Type entirely | Mitigated (proven) |
| T5 | DoS via huge bodies | DoS | **413** at 64 KiB cap, before JSON parsing; buffering stops at the cap | Mitigated (proven) |
| T6 | Garbage bytes (`\x00\xff\xfe`, broken JSON, strings, arrays) | DoS/Availability | **402, never 500** — the OKX-check-by-construction rule doubles as crash immunity | Mitigated (proven) |
| T7 | Unknown/future methods ride free | Revenue | **402** — allowlist semantics; only enumerated plumbing is free | Mitigated (proven) |
| T8 | **Replay of PAYMENT-SIGNATURE in mock mode** | Spoofing/Revenue | Same token accepted repeatedly (proven) | **ACCEPTED LIMITATION** — mock mode is explicitly non-verifying, impossible to enable by accident (exact-"1", startup banner); real facilitator enforces authorization nonces + validBefore windows on-chain [CITED: x402 v2 payload shape] |
| T9 | Header injection via PAYMENT-SIGNATURE / receipt echo | Injection | No request data is ever echoed into response headers; `PAYMENT-RESPONSE` is 100% server-constructed constants + config; 402 headers are precomputed | Mitigated by construction |
| T10 | Host-header poisoning of advertised `resource.url` | Spoofing | `resource.url` derives from `TRUSTLENS_BASE_URL` config, never the request | Mitigated by construction |
| T11 | Paid-data exfiltration via ungated GET /mcp (SSE channel) | Info disclosure | GET passes the gate but only delivers server-initiated notifications for an existing session; tool results only flow on POST `tools/call` (gated) | No exposure (analyzed; GET/DELETE pass-through proven non-402) |
| T12 | Gate bypass via `/mcp%2F`-style path encoding | Tampering | uvicorn decodes percent-encoding before ASGI (`scope["path"]` is decoded); predicate matches decoded paths; non-matching paths fall to StaticFiles 404 — no MCP route exists outside `/mcp` | Analyzed; recommend one test in-phase |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| x402 v1: `X-PAYMENT` headers, JSON-body-only challenge, decimal amounts | v2: base64 `PAYMENT-REQUIRED`/`PAYMENT-SIGNATURE`/`PAYMENT-RESPONSE` headers, atomic-unit string amounts, `resource` object | Dec 2025 (x402 v2) | Any `X-PAYMENT` or decimal-amount code is wrong on sight |
| JSON-RPC batching in MCP | Single message per POST (batches removed) | MCP spec 2025-06-18 | Gate treats arrays as unparseable → 402 (also what the server does) |
| Inspector needed transport flags | 0.22.0: `--cli <url>` auto-detects; `--header` for auth-style headers | 2026 | Mock-paid demo works via CLI flags alone |
| Coinbase-only x402 Python SDK | `okxweb3-app-x402` 0.1.1 on PyPI (OKX packaging of coinbase/x402; extras `fastapi`, `mcp`) | 2026-07-09 | The deploy-time swap package is real and current [VERIFIED: pypi.org] |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | OKX's pre-registration checker matches header names case-insensitively (RFC 9110) and accepts uppercase-on-HTTP/1.1 / lowercase-on-HTTP/2 | Wire Proofs | Low — we emit the doc-verbatim uppercase on HTTP/1.1; only a non-conformant checker behind an HTTP/2-only edge would object [ASSUMED, RFC-backed] |
| A2 | OKX's marketplace runtime tolerates the free-handshake gating granularity (tools/call-only paid) | FREE_METHODS | Locked design already hedges this: one-line flip to gate everything; the observed live OKX ASP gates all methods and still passes the curl check |
| A3 | `okxweb3-app-x402`'s facilitator API matches the PyPI `x402` 2.15.0 verify/settle pattern shown on its project page | Verifier Seam | MEDIUM — adapter sketch might need renaming at deploy; the seam position (Protocol taking raw header + requirements) is insensitive to this [ASSUMED: package not installable per dep lock] |
| A4 | Inspector UI mode (browser) connects like the verified CLI mode given the extended allowlist covers resources/prompts lists | Inspector | Demo-day friction only; CLI evidence covers MCPS-05 continuity; UI rehearsal is Phase 5 |
| A5 | OKX doc capture in PROJECT.md (2026-07-10) remains current — web3.okx.com was DNS-unreachable from this environment for re-verification | Sources | Wire shape is triple-anchored (PROJECT.md + x402 v2 spec + live OKX ASP observation); a silent OKX doc change this week would surface at registration, which is a human-reviewed step anyway |

## Open Questions (RESOLVED)

1. **413 vs 402 for oversized bodies** — both satisfy "never 500"; PoC proves 413. Planner picks (one line). Recommendation: keep 413 (honest semantics; OKX check unaffected).
   - **RESOLVED: 413 kept (orchestrator lock, pinned by test_threat_oversized_body_413 in 04-02)**
2. **`create_app()` injection surface** — recommend `create_app(payment_config=None)` param (mirrors `db_path`); alternatively tests re-wrap via `add_middleware` (both forms proven). Planner picks.
   - **RESOLVED: `create_app(payment_config=None)` parameter (orchestrator lock, implemented in 04-01 Task 2)**
3. **Should `completion/complete` be free?** — not sent by Inspector CLI (sniffed); tools-only server never needs it. Leave PAID (default) unless the Phase 5 demo surfaces a client that sends it.
   - **RESOLVED: stays PAID / default-paid for unknown methods (orchestrator lock, pinned in 04-01 acceptance + 04-02 allowlist tests)**

## Security Domain

### Applicable ASVS Categories (L1)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | x402 payment IS the access control (brief forbids auth); no identities |
| V3 Session Management | partial | MCP session ids are mcp-SDK transport tokens; the gate never creates/validates sessions, only preserves them (proven) |
| V4 Access Control | **yes — this phase IS the access control** | Default-deny allowlist (unknown methods PAID, proven T7); fail-closed verifier when unconfigured (proven); no bypass via notifications/batch/dup-keys/content-type (proven T1–T4) |
| V5 Input Validation | yes | Body parse is fail-closed (`None` → 402, never 500 — proven T6); 64 KiB cap before parsing (T5); price config validated by `usdt_to_atomic` (rejects NaN/Infinity/negative/sub-atomic) |
| V6 Cryptography | no (v1) | Deliberately NO hand-rolled crypto; real signature verification delegated to the facilitator SDK at deploy (stop-condition-gated) |
| V12 API/Web Service | yes | 402/413 bodies are fixed server-constructed JSON; no request data echoed; no exception text in responses (gate has no unguarded parse paths) |
| V14 Config | yes | Env-only secrets, placeholder + loud warning, exact-"1" mock parse, `.env` git/docker-ignored, `.env.example` shipped this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Payment-gate bypass via request-smuggling variants | Tampering | Same-parser classification (json.loads both sides), allowlist default-paid — proven matrix in §Threat Sketch |
| Mock mode reachable in production | Spoofing | Exact-"1" parse + single `make_verifier` seam + startup banner + unconfigured-mode 402 test (all proven) |
| Buffer exhaustion at the gate | DoS | 64 KiB body cap ahead of parse (proven 413) |
| Advertised-endpoint poisoning | Spoofing | Config-derived `resource.url`, never Host-derived |
| Float drift in amounts | Tampering/Integrity | Decimal-only conversion, golden-byte requirements test |

## Sources

### Primary (HIGH confidence — executed on this machine, 2026-07-11)
- Scratchpad PoC (`x402_poc.py`, `x402_poc_tests.py`, `poc_server.py`, `poc_server_debug.py`): 69/69 assertions against the real `create_app()` + `data/trustlens.db`; live uvicorn curl transcripts (OKX check, full session flow, header casing); Inspector 0.22.0 CLI e2e incl. `--header` paid call; request sniffer capturing Inspector's connect sequence (`logging/setLevel` discovery); `add_middleware` registration form; startup banner log
- Installed environment: pip list (fastmcp 3.4.4, starlette 1.3.1, mcp 1.28.1, uvicorn 0.51.0), Python 3.14.2, Inspector `--cli --help` flag listing

### Secondary (HIGH-MEDIUM — official docs/registries, fetched 2026-07-11)
- https://github.com/coinbase/x402/blob/main/specs/transports-v2/http.md — header names (PAYMENT-REQUIRED/SIGNATURE/RESPONSE), standard base64 with padding, PAYMENT-SIGNATURE payload shape (authorization nonce/validBefore), settlement response shape, "response bodies are a server implementation concern" — HIGH
- https://pypi.org/project/okxweb3-app-x402/ — exists, 0.1.1 (2026-07-09), authored Coinbase, repo coinbase/x402, extras fastapi/mcp — HIGH for existence/metadata
- https://pypi.org/project/x402/ — 2.15.0 (2026-07-10); `x402ResourceServer`, `HTTPFacilitatorClient`, async `verify(payload, requirements)`/`settle(payload, requirements)` — MEDIUM (page-level, not installed)
- `.planning/PROJECT.md` (OKX docs captured 2026-07-10) — locked requirements JSON shape, eip155:196/1952, asset address, pre-registration curl, `okxweb3-app-x402` + creds — project's OKX authority (web3.okx.com DNS-unreachable from this env for re-fetch)
- `.planning/phases/03-mcp-server-leaderboard/03-RESEARCH.md` — wire sequence, json_response mode, Inspector Windows quirks (all reconfirmed live through the gate)

### Tertiary (LOW)
- WebSearch corroboration of OKX A2MCP x402 ecosystem (Glama Mario listing, Onchain OS overview snippets) — context only; no recommendation rests on these

## Metadata

**Confidence breakdown:**
- Gate composition/ordering/session interplay: HIGH — executed, TestClient + live uvicorn + add_middleware form
- FREE_METHODS correction: HIGH — root-caused by live sniffing, fix verified e2e
- Wire format (headers/base64/casing): HIGH locally (curl transcripts) — OKX checker's tolerance is A1 [ASSUMED, RFC-backed]
- Conversion/serialization/config: HIGH — property-tested
- Deploy-time SDK shapes: MEDIUM — PyPI-verified names, package not installed (dep lock)

**Research date:** 2026-07-11
**Valid until:** 2026-07-25 (pinned stack; recheck only if fastmcp/starlette pins or OKX registration docs change)
