"""App-level tests for the one-port TrustLens composition (03-04).

Everything runs through the full in-process HTTP stack — middleware, mounts,
MCP session manager — via TestClient used ONLY as a context manager (research
Pitfall 2: without ``with`` the StreamableHTTP session manager never
initializes and every MCP call 500s).

With ``json_response=True`` (orchestrator-locked) every /mcp response body is
plain application/json, so ``r.json()`` reads JSON-RPC messages directly — no
SSE frame parsing anywhere in this file.
"""
import json
import time

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.db import connect_ro
from web.build import build

H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

EXPECTED_TOOLS = [
    "category_leaderboard",
    "compare_agents",
    "marketplace_stats",
    "score_agent",
]


def call_body(name: str, args: dict, req_id: int = 9) -> str:
    """tools/call JSON-RPC body (CJK kept unescaped — utf-8 on the wire)."""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        },
        ensure_ascii=False,
    )


def handshake(client: TestClient) -> dict:
    """initialize -> session id -> notifications/initialized; returns headers."""
    r = client.post(
        "/mcp",
        headers=H,
        content=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "e2e", "version": "0"},
                },
            }
        ),
    )
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
    build(real_db, d / "index.html")  # web.build.build — the real page
    return d


@pytest.fixture()
def client(static_dir, real_db):
    with TestClient(create_app(db_path=real_db, static_dir=static_dir)) as c:
        yield c  # `with` = lifespan runs (Pitfall 2)


# 1. Route order — the research 3-assert test; the bare-POST assert alone
#    proves McpPathRewrite works with static mounted (405 without it).
def test_route_order(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    r = client.post(
        "/mcp",
        headers=H,
        content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
        follow_redirects=False,
    )
    assert r.status_code == 400  # NOT 405 (static swallow), NOT 307 (redirect)
    assert r.headers["content-type"].startswith("application/json")  # not HTML
    body = r.json()
    assert body["jsonrpc"] == "2.0" and "error" in body  # JSON-RPC error envelope

    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert 'id="methodology"' in r.text


# 2. Both paths served: the locked "test both /mcp and /mcp/" requirement.
def test_trailing_slash_mcp_also_served(client):
    r = client.post(
        "/mcp/",
        headers=H,
        content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
        follow_redirects=False,
    )
    assert r.status_code == 400  # never 405
    body = r.json()
    assert body["jsonrpc"] == "2.0" and "error" in body


# 3. Full e2e JSON-RPC handshake (research-verbatim sequence).
def test_full_e2e_handshake(client):
    r = client.post(
        "/mcp",
        headers=H,
        content=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "e2e", "version": "0"},
                },
            }
        ),
    )
    assert r.status_code == 200
    init = r.json()["result"]
    assert init["protocolVersion"] == "2025-06-18"
    assert init["serverInfo"]["name"] == "TrustLens"
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

    r = client.post(
        "/mcp",
        headers=sess,
        content=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    )
    tools = r.json()["result"]["tools"]
    assert sorted(t["name"] for t in tools) == EXPECTED_TOOLS  # exactly 4 (MCPS-01)
    assert all(t.get("outputSchema") for t in tools)  # schemas on the wire (MCPS-02)

    r = client.post(
        "/mcp",
        headers=sess,
        content=call_body("score_agent", {"agent_id_or_name": "这个能吃吗？"}, req_id=3),
    )
    result = r.json()["result"]
    assert result["isError"] is False
    sc = result["structuredContent"]
    assert sc["agent_id"] == "3345"
    assert sc["score"] == 94 and sc["grade"] == "A"
    assert sc["generated_at"] == "2026-07-10T00:00:00Z"
    assert sc["methodology_url"].endswith("/#methodology")


# 4. MCPS-04: both benchmark lookups < 500 ms through the full HTTP stack
#    (research recipe: one warm-up, then timed; observed ~0.04 s = 12x margin).
def test_score_agent_under_500ms(client):
    sess = handshake(client)
    client.post(
        "/mcp",
        headers=sess,
        content=call_body("score_agent", {"agent_id_or_name": "这个能吃吗？"}),
    )  # 1 warm-up call
    for arg in ("这个能吃吗？", "3345"):
        t0 = time.perf_counter()
        r = client.post(
            "/mcp",
            headers=sess,
            content=call_body("score_agent", {"agent_id_or_name": arg}),
        )
        elapsed = time.perf_counter() - t0
        assert r.status_code == 200 and elapsed < 0.5


# 5. Not-found over HTTP (STRIDE T-03-06 at the transport): neutral JSON error,
#    no traceback text ever reaches the client.
def test_not_found_over_http(client):
    sess = handshake(client)
    r = client.post(
        "/mcp",
        headers=sess,
        content=call_body("score_agent", {"agent_id_or_name": "no-such-agent-xyz"}),
    )
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["isError"] is True
    text = result["content"][0]["text"]
    payload = json.loads(text)
    assert payload["error"] == "not_found"
    assert "Traceback" not in text


# 6. healthz 503 contract (MCPS-03 / STRIDE T-03-14): fixed body, no leak.
def test_healthz_503_when_db_missing(tmp_path, static_dir):
    with TestClient(
        create_app(db_path=tmp_path / "missing.db", static_dir=static_dir)
    ) as c:
        r = c.get("/healthz")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["agents"] == 0 and body["scores"] == 0
    assert body["score_version"] is None and body["data_as_of"] is None
    # exactly the locked field set — no exception text serialized
    assert set(body) == {"status", "agents", "scores", "score_version", "data_as_of"}


# 7. Badge route (WEB-02 + STRIDE T-03-13): known, unknown, traversal, NR.
def test_badge_route(client, real_db):
    r = client.get("/badge/3345.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert r.headers["cache-control"] == "max-age=3600"
    assert "A 94" in r.text and 'viewBox="0 0 110 20"' in r.text

    r = client.get("/badge/999999999.svg")
    assert r.status_code == 200 and "N/A" in r.text  # never 404 for embeds

    # %2F traversal: starlette 1.3.1 percent-decodes BEFORE routing, so the
    # slashed path never matches the badge route; StaticFiles' anti-traversal
    # guard 404s it. No DB touch, no file read, no 500 — traversal moot.
    r = client.get("/badge/..%2F..%2Fsecret.svg", follow_redirects=False)
    assert r.status_code == 404 and "secret" not in r.text

    # %5C (backslash) traversal DOES reach the route: the allowlist regex
    # rejects it before any DB touch -> neutral N/A badge, 200.
    r = client.get("/badge/..%5C..%5Csecret.svg", follow_redirects=False)
    assert r.status_code == 200 and "N/A" in r.text

    conn = connect_ro(real_db)
    try:
        nr_id = conn.execute(
            "SELECT agent_id FROM scores WHERE score IS NULL ORDER BY agent_id LIMIT 1"
        ).fetchone()[0]
    finally:
        conn.close()
    r = client.get(f"/badge/{nr_id}.svg")
    assert r.status_code == 200 and ">NR<" in r.text


# 8. Static integrity: the real page serves whole; misses pass through as 404.
def test_static_integrity(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.text.count('<tr id="agent-') == 272
    r = client.get("/nonexistent-page")
    assert r.status_code == 404  # StaticFiles pass-through, no server error
