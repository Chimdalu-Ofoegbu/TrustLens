"""x402 v2 payment layer: config, requirements JSON, verifier seam, ASGI gate.

PAYX-01/02/03. Transcribed verbatim from the Phase 4 research PoC (69/69
proof assertions against the real create_app() + data/trustlens.db — see
.planning/phases/04-x402-payment-layer/04-RESEARCH.md).

Wire format (locked by 04-CONTEXT): unpaid/unparseable POST /mcp* answers
402 with the payment-requirements JSON as the body AND base64-encoded in
the PAYMENT-REQUIRED header (header always decodes to exactly the body).
Payment proof arrives in PAYMENT-SIGNATURE; the settlement receipt is
echoed base64-encoded in PAYMENT-RESPONSE. No new runtime deps — stdlib
only (base64/json/decimal/dataclasses/typing).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Protocol

log = logging.getLogger("server.payments")

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

PLACEHOLDER_PAY_TO = "0x0000000000000000000000000000000000000000"
XLAYER_USDT = "0x779ded0c9e1022225f8e0630b35a9b54be713736"
USDT_DECIMALS = 6
MAX_BODY_BYTES = 64 * 1024  # tool-call bodies are <1 KiB; cap DoS buffering

# TRUSTLENS_PRICE_USDT grammar: plain decimal or scientific, no sign, no
# whitespace, no PEP-515 underscore grouping. Decimal() ALONE would silently
# accept " 0.01 ", "+0.01", and "1_000" (as one thousand) - operator typos that
# must fail loudly at startup, not misprice every call. Anchored fullmatch so a
# stray newline/space in a .env is rejected instead of stripped-and-accepted.
_PRICE_RE = re.compile(r"[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?")
# Sanity ceiling on the configured price (human USDT units). 0.01 is the spec
# price; anything above 1,000,000 USDT/call is a misconfiguration, not a
# business decision - reject rather than emit a ~7+ digit atomic amount.
MAX_PRICE_USDT = Decimal("1000000")

# x402 v2 HTTP transport header names (spec: coinbase/x402 transports-v2/http.md)
HDR_PAYMENT_REQUIRED = b"PAYMENT-REQUIRED"
HDR_PAYMENT_RESPONSE = b"PAYMENT-RESPONSE"
# ASGI request header names arrive lowercased (ASGI spec) - lookup key:
HDR_PAYMENT_SIGNATURE = b"payment-signature"

# FREE_METHODS is an allowlist of unpaid MCP methods. tools/call (the revenue
# method) is deliberately absent, and ANY method not listed here defaults to PAID
# (proven: tools/execute_all -> 402). Gating everything is still a one-line flip:
# FREE_METHODS = frozenset().
#
# DELIBERATE, ORCHESTRATOR-APPROVED WIDENING beyond the 04-CONTEXT lock:
# 04-CONTEXT (line 28) locks the FREE set to `initialize`, `notifications/*`, and
# `tools/list`. 04-RESEARCH (Pitfall 1) then PROVED that CONTEXT-only set bricks
# MCP Inspector: Inspector 0.22.0 sends `logging/setLevel` during connect (FastMCP
# advertises the `logging` capability), gets 402'd, and ABORTS before ever calling
# tools/list - so `--method tools/list` fails and the Phase 5 demo dies. The fix
# stays inside the locked "configurable FREE_METHODS set" design by extending the
# allowlist with client-bootstrap plumbing. Each group and its justification:
FREE_METHODS = frozenset({
    # (1) CONTEXT-locked handshake + the one revenue-free introspection call.
    "initialize", "tools/list",
    # (2) Bootstrap plumbing SDK clients send on connect before tools/list.
    #     `ping` is a keepalive; `logging/setLevel` is emitted by Inspector 0.22.0
    #     immediately post-handshake (PROVEN by request sniffer, 04-RESEARCH).
    #     Without these two, Inspector never reaches tools/list.
    "ping", "logging/setLevel",
    # (3) Capability-discovery lists SDK/UI clients enumerate on connect.
    #     SAFE-ONLY-WHILE-EMPTY: the server registers NO resources/prompts, so
    #     these return [] and leak zero paid product. If a future phase ever
    #     registers a real resource or prompt, these entries begin serving that
    #     product UNPAID - re-evaluate their FREE status at that point (this is
    #     the forward-risk flagged by review WR-01).
    "resources/list", "resources/templates/list", "prompts/list",
})
FREE_METHOD_PREFIXES = ("notifications/",)  # CONTEXT-locked: notifications/* free


def is_free(method: str) -> bool:
    return method in FREE_METHODS or method.startswith(FREE_METHOD_PREFIXES)


# ---------------------------------------------------------------------------
# config (PAYX-03): env read once, injectable, fail-closed mock parse
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaymentConfig:
    pay_to: str = PLACEHOLDER_PAY_TO
    price_usdt: str = "0.01"
    x_layer_rpc: str = "https://rpc.xlayer.tech"
    mock: bool = False
    base_url: str = "http://localhost:8000"
    network: str = "eip155:196"
    asset: str = XLAYER_USDT
    # PAYX-04 real settlement (deploy-time, human-only OKX creds). Empty by
    # default -> facilitator_ready() is False -> make_verifier stays fail-closed.
    okx_api_key: str = ""
    okx_secret_key: str = ""
    okx_passphrase: str = ""
    okx_base_url: str = "https://web3.okx.com"

    def facilitator_ready(self) -> bool:
        """True ONLY when real OKX-facilitator settlement can be enabled: all
        three OKX API credentials present AND a real payTo configured. Absent
        any of them, make_verifier returns the fail-closed UnconfiguredVerifier
        (every paid call 402s) - real settlement is never on by accident."""
        return bool(
            self.okx_api_key
            and self.okx_secret_key
            and self.okx_passphrase
            and self.pay_to != PLACEHOLDER_PAY_TO
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "PaymentConfig":
        env = os.environ if env is None else env
        cfg = cls(
            pay_to=env.get("TRUSTLENS_PAY_TO", PLACEHOLDER_PAY_TO),
            price_usdt=env.get("TRUSTLENS_PRICE_USDT", "0.01"),
            x_layer_rpc=env.get("X_LAYER_RPC", "https://rpc.xlayer.tech"),
            # fail-closed: ONLY the exact string "1" enables mock mode
            mock=env.get("X402_MOCK") == "1",
            base_url=env.get("TRUSTLENS_BASE_URL", "http://localhost:8000"),
            okx_api_key=env.get("OKX_API_KEY", ""),
            okx_secret_key=env.get("OKX_SECRET_KEY", ""),
            okx_passphrase=env.get("OKX_PASSPHRASE", ""),
            okx_base_url=env.get("OKX_BASE_URL", "https://web3.okx.com"),
        )
        if cfg.pay_to == PLACEHOLDER_PAY_TO:
            log.warning(
                "TRUSTLENS_PAY_TO is unset - using the placeholder address; "
                "real payments CANNOT settle until it is configured"
            )
        okx_flags = (bool(cfg.okx_api_key), bool(cfg.okx_secret_key), bool(cfg.okx_passphrase))
        if any(okx_flags) and not all(okx_flags):
            log.warning(
                "OKX facilitator credentials are partially set - real settlement "
                "stays DISABLED (fail-closed) until OKX_API_KEY, OKX_SECRET_KEY, "
                "and OKX_PASSPHRASE are ALL present (values never logged)"
            )
        return cfg


# ---------------------------------------------------------------------------
# amount conversion (never float)
# ---------------------------------------------------------------------------


def usdt_to_atomic(price: str, decimals: int = USDT_DECIMALS) -> str:
    """Convert a human decimal USDT string to an atomic-unit string.

    "0.01" -> "10000" (6 decimals). Exact Decimal arithmetic; rejects
    non-finite, non-positive, and sub-atomic precision inputs. The accepted
    grammar is deliberately strict (``[0-9]+(.[0-9]+)?([eE][+-]?[0-9]+)?``):
    whitespace-padded ("  0.01  ", "0.01\\n"), sign-prefixed ("+0.01"), and
    PEP-515 underscore-grouped ("1_000") forms are REJECTED rather than
    silently normalized by Decimal(), because this value is a trusted-but-
    typo-prone env var (TRUSTLENS_PRICE_USDT) read once at startup. Values
    above MAX_PRICE_USDT are rejected as misconfiguration.
    """
    if not isinstance(price, str):
        raise TypeError(f"price must be a string, got {type(price).__name__}")
    # Grammar gate BEFORE Decimal: fullmatch so no surrounding whitespace,
    # sign, or underscore-grouping slips through Decimal's lenient parser.
    if not _PRICE_RE.fullmatch(price):
        raise ValueError(f"invalid price format: {price!r}")
    try:
        d = Decimal(price)
    except InvalidOperation as exc:
        raise ValueError(f"invalid price: {price!r}") from exc
    if not d.is_finite():
        raise ValueError(f"price must be finite: {price!r}")
    if d <= 0:
        raise ValueError(f"price must be positive: {price!r}")
    if d > MAX_PRICE_USDT:
        raise ValueError(
            f"price {price!r} exceeds the sanity ceiling of "
            f"{MAX_PRICE_USDT} USDT (misconfiguration)"
        )
    atomic = d.scaleb(decimals)  # shift exponent by +decimals, exactly
    if atomic != atomic.to_integral_value():
        raise ValueError(
            f"price {price!r} has more precision than {decimals} decimals"
        )
    return str(int(atomic))


# ---------------------------------------------------------------------------
# payment requirements (PAYX-01): locked JSON shape, byte-stable serialization
# ---------------------------------------------------------------------------


def build_requirements(cfg: PaymentConfig) -> dict[str, Any]:
    return {
        "x402Version": 2,
        "resource": {
            "url": cfg.base_url.rstrip("/") + "/mcp",
            "description": (
                "TrustLens: evidence-based trust scores for OKX.AI "
                "marketplace agents over MCP"
            ),
            "mimeType": "application/json",
        },
        "accepts": [
            {
                "scheme": "exact",
                "network": cfg.network,
                "asset": cfg.asset,
                "amount": usdt_to_atomic(cfg.price_usdt),
                "payTo": cfg.pay_to,
                "maxTimeoutSeconds": 300,
            }
        ],
    }


def canonical_json(obj: Any) -> bytes:
    """Byte-stable serialization: sorted keys, compact separators, ASCII-only.

    The SAME bytes are used for the 402 body and (base64d) for the
    PAYMENT-REQUIRED header, so header always decodes to exactly the body.
    """
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def encode_header(payload: bytes) -> bytes:
    """Standard RFC 4648 base64 (with padding) - per x402 v2 HTTP transport."""
    return base64.b64encode(payload)


# ---------------------------------------------------------------------------
# verifier seam (PAYX-02)
# ---------------------------------------------------------------------------


class PaymentVerifier(Protocol):
    async def verify(self, payment_b64: str, requirements: dict) -> bool: ...

    async def settle(self, payment_b64: str, requirements: dict) -> dict: ...


class MockVerifier:
    """Active ONLY under X402_MOCK == "1". Accepts any non-empty signature.

    Documented mock token: any non-empty PAYMENT-SIGNATURE value (demo:
    -H "PAYMENT-SIGNATURE: demo"). Replay is NOT detected in mock mode -
    accepted, documented limitation; real facilitator enforces nonces.
    """

    mode = "mock"

    def __init__(self, cfg: PaymentConfig) -> None:
        self.cfg = cfg

    async def verify(self, payment_b64: str, requirements: dict) -> bool:
        return bool(payment_b64.strip())

    async def settle(self, payment_b64: str, requirements: dict) -> dict:
        return {
            "success": True,
            "transaction": "0x" + "0" * 64,
            "network": self.cfg.network,
            "payer": "0x" + "0" * 40,
            "mock": True,
        }


class UnconfiguredVerifier:
    """Production default without creds: every paid request 402s (fail closed)."""

    mode = "unconfigured"

    async def verify(self, payment_b64: str, requirements: dict) -> bool:
        return False

    async def settle(self, payment_b64: str, requirements: dict) -> dict:
        raise RuntimeError("UnconfiguredVerifier cannot settle")


# ---------------------------------------------------------------------------
# real settlement (PAYX-04): OKX facilitator verifier at the SAME seam
# ---------------------------------------------------------------------------
# Option B: the pure-ASGI X402Middleware keeps doing the MCP-method gating + 402;
# ONLY verify/settle swap to the OKX x402 facilitator. Selected by make_verifier
# exclusively when cfg.facilitator_ready() (all three OKX creds + real payTo) -
# a route-based middleware swap would gate all of /mcp uniformly and break the
# free MCP handshake (initialize/tools/list), so we keep our method-level gate.
#
# API verified 2026-07-17 against the installed okxweb3-app-x402==0.1.1:
#   from x402.http import OKXAuthConfig, OKXFacilitatorClient, OKXFacilitatorConfig
#   from x402.schemas.payments import PaymentPayload, PaymentRequirements
#   client = OKXFacilitatorClient(OKXFacilitatorConfig(
#       auth=OKXAuthConfig(api_key=..., secret_key=..., passphrase=...),
#       base_url="https://web3.okx.com"))          # HOSTED facilitator, HMAC-signed
#   await client.verify(PaymentPayload, PaymentRequirements) -> VerifyResponse(.is_valid)
#   await client.settle(PaymentPayload, PaymentRequirements) -> SettleResponse(.model_dump())
# The hosted client POSTs verify/settle to OKX and needs NO local web3/eth-account
# and NO scheme registration (no x402ResourceServer / ExactEvmScheme). To keep the
# SDK out of the core app and the tests, OkxFacilitatorVerifier stays SDK-free and
# passes plain dicts; the dict->pydantic-model conversion is confined to the
# _OkxClientAdapter built in _build_okx_facilitator, so the injected test fake needs
# no SDK. The facilitator verify/settle call surface is isolated in _okx_verify /
# _okx_settle.


def _decode_payment_payload(payment_b64: str) -> dict:
    """Base64 PAYMENT-SIGNATURE header value -> x402 payload dict
    ({x402Version, resource, accepted, payload:{signature, authorization}})."""
    return json.loads(base64.b64decode(payment_b64))


def _build_okx_facilitator(cfg: PaymentConfig):
    """Lazily import okxweb3-app-x402 (v0.1.1) and build a dict->model adapter over
    the OKX HOSTED facilitator client for X Layer. Imported ONLY here so the SDK is
    never required by the core app, the tests, or the fail-closed default. The
    adapter keeps OkxFacilitatorVerifier SDK-free (it passes plain dicts): the SDK's
    pydantic models are constructed here, at the real-client boundary, so the
    injected fake in tests needs no SDK.

    API verified 2026-07-17 against the installed okxweb3-app-x402==0.1.1:
    OKXFacilitatorClient POSTs verify/settle to OKX's hosted facilitator (base_url
    default https://web3.okx.com, HMAC-signed) - no local web3/eth-account or scheme
    registration. verify -> VerifyResponse(.is_valid); settle -> SettleResponse.
    """
    from x402.http import OKXAuthConfig, OKXFacilitatorClient, OKXFacilitatorConfig
    from x402.schemas.payments import PaymentPayload, PaymentRequirements

    client = OKXFacilitatorClient(
        OKXFacilitatorConfig(
            auth=OKXAuthConfig(
                api_key=cfg.okx_api_key,
                secret_key=cfg.okx_secret_key,
                passphrase=cfg.okx_passphrase,
            ),
            base_url=cfg.okx_base_url,
        )
    )

    class _OkxClientAdapter:
        """Convert the decoded PAYMENT-SIGNATURE dict + our requirements envelope
        into the SDK's pydantic models, then delegate to the hosted client."""

        async def verify(self, payload: dict, requirements: dict):
            return await client.verify(
                PaymentPayload.model_validate(payload),
                PaymentRequirements.model_validate(requirements["accepts"][0]),
            )

        async def settle(self, payload: dict, requirements: dict):
            return await client.settle(
                PaymentPayload.model_validate(payload),
                PaymentRequirements.model_validate(requirements["accepts"][0]),
            )

    return _OkxClientAdapter()


async def _okx_verify(facilitator, payload: dict, requirements: dict):
    """Thin dict-in pass-through to the injected facilitator/adapter's async verify.
    API verified against okxweb3-app-x402==0.1.1: the real _OkxClientAdapter
    (built in _build_okx_facilitator) constructs the SDK's PaymentPayload /
    PaymentRequirements models from these plain dicts and calls the hosted client,
    whose VerifyResponse exposes `.is_valid`. Kept dict-in so this seam and the
    injected test fake never need the SDK."""
    return await facilitator.verify(payload, requirements)


async def _okx_settle(facilitator, payload: dict, requirements: dict):
    """Thin dict-in pass-through to the injected facilitator/adapter's async settle.
    API verified against okxweb3-app-x402==0.1.1: the real _OkxClientAdapter builds
    the SDK's pydantic models from these plain dicts and calls the hosted client,
    returning a SettleResponse that _receipt_dict normalizes. Kept dict-in so this
    seam and the injected test fake never need the SDK."""
    return await facilitator.settle(payload, requirements)


def _receipt_dict(result) -> dict:
    """Normalize a facilitator settlement result to a plain dict for the
    PAYMENT-RESPONSE receipt (dict as-is, else pydantic/obj -> dict)."""
    if isinstance(result, dict):
        return result
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(result, attr, None)
        if callable(fn):
            out = fn()
            if isinstance(out, dict):
                return out
    return {"settled": True, "detail": str(result)}


class OkxFacilitatorVerifier:
    """Real settlement via the OKX x402 facilitator, at the SAME PaymentVerifier
    seam as Mock/Unconfigured. Fail-closed by construction: ANY verify error is
    swallowed to False (the request 402s), so a mis-set credential or an SDK
    shape mismatch can never serve paid product unpaid or crash the gate; settle
    runs only after a True verify. The facilitator is built lazily (or injected
    for tests)."""

    mode = "okx-facilitator"

    def __init__(self, cfg: PaymentConfig, facilitator: Any | None = None) -> None:
        self.cfg = cfg
        self._facilitator = facilitator  # injected in tests; built lazily otherwise

    def _get_facilitator(self):
        if self._facilitator is None:
            self._facilitator = _build_okx_facilitator(self.cfg)
        return self._facilitator

    async def verify(self, payment_b64: str, requirements: dict) -> bool:
        try:
            facilitator = self._get_facilitator()
            payload = _decode_payment_payload(payment_b64)
            result = await _okx_verify(facilitator, payload, requirements)
            return bool(getattr(result, "is_valid", result))
        except Exception:  # fail-closed: deny (402), never crash the gate
            log.exception("OKX facilitator verify failed - denying (402)")
            return False

    async def settle(self, payment_b64: str, requirements: dict) -> dict:
        facilitator = self._get_facilitator()
        payload = _decode_payment_payload(payment_b64)
        result = await _okx_settle(facilitator, payload, requirements)
        return _receipt_dict(result)


def make_verifier(cfg: PaymentConfig) -> PaymentVerifier:
    if cfg.mock:
        log.warning("X402_MOCK=1 - payments are NOT verified (mock mode)")
        return MockVerifier(cfg)
    if cfg.facilitator_ready():
        log.info("x402 verifier: OKX facilitator (real settlement on %s)", cfg.network)
        return OkxFacilitatorVerifier(cfg)
    log.info("x402 verifier: unconfigured (all paid requests will 402)")
    return UnconfiguredVerifier()


# ---------------------------------------------------------------------------
# the gate: pure ASGI middleware (NOT BaseHTTPMiddleware)
# ---------------------------------------------------------------------------


def _get_header(scope: dict, name: bytes) -> str | None:
    for k, v in scope.get("headers", []):
        if k == name:
            return v.decode("latin-1")
    return None


def _replay(body: bytes):
    """A receive() that replays an already-buffered body downstream."""
    sent = False

    async def receive() -> dict:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive


def jsonrpc_method(body: bytes) -> str | None:
    """Method of a single JSON-RPC message; None for anything else.

    None covers: empty body, invalid JSON/UTF-8, non-object payloads
    (batch arrays - removed in MCP 2025-06-18), missing/non-string method.
    Duplicate keys resolve LAST-wins, same as every json.loads in the stack,
    so the gate and the MCP server always agree on the method.
    """
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


class X402Middleware:
    """402-gate POST /mcp* ; everything else passes untouched.

    Wire behavior (locked by 04-CONTEXT):
    - bodyless/unparseable POST /mcp -> 402 + PAYMENT-REQUIRED (OKX curl check)
    - FREE methods pass through unpaid
    - paid methods: no/invalid PAYMENT-SIGNATURE -> 402; verified -> settle ->
      serve with PAYMENT-RESPONSE header appended
    """

    def __init__(
        self,
        app,
        config: PaymentConfig | None = None,
        verifier: PaymentVerifier | None = None,
    ) -> None:
        self.app = app
        self.config = config if config is not None else PaymentConfig.from_env()
        self.verifier = verifier if verifier is not None else make_verifier(self.config)
        self.requirements = build_requirements(self.config)
        self._req_body = canonical_json(self.requirements)
        self._req_b64 = encode_header(self._req_body)

    def _gated(self, scope: dict) -> bool:
        path = scope.get("path", "")
        return scope.get("method") == "POST" and (
            path == "/mcp" or path.startswith("/mcp/")
        )

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not self._gated(scope):
            return await self.app(scope, receive, send)

        # buffer the body with a hard cap (DoS guard)
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return  # client gone; nothing to answer
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > MAX_BODY_BYTES:
                return await self._send_json(
                    send,
                    413,
                    {"error": "payload_too_large", "max_bytes": MAX_BODY_BYTES},
                )
            if chunk:
                chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)

        method = jsonrpc_method(body)
        if method is not None and is_free(method):
            return await self.app(scope, _replay(body), send)

        # paid (tools/call and everything unknown) or unparseable
        signature = _get_header(scope, HDR_PAYMENT_SIGNATURE)
        if signature is None or not await self.verifier.verify(
            signature, self.requirements
        ):
            return await self._send_402(send)

        receipt = await self.verifier.settle(signature, self.requirements)
        receipt_b64 = encode_header(canonical_json(receipt))

        async def send_with_receipt(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((HDR_PAYMENT_RESPONSE, receipt_b64))
                message = {**message, "headers": headers}
            await send(message)

        return await self.app(scope, _replay(body), send_with_receipt)

    async def _send_402(self, send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 402,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(self._req_body)).encode("ascii")),
                    (HDR_PAYMENT_REQUIRED, self._req_b64),
                ],
            }
        )
        await send({"type": "http.response.body", "body": self._req_body})

    @staticmethod
    async def _send_json(send, status: int, obj: dict) -> None:
        body = canonical_json(obj)
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
