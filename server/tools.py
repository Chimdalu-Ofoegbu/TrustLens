"""The TrustLens MCP surface: FastMCP("TrustLens") plus exactly 4 tools (MCPS-01).

Every tool response is deterministic JSON carrying the full envelope —
generated_at, data_as_of, score_version, methodology_url, disclaimer — with
timestamp and version values SERVED from the scores table, never recomputed
and never read from the wall clock (MCPS-02).

Error channel: fastmcp.exceptions.ToolError ONLY. Plain exceptions reach
clients verbatim (research-verified information disclosure), so every tool
body re-raises unexpected failures as a neutral, deterministic ToolError and
logs the real exception server-side only (STRIDE T-03-06).
"""
import json
import logging
import os
import sqlite3
from typing import Any, NotRequired, TypedDict

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from indexer.category import CATEGORIES
from scoring import DISCLAIMER
from server import db

_LOG = logging.getLogger("server.tools")

mcp = FastMCP("TrustLens")

# The 5 component keys as stored in scores.components (fixed set).
COMPONENT_KEYS = (
    "sales_volume_velocity",
    "review_signal_ratio",
    "rating_credibility",
    "price_vs_category",
    "listing_age_consistency",
)


# --- Structured output types (research-verbatim; FastMCP derives each tool's
# outputSchema from these via serialization-mode TypeAdapter and VALIDATES
# returns server-side, so every required key must be present on every response).

class ScoreCard(TypedDict):
    agent_id: str
    name: str
    category: str
    score: int | None            # None for NR — anyOf[integer,null] in schema
    grade: str
    confidence: str
    score_version: str
    generated_at: str
    data_as_of: str
    methodology_url: str
    disclaimer: str
    components: dict[str, Any]   # 5 keys, each {score,weight,reason,observed,benchmark,flagged}
    marketplace: dict[str, Any]  # passthrough: sold, rating, positive_pct, price_usdt, tagline
    ambiguous_matches: NotRequired[list[dict[str, str]]]  # collision disclosure (2 real cases)


class CompareResult(TypedDict):
    agents: list[ScoreCard]
    component_winners: dict[str, str | None]   # component -> winning agent_id (None = tie)
    overall_winner: str | None
    generated_at: str
    methodology_url: str
    score_version: str
    data_as_of: str
    disclaimer: str


class CategoryLeaderboard(TypedDict):
    category: str
    entries: list[dict[str, Any]]   # rank, agent_id, name, score, grade, confidence
    total_in_category: int
    generated_at: str
    methodology_url: str
    score_version: str
    data_as_of: str
    disclaimer: str


class MarketplaceStats(TypedDict):
    agents_total: int
    scored: int
    not_rated: int
    grade_distribution: dict[str, int]
    category_counts: dict[str, int]
    median_price_usdt: float | None
    generated_at: str
    methodology_url: str
    score_version: str
    data_as_of: str
    disclaimer: str


# --- Envelope helpers ---------------------------------------------------------

def _methodology_url() -> str:
    """Env-driven base URL, read at CALL time so tests can monkeypatch it."""
    return os.environ.get("TRUSTLENS_BASE_URL", "http://localhost:8000") + "/#methodology"


def _err(payload: dict) -> ToolError:
    """The ONLY error channel: deterministic, neutral, compact JSON."""
    return ToolError(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _not_found_payload(conn: sqlite3.Connection, query: str) -> dict:
    """Neutral not-found body with deterministic prefix-match candidates."""
    closest = db.closest_candidates(conn, query)
    return {
        "error": "not_found",
        "query": query,
        "detail": "no agent matched by id, exact name, or normalized name",
        "candidates": [{"agent_id": r["id"], "name": r["name"]} for r in closest],
        "methodology_url": _methodology_url(),
    }


def _unavailable_payload() -> dict:
    """Deterministic body for an empty scores table (public-knowledge remedy)."""
    return {
        "error": "unavailable",
        "detail": "no scores present — run python -m indexer.refresh",
        "methodology_url": _methodology_url(),
    }


def _internal_payload() -> dict:
    """Neutral body for unexpected failures; the real exception stays server-side."""
    return {
        "error": "internal",
        "detail": "unexpected server error",
        "methodology_url": _methodology_url(),
    }


def _card(row: sqlite3.Row, ambiguous: list[sqlite3.Row]) -> ScoreCard:
    """Build EVERY ScoreCard (scored, NR, collision) from one stored row.

    A single builder guarantees all required keys are always present —
    FastMCP validates returns against the derived outputSchema server-side,
    so a missing key would turn a valid answer into an error (Pitfall 4).
    Timestamps and version come from the STORED row, never the wall clock.
    """
    card: ScoreCard = {
        "agent_id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "score": row["score"],
        "grade": row["grade"],
        "confidence": row["confidence"],
        "score_version": row["score_version"],
        "generated_at": row["generated_at"],
        "data_as_of": row["data_as_of"],
        "methodology_url": _methodology_url(),
        "disclaimer": DISCLAIMER,
        "components": json.loads(row["components"]),
        "marketplace": {
            "sold": row["sold"],
            "rating": row["rating"],
            "positive_pct": row["positive_pct"],
            "price_usdt": row["price_usdt"],
            "tagline": row["tagline"],
        },
    }
    if len(ambiguous) >= 2:
        card["ambiguous_matches"] = [
            {"agent_id": r["id"], "name": r["name"]} for r in ambiguous
        ]
    return card


# --- The 4 tools (MCPS-01: no more, no fewer) ---------------------------------

@mcp.tool
def score_agent(agent_id_or_name: str) -> ScoreCard:
    """Full trust score card for one OKX.AI agent, looked up by id or name."""
    try:
        conn = db.connect_ro()
        try:
            row, ambiguous = db.lookup_agent(conn, agent_id_or_name)
            if row is None:
                raise _err(_not_found_payload(conn, agent_id_or_name))
            return _card(row, ambiguous)
        finally:
            conn.close()
    except ToolError:
        raise
    except Exception:
        _LOG.exception("unexpected error in score_agent")
        raise _err(_internal_payload()) from None


@mcp.tool
def compare_agents(ids: list[str]) -> CompareResult:
    """Score cards plus per-component winners for 2 to 10 agents."""
    try:
        if not 2 <= len(ids) <= 10:
            raise _err({
                "error": "invalid_argument",
                "detail": "ids must contain between 2 and 10 entries",
                "methodology_url": _methodology_url(),
            })
        conn = db.connect_ro()
        try:
            cards: list[ScoreCard] = []
            for query in ids:
                row, ambiguous = db.lookup_agent(conn, query)
                if row is None:
                    raise _err(_not_found_payload(conn, query))
                cards.append(_card(row, ambiguous))
            env = db.envelope_values(conn)
            if env is None:
                raise _err(_unavailable_payload())
        finally:
            conn.close()

        component_winners: dict[str, str | None] = {}
        for key in COMPONENT_KEYS:
            observed = [
                (card["components"][key]["score"], card["agent_id"])
                for card in cards
                if card["components"].get(key, {}).get("score") is not None
            ]
            if not observed:
                component_winners[key] = None
                continue
            best = max(value for value, _ in observed)
            leaders = [aid for value, aid in observed if value == best]
            component_winners[key] = leaders[0] if len(leaders) == 1 else None

        scored = [(c["score"], c["agent_id"]) for c in cards if c["score"] is not None]
        if not scored:
            overall_winner = None
        else:
            top = max(value for value, _ in scored)
            leaders = [aid for value, aid in scored if value == top]
            overall_winner = leaders[0] if len(leaders) == 1 else None

        return {
            "agents": cards,
            "component_winners": component_winners,
            "overall_winner": overall_winner,
            "generated_at": env["generated_at"],
            "methodology_url": _methodology_url(),
            "score_version": env["score_version"],
            "data_as_of": env["data_as_of"],
            "disclaimer": DISCLAIMER,
        }
    except ToolError:
        raise
    except Exception:
        _LOG.exception("unexpected error in compare_agents")
        raise _err(_internal_payload()) from None


@mcp.tool
def category_leaderboard(category: str, limit: int = 10) -> CategoryLeaderboard:
    """Ranked top agents within one of the 9 TrustLens categories.

    Entries cover scored agents only (best score first); total_in_category
    counts every agent in the category, scored and not-rated alike.
    """
    try:
        if category not in CATEGORIES:
            raise _err({
                "error": "invalid_argument",
                "detail": "unknown category",
                "valid_categories": sorted(CATEGORIES),
                "methodology_url": _methodology_url(),
            })
        if not 1 <= limit <= 50:
            raise _err({
                "error": "invalid_argument",
                "detail": "limit must be between 1 and 50",
                "methodology_url": _methodology_url(),
            })
        conn = db.connect_ro()
        try:
            env = db.envelope_values(conn)
            if env is None:
                raise _err(_unavailable_payload())
            rows = db.category_slice(conn, category, limit)
            total = db.category_total(conn, category)
        finally:
            conn.close()

        entries = [
            {
                "rank": rank,
                "agent_id": row["id"],
                "name": row["name"],
                "score": row["score"],
                "grade": row["grade"],
                "confidence": row["confidence"],
            }
            for rank, row in enumerate(rows, start=1)
        ]
        return {
            "category": category,
            "entries": entries,
            "total_in_category": total,
            "generated_at": env["generated_at"],
            "methodology_url": _methodology_url(),
            "score_version": env["score_version"],
            "data_as_of": env["data_as_of"],
            "disclaimer": DISCLAIMER,
        }
    except ToolError:
        raise
    except Exception:
        _LOG.exception("unexpected error in category_leaderboard")
        raise _err(_internal_payload()) from None


@mcp.tool
def marketplace_stats() -> MarketplaceStats:
    """Aggregate marketplace statistics: totals, grade distribution, category counts, median price."""
    try:
        conn = db.connect_ro()
        try:
            env = db.envelope_values(conn)
            if env is None:
                raise _err(_unavailable_payload())
            aggregates = db.stats(conn)
        finally:
            conn.close()

        return {
            "agents_total": aggregates["agents_total"],
            "scored": aggregates["scored"],
            "not_rated": aggregates["not_rated"],
            "grade_distribution": aggregates["grade_distribution"],
            "category_counts": aggregates["category_counts"],
            "median_price_usdt": aggregates["median_price_usdt"],
            "generated_at": env["generated_at"],
            "methodology_url": _methodology_url(),
            "score_version": env["score_version"],
            "data_as_of": env["data_as_of"],
            "disclaimer": DISCLAIMER,
        }
    except ToolError:
        raise
    except Exception:
        _LOG.exception("unexpected error in marketplace_stats")
        raise _err(_internal_payload()) from None
