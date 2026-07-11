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

# FREE = MCP protocol plumbing (locked: initialize, notifications/*, tools/list;
# ping added as plumbing - one-line flip to gate everything per CONTEXT).
FREE_METHODS = frozenset({
    "initialize", "ping", "tools/list",
    # client bootstrap plumbing - Inspector 0.22.0 sends logging/setLevel
    # on connect (PROVEN by sniffer); discovery lists are free for
    # marketplace/Inspector introspection
    "logging/setLevel", "resources/list", "resources/templates/list",
    "prompts/list",
})
FREE_METHOD_PREFIXES = ("notifications/",)


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
        )
        if cfg.pay_to == PLACEHOLDER_PAY_TO:
            log.warning(
                "TRUSTLENS_PAY_TO is unset - using the placeholder address; "
                "real payments CANNOT settle until it is configured"
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


def make_verifier(cfg: PaymentConfig) -> PaymentVerifier:
    if cfg.mock:
        log.warning("X402_MOCK=1 - payments are NOT verified (mock mode)")
        return MockVerifier(cfg)
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
