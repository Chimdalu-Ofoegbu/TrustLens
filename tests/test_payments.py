"""Unit proof matrix for server/payments.py (PAYX-01/02/03).

Every expectation was executed in the Phase 4 PoC (69/69) - see 04-RESEARCH.md.
No env mutation anywhere: from_env takes explicit dicts; async verifier methods
run via asyncio.run (no pytest-asyncio in this repo).
"""
import asyncio
import base64
import json
import logging

import pytest

from server.payments import (
    FREE_METHODS,
    MAX_BODY_BYTES,
    MAX_PRICE_USDT,
    PLACEHOLDER_PAY_TO,
    XLAYER_USDT,
    MockVerifier,
    PaymentConfig,
    UnconfiguredVerifier,
    X402Middleware,
    build_requirements,
    canonical_json,
    encode_header,
    is_free,
    jsonrpc_method,
    make_verifier,
    usdt_to_atomic,
)


# 1. Decimal -> atomic conversion, the PROVEN property table (no float math).
@pytest.mark.parametrize(
    "price, expected",
    [
        ("0.01", "10000"),
        ("0.001", "1000"),
        ("1", "1000000"),
        ("0.000001", "1"),
        ("2.5", "2500000"),
        ("0.010000", "10000"),  # trailing zeros normalize
        ("1e2", "100000000"),  # Decimal accepts scientific notation, exactly
    ],
)
def test_usdt_to_atomic_conversions(price, expected):
    assert usdt_to_atomic(price) == expected


# 2. Rejections: non-finite / non-positive / sub-atomic / unparseable, PLUS the
#    WR-02 grammar tightening. The env-var price (TRUSTLENS_PRICE_USDT) is read
#    once at startup, so a raised ValueError is the correct fail-loud behavior on
#    an operator typo. Decimal() ALONE would silently accept the whitespace/sign/
#    underscore forms below; _PRICE_RE.fullmatch() rejects them BEFORE Decimal so
#    "1_000" is never misread as one thousand USDT and " 0.01 " never strips-and-
#    passes. "1e1000"/"2000000" trip the MAX_PRICE_USDT sanity ceiling.
@pytest.mark.parametrize(
    "bad",
    [
        # non-finite / non-positive / sub-atomic / unparseable (original set)
        "0.0000001", "-0.01", "0", "abc", "NaN", "Infinity", "-Infinity", "",
        # WR-02: whitespace-padded (newline/leading/trailing/internal)
        "0.01\n", " 0.01 ", "  0.01", "0.01  ", "0. 01",
        # WR-02: sign-prefixed
        "+0.01", "+1",
        # WR-02: PEP-515 underscore grouping (Decimal would accept as 1000)
        "1_000", "1_0",
        # WR-02: magnitude ceiling (> MAX_PRICE_USDT = 1,000,000 USDT)
        "1e1000", "2000000", "1000001",
    ],
)
def test_usdt_to_atomic_rejections(bad):
    # "NaN"/"Infinity"/"-Infinity" parse as VALID Decimals - the is_finite()
    # check is what catches them (a plain try/except would let them through).
    # The grammar/ceiling additions above all surface as ValueError too, so the
    # single raises-clause covers the whole rejection contract.
    with pytest.raises(ValueError):
        usdt_to_atomic(bad)
    # Separate assert: a float (not str) is a TypeError - the signature demands
    # an exact string so float drift can never enter the amount.
    with pytest.raises(TypeError):
        usdt_to_atomic(0.01)  # type: ignore[arg-type]


# 2b. WR-02 ceiling boundary: exactly MAX_PRICE_USDT is still ACCEPTED (the
#     ceiling rejects strictly-greater), while the golden low-end path is
#     unchanged. Guards against an off-by-one that would reject the boundary.
def test_usdt_to_atomic_ceiling_boundary():
    assert usdt_to_atomic(str(MAX_PRICE_USDT)) == "1000000000000"  # 1e6 * 1e6
    assert usdt_to_atomic("0.01") == "10000"  # golden low-end untouched


# 3. Requirements JSON is byte-stable and pure ASCII.
def test_requirements_byte_stability():
    a = canonical_json(build_requirements(PaymentConfig()))
    b = canonical_json(build_requirements(PaymentConfig()))
    assert a == b
    a.decode("ascii")  # ASCII-only: does not raise


# 4. Golden bytes - regenerate-and-pin against the research-locked default config
#    (placeholder payTo, price "0.01", base_url http://localhost:8000).
def test_requirements_golden_bytes():
    GOLDEN = (
        b'{"accepts":[{"amount":"10000","asset":"0x779ded0c9e1022225f8e0630b35a9b54be713736",'
        b'"maxTimeoutSeconds":300,"network":"eip155:196",'
        b'"payTo":"0x0000000000000000000000000000000000000000","scheme":"exact"}],'
        b'"resource":{"description":"TrustLens: evidence-based trust scores for OKX.AI '
        b'marketplace agents over MCP","mimeType":"application/json",'
        b'"url":"http://localhost:8000/mcp"},"x402Version":2}'
    )
    assert canonical_json(build_requirements(PaymentConfig())) == GOLDEN


# 5. Every locked field of the requirements object.
def test_requirements_locked_fields():
    req = build_requirements(PaymentConfig())
    acc = req["accepts"][0]
    assert req["x402Version"] == 2
    assert acc["scheme"] == "exact"
    assert acc["network"] == "eip155:196"
    assert acc["amount"] == "10000"
    assert acc["asset"] == XLAYER_USDT
    assert acc["maxTimeoutSeconds"] == 300
    assert acc["payTo"] == PLACEHOLDER_PAY_TO
    assert req["resource"]["url"] == "http://localhost:8000/mcp"
    assert req["resource"]["mimeType"] == "application/json"

    # base_url rstrip proven: a trailing slash never doubles into the url.
    req2 = build_requirements(PaymentConfig(base_url="https://example.com/"))
    assert req2["resource"]["url"] == "https://example.com/mcp"

    # payTo carries through from config (env-only, never hardcoded).
    req3 = build_requirements(PaymentConfig(pay_to="0x" + "11" * 20))
    assert req3["accepts"][0]["payTo"] == "0x" + "11" * 20


# 6. Header base64 round-trip (RFC 4648 with padding, no newlines).
def test_header_b64_roundtrip():
    b = canonical_json(build_requirements(PaymentConfig()))
    h = encode_header(b)
    assert base64.b64decode(h) == b
    assert b"\n" not in h
    assert len(h) % 4 == 0  # padded to a multiple of four


# 7. X402_MOCK fail-closed: ONLY the exact string "1" enables mock mode.
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1", True),
        ("0", False),
        ("true", False),
        ("TRUE", False),
        ("yes", False),
        (" 1", False),
        ("1 ", False),
        ("", False),
    ],
)
def test_x402_mock_exact_one_fail_closed(raw, expected):
    assert PaymentConfig.from_env({"X402_MOCK": raw}).mock is expected
    # The ninth case: X402_MOCK entirely absent -> not mock (unset default).
    assert PaymentConfig.from_env({}).mock is False


# 8. from_env reads all five vars, and yields documented defaults on empty.
def test_from_env_reads_all_five_vars():
    cfg = PaymentConfig.from_env(
        {
            "TRUSTLENS_PAY_TO": "0x" + "22" * 20,
            "TRUSTLENS_PRICE_USDT": "0.02",
            "X_LAYER_RPC": "https://rpc.example",
            "X402_MOCK": "1",
            "TRUSTLENS_BASE_URL": "https://tl.example",
        }
    )
    assert cfg.pay_to == "0x" + "22" * 20
    assert cfg.price_usdt == "0.02"
    assert cfg.x_layer_rpc == "https://rpc.example"
    assert cfg.mock is True
    assert cfg.base_url == "https://tl.example"

    defaults = PaymentConfig.from_env({})
    assert defaults.pay_to == PLACEHOLDER_PAY_TO
    assert defaults.price_usdt == "0.01"
    assert defaults.x_layer_rpc == "https://rpc.xlayer.tech"
    assert defaults.mock is False
    assert defaults.base_url == "http://localhost:8000"


# 9. Placeholder payTo warning fires when unset, and NOT for a real address.
def test_placeholder_payto_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="server.payments"):
        PaymentConfig.from_env({})
    assert any("TRUSTLENS_PAY_TO is unset" in r.message for r in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="server.payments"):
        PaymentConfig.from_env({"TRUSTLENS_PAY_TO": "0x" + "ab" * 20})
    assert not any("TRUSTLENS_PAY_TO" in r.message for r in caplog.records)


# 10. make_verifier selects the right implementation and logs the mode banner.
def test_make_verifier_selection_and_banners(caplog):
    with caplog.at_level(logging.INFO, logger="server.payments"):
        v = make_verifier(PaymentConfig(mock=True))
    assert isinstance(v, MockVerifier)
    assert any("NOT verified (mock mode)" in r.message for r in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="server.payments"):
        u = make_verifier(PaymentConfig())
    assert isinstance(u, UnconfiguredVerifier)
    assert any("unconfigured" in r.message for r in caplog.records)


# 11. MockVerifier token semantics: non-empty-after-strip verifies; receipt shape.
def test_mock_verifier_token_semantics():
    v = MockVerifier(PaymentConfig(mock=True))
    assert asyncio.run(v.verify("demo", {})) is True
    assert asyncio.run(v.verify("", {})) is False
    assert asyncio.run(v.verify("   ", {})) is False  # whitespace-only strips empty

    r = asyncio.run(v.settle("demo", {}))
    assert r["success"] is True
    assert r["mock"] is True
    assert r["network"] == "eip155:196"
    assert set(r) >= {"success", "transaction", "network", "payer"}
    assert r["transaction"] == "0x" + "0" * 64


# 12. UnconfiguredVerifier is fail-closed: False even for a plausible signature.
def test_unconfigured_verifier_fail_closed():
    u = UnconfiguredVerifier()
    # False even for non-empty input - THE fail-closed property.
    assert asyncio.run(u.verify("valid-looking-signature", {})) is False
    with pytest.raises(RuntimeError):
        asyncio.run(u.settle("x", {}))


# 13. FREE_METHODS is the orchestrator-locked EXTENDED allowlist; tools/call is
#     never free, and unknown methods default to PAID.
#
# AUDIT TRAIL (review WR-01 / IN-02): this frozenset is deliberately WIDER than
# the 04-CONTEXT (line 28) lock, which fixes the FREE set to `initialize`,
# `notifications/*`, and `tools/list` only. The five extra methods below were
# added because 04-RESEARCH (Pitfall 1) PROVED the CONTEXT-only set bricks MCP
# Inspector: it sends `logging/setLevel` during connect and aborts on the 402
# before ever calling tools/list. The widening is intentional and orchestrator-
# approved (see the FREE_METHODS comment in server/payments.py); this test pins
# it so any *further* drift is caught, and the split below records which members
# are CONTEXT-locked vs research-added so the deviation is auditable here alone.
def test_free_methods_allowlist():
    # CONTEXT-locked members (04-CONTEXT line 28). notifications/* is via prefix.
    context_locked = {"initialize", "tools/list"}
    # Research-added bootstrap/discovery plumbing (04-RESEARCH Pitfall 1). SAFE
    # ONLY while the server registers no resources/prompts - see WR-01 note.
    research_added = {
        "ping",
        "logging/setLevel",
        "resources/list",
        "resources/templates/list",
        "prompts/list",
    }
    assert FREE_METHODS == frozenset(context_locked | research_added)
    # notifications/* are free via prefix (CONTEXT-locked, not in the frozenset).
    assert is_free("notifications/initialized") is True
    assert is_free("notifications/cancelled") is True
    # the revenue method is NEVER free.
    assert is_free("tools/call") is False
    # locked: unknown/unlisted methods are default-paid.
    assert is_free("completion/complete") is False
    assert is_free("tools/execute_all") is False


# 14. The gate predicate: tight /mcp prefix, POST-only, no over-gating.
def test_gated_predicate():
    gate = X402Middleware(
        app=None, config=PaymentConfig(), verifier=UnconfiguredVerifier()
    )  # app is never called - _gated is pure
    assert gate._gated({"method": "POST", "path": "/mcp"}) is True
    assert gate._gated({"method": "POST", "path": "/mcp/"}) is True
    assert gate._gated({"method": "POST", "path": "/mcp/sub"}) is True
    assert gate._gated({"method": "POST", "path": "/mcpfoo"}) is False  # tight prefix
    assert gate._gated({"method": "GET", "path": "/mcp"}) is False  # only POST
    assert gate._gated({"method": "POST", "path": "/healthz"}) is False
    assert gate._gated({"method": "POST", "path": "/"}) is False


# 15. jsonrpc_method classification: None for anything non-standard;
#     last-key-wins matches the MCP server's parser (the T3 anti-smuggling property).
def test_jsonrpc_method_classification():
    assert jsonrpc_method(b"") is None
    assert jsonrpc_method(b"\xff\xfe") is None  # invalid UTF-8
    assert jsonrpc_method(b"[1,2,3]") is None  # batch arrays unparseable-by-policy
    assert jsonrpc_method(b'"just a string"') is None
    assert jsonrpc_method(b"{}") is None  # missing method
    assert jsonrpc_method(b'{"method": 5}') is None  # non-string method
    # duplicate keys resolve last-wins, same as the MCP server's json.loads:
    assert jsonrpc_method(b'{"method":"a","method":"b"}') == "b"
    assert (
        jsonrpc_method(b'{"jsonrpc":"2.0","id":1,"method":"tools/call"}')
        == "tools/call"
    )
    # MAX_BODY_BYTES is the DoS body cap; its 413 wire behavior is exercised in
    # tests/test_payments_gate.py - pin the constant value here.
    assert MAX_BODY_BYTES == 64 * 1024
