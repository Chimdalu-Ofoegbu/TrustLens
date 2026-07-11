"""Wire proof matrix: the x402 gate through the full create_app() composition
(PAYX-01/02).

Transcribed from the PoC proof suite (sections 4-8, all executed). Config always
injected - never env-derived - so tests are hermetic. Every gated-path test
covers BOTH /mcp and /mcp/ (Pitfall 8: the two paths take different code routes).
"""
import base64
import json

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.payments import MAX_BODY_BYTES, PaymentConfig
from web.build import build

H = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def init_body() -> str:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "gate-tests", "version": "0"},
            },
        }
    )


def call_body(tool: str, args: dict, id_: int | None = 3) -> str:
    msg: dict = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool, "arguments": args},
    }
    if id_ is not None:
        msg["id"] = id_
    return json.dumps(msg, ensure_ascii=False)


def decode_hdr(value: str) -> dict:
    return json.loads(base64.b64decode(value))


def handshake(client) -> dict:
    """initialize -> session headers -> notifications/initialized (all FREE)."""
    r = client.post("/mcp", headers=H, content=init_body())
    assert r.status_code == 200
    sess = {
        **H,
        "mcp-session-id": r.headers["mcp-session-id"],
        "MCP-Protocol-Version": "2025-06-18",
    }
    r = client.post(
        "/mcp",
        headers=sess,
        content=json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
    )
    assert r.status_code == 202
    return sess


@pytest.fixture(scope="module")
def static_dir(tmp_path_factory, real_db):
    """Materialize a real 272-agent leaderboard page in a tmp dist dir."""
    d = tmp_path_factory.mktemp("dist")
    build(real_db, d / "index.html")
    return d


@pytest.fixture()
def mock_client(static_dir, real_db):
    app = create_app(
        db_path=real_db,
        static_dir=static_dir,
        payment_config=PaymentConfig(mock=True),
    )
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def unconfig_client(static_dir, real_db):
    app = create_app(
        db_path=real_db,
        static_dir=static_dir,
        payment_config=PaymentConfig(),  # mock=False -> UnconfiguredVerifier
    )
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# 1. THE OKX pre-registration check, in-process, ZERO extra headers (both paths).
def test_okx_preregistration_check(mock_client):
    r = mock_client.post("/mcp")  # no body, no headers beyond httpx defaults
    assert r.status_code == 402
    assert "PAYMENT-REQUIRED" in r.headers
    req = decode_hdr(r.headers["PAYMENT-REQUIRED"])
    assert req == r.json()  # header decodes to exactly the body
    a = req["accepts"][0]
    assert (a["scheme"], a["network"], a["amount"], a["maxTimeoutSeconds"]) == (
        "exact",
        "eip155:196",
        "10000",
        300,
    )
    assert req["x402Version"] == 2
    assert "payTo" in a
    assert r.headers["content-type"] == "application/json"
    assert int(r.headers["content-length"]) == len(r.content)

    # Pitfall 8: the rewritten trailing-slash path is byte-identical.
    r2 = mock_client.post("/mcp/")
    assert r2.status_code == 402
    assert r2.content == r.content
    assert r2.headers["PAYMENT-REQUIRED"] == r.headers["PAYMENT-REQUIRED"]


# 2. The production default (unconfigured) also passes the OKX check - safe-by-default.
def test_okx_check_in_unconfigured_mode(unconfig_client):
    for path in ("/mcp", "/mcp/"):
        r = unconfig_client.post(path)
        assert r.status_code == 402
        assert "PAYMENT-REQUIRED" in r.headers


# 3. Free handshake + unpaid tools/list, NO payment header anywhere.
def test_free_handshake_and_tools_list_unpaid(mock_client):
    sess = handshake(mock_client)  # initialize 200 (session survives gate) + 202
    r = mock_client.post(
        "/mcp",
        headers=sess,
        content=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    )
    assert r.status_code == 200
    assert sorted(t["name"] for t in r.json()["result"]["tools"]) == [
        "category_leaderboard",
        "compare_agents",
        "marketplace_stats",
        "score_agent",
    ]


# 4. Inspector 0.22.0 bootstrap plumbing is free (the MCPS-05-preserving correction).
def test_bootstrap_plumbing_free(mock_client):
    sess = handshake(mock_client)
    r = mock_client.post(
        "/mcp",
        headers=sess,
        content=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "logging/setLevel",
                "params": {"level": "debug"},
            }
        ),
    )
    assert r.status_code != 402
    r = mock_client.post(
        "/mcp",
        headers=sess,
        content=json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"}),
    )
    assert r.status_code != 402


# 5. THE money test: unpaid tools/call -> 402, then paid retry on the SAME session
#    -> real 3345/A/94 card + PAYMENT-RESPONSE receipt (PAYX-02 + OPS-03 e2e clause).
def test_unpaid_tools_call_402_then_paid_retry_same_session(mock_client):
    sess = handshake(mock_client)

    r = mock_client.post(
        "/mcp",
        headers=sess,
        content=call_body("score_agent", {"agent_id_or_name": "3345"}),
    )
    assert r.status_code == 402
    assert "PAYMENT-REQUIRED" in r.headers  # the unpaid 402 does NOT kill the session

    paid = {**sess, "PAYMENT-SIGNATURE": "demo-mock-token"}
    r = mock_client.post(
        "/mcp",
        headers=paid,
        content=call_body("score_agent", {"agent_id_or_name": "3345"}),
    )
    assert r.status_code == 200
    res = r.json()["result"]
    assert res["isError"] is False
    sc = res["structuredContent"]
    assert sc["agent_id"] == "3345"
    assert sc["grade"] == "A"
    assert sc["score"] == 94

    assert "PAYMENT-RESPONSE" in r.headers
    receipt = decode_hdr(r.headers["PAYMENT-RESPONSE"])
    assert receipt["success"] is True
    assert receipt["mock"] is True
    assert receipt["network"] == "eip155:196"
    assert set(receipt) >= {"success", "transaction", "network", "payer"}


# 6. CJK argument through the paid path (buffer-and-replay is byte-perfect).
def test_paid_cjk_argument(mock_client):
    sess = handshake(mock_client)
    paid = {**sess, "PAYMENT-SIGNATURE": "demo-mock-token"}
    r = mock_client.post(
        "/mcp",
        headers=paid,
        content=call_body("score_agent", {"agent_id_or_name": "这个能吃吗？"}),
    )
    assert r.status_code == 200
    assert r.json()["result"]["structuredContent"]["agent_id"] == "3345"


# 7. Mock replay is accepted (documented limitation T-04-08).
def test_mock_replay_accepted_documented_limitation(mock_client):
    sess = handshake(mock_client)
    paid = {**sess, "PAYMENT-SIGNATURE": "demo-mock-token"}
    body = call_body("score_agent", {"agent_id_or_name": "3345"})
    assert mock_client.post("/mcp", headers=paid, content=body).status_code == 200
    # Replay is NOT detected in mock mode - accepted, documented limitation
    # (T-04-08); the deploy-time facilitator enforces authorization nonces +
    # validBefore windows on-chain.
    assert mock_client.post("/mcp", headers=paid, content=body).status_code == 200


# 8. Free routes are never gated in EITHER verifier mode.
def test_free_routes_never_gated_in_both_modes(mock_client, unconfig_client):
    for client in (mock_client, unconfig_client):
        assert client.get("/healthz").status_code == 200
        r = client.get("/")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        r = client.get("/badge/3345.svg")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/svg")


# 9. Unconfigured mode is fail-closed even WITH a signature (safe-by-default).
def test_unconfigured_fail_closed_even_with_signature(unconfig_client):
    sess = handshake(unconfig_client)  # free plumbing works unpaid
    # tools/list is free even in unconfigured mode - exactly 4 tools.
    r = unconfig_client.post(
        "/mcp",
        headers=sess,
        content=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    )
    assert r.status_code == 200
    assert len(r.json()["result"]["tools"]) == 4
    # tools/call WITH a signature -> 402: UnconfiguredVerifier rejects everything.
    # The okxweb3-app-x402 facilitator drops in at exactly this seam at deploy.
    paid = {**sess, "PAYMENT-SIGNATURE": "demo-mock-token"}
    r = unconfig_client.post(
        "/mcp",
        headers=paid,
        content=call_body("score_agent", {"agent_id_or_name": "3345"}),
    )
    assert r.status_code == 402


# 10. GET (SSE channel) and DELETE (session close) pass the gate - only POST gated.
def test_get_delete_pass_gate(mock_client):
    r = mock_client.get("/mcp", headers=H)
    assert r.status_code != 402
    sess = handshake(mock_client)
    r = mock_client.delete("/mcp", headers=sess)
    assert r.status_code != 402


# 11. T-04-01: tools/call smuggled as a NOTIFICATION (no id) is still paid.
def test_threat_notification_form_tools_call(mock_client):
    sess = handshake(mock_client)
    r = mock_client.post(
        "/mcp",
        headers=sess,
        content=call_body("score_agent", {"agent_id_or_name": "3345"}, id_=None),
    )
    # The gate keys on `method`, not id-presence: no free execution via notification.
    assert r.status_code == 402


# 12. T-04-02: JSON-RPC batch smuggling - arrays are unparseable-by-policy -> 402.
def test_threat_batch_smuggling(mock_client):
    sess = handshake(mock_client)
    batch = json.dumps(
        [
            json.loads(init_body()),
            json.loads(call_body("score_agent", {"agent_id_or_name": "3345"})),
        ]
    )
    r = mock_client.post("/mcp", headers=sess, content=batch)
    assert r.status_code == 402  # batches removed in MCP 2025-06-18


# 13. T-04-03: duplicate-key smuggling, both directions (same-parser guarantee).
def test_threat_duplicate_keys_both_directions(mock_client):
    dup1 = (
        '{"jsonrpc":"2.0","id":9,"method":"tools/call","method":"initialize",'
        '"params":{"protocolVersion":"2025-06-18","capabilities":{},'
        '"clientInfo":{"name":"dup","version":"0"}}}'
    )
    r = mock_client.post("/mcp", headers=H, content=dup1)  # fresh initialize attempt
    # last=initialize -> gate free-passes AND the server executes initialize
    # (same last-key-wins parse on both sides; no divergence, no tool ran).
    assert r.status_code == 200
    assert "serverInfo" in r.text

    sess = handshake(mock_client)
    dup2 = (
        '{"jsonrpc":"2.0","id":9,"method":"initialize","method":"tools/call",'
        '"params":{"name":"score_agent","arguments":{"agent_id_or_name":"3345"}}}'
    )
    r = mock_client.post("/mcp", headers=sess, content=dup2)
    assert r.status_code == 402  # last=tools/call -> paid


# 14. T-04-04: content-type tricks do nothing - the gate classifies raw bytes.
def test_threat_content_type_tricks(mock_client):
    sess = handshake(mock_client)
    r = mock_client.post(
        "/mcp",
        headers={**sess, "Content-Type": "text/plain"},
        content=call_body("score_agent", {"agent_id_or_name": "3345"}),
    )
    assert r.status_code == 402


# 15. T-04-05: oversized body hits the 64 KiB cap -> 413 (orchestrator-locked).
def test_threat_oversized_body_413(mock_client):
    huge = (
        b'{"method":"tools/call","padding":"'
        + b"A" * (MAX_BODY_BYTES + 1024)
        + b'"}'
    )
    r = mock_client.post("/mcp", content=huge)
    assert r.status_code == 413
    assert r.json() == {"error": "payload_too_large", "max_bytes": MAX_BODY_BYTES}


# 16. T-04-06: garbage bytes -> 402, never 500 (crash immunity by construction).
def test_threat_garbage_never_500(mock_client):
    for garbage in (b"\x00\xff\xfe", b"{not json", b'"just a string"', b"[1,2,3]"):
        r = mock_client.post("/mcp", content=garbage)
        assert r.status_code == 402
    # Pitfall 8: the same holds on the rewritten trailing-slash path.
    assert mock_client.post("/mcp/", content=b"{not json").status_code == 402


# 17. T-04-07: unknown/unlisted methods default to PAID (allowlist semantics).
def test_threat_unknown_method_paid(mock_client):
    sess = handshake(mock_client)
    r = mock_client.post(
        "/mcp",
        headers=sess,
        content=json.dumps(
            {"jsonrpc": "2.0", "id": 5, "method": "tools/execute_all"}
        ),
    )
    assert r.status_code == 402
    r = mock_client.post(
        "/mcp",
        headers=sess,
        content=json.dumps(
            {"jsonrpc": "2.0", "id": 6, "method": "completion/complete"}
        ),
    )
    assert r.status_code == 402


# 18. T-04-12: percent-encoded path buys no bypass; the tight prefix does not over-gate.
def test_threat_percent_encoded_path(mock_client):
    # TestClient/uvicorn deliver the DECODED path /mcp/foo in scope, so the
    # predicate matches and encoding buys no bypass.
    assert mock_client.post("/mcp%2Ffoo").status_code == 402
    # A lookalike path outside /mcp* has no MCP route AND is not over-gated.
    r = mock_client.post(
        "/mcpfoo",
        content=call_body("score_agent", {"agent_id_or_name": "3345"}),
    )
    assert r.status_code in (404, 405)
    assert r.status_code != 402
