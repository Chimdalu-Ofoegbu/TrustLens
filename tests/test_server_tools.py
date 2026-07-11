"""Tool-level tests for the TrustLens MCP core (03-02) against the real DB.

Direct-call tests use the plain functions (FastMCP v3 decorators return the
original function). Protocol-level tests run through the in-memory Client
inside asyncio.run() wrappers — no async test plugin, zero new dev deps
(research-verified pattern).
"""
import asyncio
import json
import re
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import scoring
from server.db import connect_ro
from server.tools import (
    category_leaderboard,
    compare_agents,
    marketplace_stats,
    mcp,
    score_agent,
)

SEED_TS = "2026-07-10T00:00:00Z"


def call(tool_name, args):
    async def inner():
        async with Client(mcp) as c:
            return await c.call_tool(tool_name, args, raise_on_error=False)

    return asyncio.run(inner())


# 1. Exactly 4 tools with schemas (MCPS-01)
def test_exactly_four_tools_with_output_schemas(real_db):
    tools = asyncio.run(mcp.list_tools())
    assert sorted(t.name for t in tools) == [
        "category_leaderboard",
        "compare_agents",
        "marketplace_stats",
        "score_agent",
    ]
    for tool in tools:
        assert tool.output_schema  # non-empty derived schema on every tool


# 2. Golden card via direct call
def test_golden_card_direct_call(real_db):
    card = score_agent("3345")
    assert card["agent_id"] == "3345"
    assert card["name"] == "这个能吃吗？"
    assert card["category"] == "Lifestyle & Health"
    assert card["score"] == 94
    assert card["grade"] == "A"
    assert card["confidence"] == "high"
    assert card["score_version"] == "1.0.0"


# 3. Lookup ladder: exact name and NFKC name_key resolve the same agent
def test_lookup_ladder_cjk_variants(real_db):
    by_name = score_agent("这个能吃吗？")  # exact name (fullwidth ?)
    by_key = score_agent("这个能吃吗?")   # ASCII ? -> NFKC name_key
    assert by_name["agent_id"] == "3345"
    assert by_key["agent_id"] == "3345"
    assert "ambiguous_matches" not in by_name
    assert "ambiguous_matches" not in by_key


# 4. Envelope on all 4 tools (MCPS-02)
def test_envelope_on_all_four_tools(real_db, monkeypatch):
    monkeypatch.delenv("TRUSTLENS_BASE_URL", raising=False)
    results = [
        score_agent("3345"),
        compare_agents(["3345", "2662"]),
        category_leaderboard("Trading & DeFi"),
        marketplace_stats(),
    ]
    for result in results:
        assert result["generated_at"] == SEED_TS
        assert result["data_as_of"] == SEED_TS
        assert result["methodology_url"] == "http://localhost:8000/#methodology"
        assert result["score_version"] == "1.0.0"
        assert result["disclaimer"] == scoring.DISCLAIMER


# 5. Determinism (MCPS-02): identical args -> identical JSON
def test_deterministic_responses(real_db):
    calls = [
        (score_agent, ("3345",)),
        (compare_agents, (["3345", "2662"],)),
        (category_leaderboard, ("Trading & DeFi",)),
        (marketplace_stats, ()),
    ]
    for fn, args in calls:
        first = fn(*args)
        second = fn(*args)
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# 6. Collision disclosure: lowest id wins, all matches disclosed
def test_collision_disclosure(real_db):
    card = score_agent("人生说明书 · life book")
    assert card["agent_id"] == "4353"
    assert len(card["ambiguous_matches"]) == 2
    assert {m["agent_id"] for m in card["ambiguous_matches"]} == {"4353", "4517"}

    card2 = score_agent("链上任务助手")
    assert card2["agent_id"] == "2662"
    assert {m["agent_id"] for m in card2["ambiguous_matches"]} == {"2662", "2791"}


# 7. NR card is a full valid answer (passes server-side output validation)
def test_nr_card_is_valid_answer(real_db):
    conn = connect_ro(real_db)
    try:
        nr_id = conn.execute(
            "SELECT agent_id FROM scores WHERE score IS NULL ORDER BY agent_id LIMIT 1"
        ).fetchone()["agent_id"]
    finally:
        conn.close()

    card = score_agent(nr_id)
    assert card["score"] is None
    assert card["grade"] == "NR"
    assert card["confidence"] == "low"
    for key in (
        "agent_id", "name", "category", "score_version", "generated_at",
        "data_as_of", "methodology_url", "disclaimer", "components", "marketplace",
    ):
        assert key in card

    res = call("score_agent", {"agent_id_or_name": nr_id})
    assert res.is_error is False  # NR card conforms to the derived outputSchema


# 8. Not-found via Client: neutral deterministic JSON, no internals (T-03-06)
def test_not_found_neutral_error_no_leaks(real_db):
    res = call("score_agent", {"agent_id_or_name": "no-such-agent-xyz"})
    assert res.is_error is True
    text = res.content[0].text
    payload = json.loads(text)
    assert payload["error"] == "not_found"
    assert payload["query"] == "no-such-agent-xyz"
    assert "Traceback" not in text
    assert "server/db" not in text
    assert "sqlite3" not in text


# 9. Injection probes (T-03-05): parameterized queries keep the table intact
def test_injection_probes(real_db):
    with pytest.raises(ToolError) as exc:
        score_agent("' OR 1=1 --")
    assert "not_found" in str(exc.value)

    res = call(
        "category_leaderboard",
        {"category": "x'); DROP TABLE agents;--", "limit": 5},
    )
    assert res.is_error is True
    assert json.loads(res.content[0].text)["error"] == "invalid_argument"

    conn = connect_ro(real_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0] == 272
    finally:
        conn.close()

    with pytest.raises(ToolError) as exc:  # LIKE wildcard escaped in candidates
        score_agent("%")
    assert "not_found" in str(exc.value)


# 10. Caps (T-03-07): ids 2-10, limit 1-50
def test_argument_caps(real_db):
    with pytest.raises(ToolError):
        compare_agents(["3345"])
    with pytest.raises(ToolError):
        compare_agents(["3345"] * 11)
    with pytest.raises(ToolError):
        category_leaderboard("Trading & DeFi", limit=0)
    with pytest.raises(ToolError):
        category_leaderboard("Trading & DeFi", limit=51)
    assert category_leaderboard("Trading & DeFi", limit=50)["entries"]


# 11. compare winners: 5 component keys + overall winner from card scores
def test_compare_winners(real_db):
    result = compare_agents(["3345", "2662"])
    assert set(result["component_winners"]) == {
        "sales_volume_velocity",
        "review_signal_ratio",
        "rating_credibility",
        "price_vs_category",
        "listing_age_consistency",
    }
    scores = {c["agent_id"]: c["score"] for c in result["agents"]}
    non_null = {aid: s for aid, s in scores.items() if s is not None}
    if not non_null:
        expected = None
    else:
        best = max(non_null.values())
        leaders = [aid for aid, s in non_null.items() if s == best]
        expected = leaders[0] if len(leaders) == 1 else None
    assert result["overall_winner"] in {"3345", "2662", None}
    assert result["overall_winner"] == expected


# 12. category_leaderboard shape and pinned census total
def test_category_leaderboard_shape(real_db):
    result = category_leaderboard("Trading & DeFi", 5)
    assert result["category"] == "Trading & DeFi"
    entries = result["entries"]
    assert len(entries) <= 5
    assert [e["rank"] for e in entries] == list(range(1, len(entries) + 1))
    for entry in entries:
        assert set(entry) == {"rank", "agent_id", "name", "score", "grade", "confidence"}
        assert entry["score"] is not None
    scores = [e["score"] for e in entries]
    assert scores == sorted(scores, reverse=True)
    assert result["total_in_category"] == 41  # pinned census count (scored + NR)


# 13. marketplace_stats goldens over the real 272-agent census
def test_marketplace_stats_goldens(real_db):
    stats = marketplace_stats()
    assert stats["agents_total"] == 272
    assert stats["scored"] == 121
    assert stats["not_rated"] == 151
    assert stats["grade_distribution"] == {
        "A": 12, "B": 9, "C": 19, "D": 54, "F": 27, "NR": 151,
    }
    assert len(stats["category_counts"]) == 9
    assert stats["category_counts"]["Market Data & Analytics"] == 70
    assert isinstance(stats["median_price_usdt"], float)


# 14. Strict input validation (conforming FastMCP behavior, T-03-08)
def test_strict_input_validation(real_db):
    res = call("score_agent", {"agent_id_or_name": 3345})  # integer, not string
    assert res.is_error is True
    assert "Input should be a valid string" in res.content[0].text


# 15. Banned vocabulary never appears in server source (T-03-09)
def test_banned_vocabulary_absent_from_server_source(real_db):
    banned = re.compile(r"(?i)(fraud|scam|fake|manipulat)")
    repo = Path(__file__).resolve().parents[1]
    for rel in ("server/tools.py", "server/db.py"):
        assert not banned.search((repo / rel).read_text(encoding="utf-8")), rel


# 16. methodology_url honors TRUSTLENS_BASE_URL at call time
def test_methodology_url_honors_env(real_db, monkeypatch):
    monkeypatch.setenv("TRUSTLENS_BASE_URL", "https://example.test")
    card = score_agent("3345")
    assert card["methodology_url"] == "https://example.test/#methodology"
