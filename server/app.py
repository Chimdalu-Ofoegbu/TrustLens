"""TrustLens host app: /healthz + /badge/{id}.svg + /mcp (FastMCP) + static / — one port."""
from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastmcp.utilities.lifespan import combine_lifespans

from server.db import DEFAULT_DB, connect_ro
from server.payments import PaymentConfig, X402Middleware
from server.tools import mcp
from web.badge import badge_svg

log = logging.getLogger("server.app")

# defense-in-depth; real ids are digits. \Z (not $): $ also matches before a
# trailing \n, so "3345\n" would pass and reach the query (WR-01 / T-03-13).
_AGENT_ID = re.compile(r"[A-Za-z0-9_-]{1,32}\Z")
DEFAULT_STATIC = Path("web/dist")

# Fixed 503 body (MCPS-03): same locked field set as the 200 shape, no
# exception text ever serialized (STRIDE T-03-14).
_UNAVAILABLE = {
    "status": "unavailable",
    "agents": 0,
    "scores": 0,
    "score_version": None,
    "data_as_of": None,
}


class McpPathRewrite:
    """starlette>=1.0 Mount matches only /mcp/*; rewrite exact /mcp -> /mcp/ (no 307/405)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
            scope["raw_path"] = b"/mcp/"
        await self.app(scope, receive, send)


def create_app(
    db_path: str | Path = DEFAULT_DB,
    static_dir: str | Path = DEFAULT_STATIC,
    payment_config: PaymentConfig | None = None,
) -> FastAPI:
    """Build the one-port TrustLens app (PoC-verified V3 composition).

    ``db_path``/``static_dir`` exist for test isolation only; the defaults
    preserve the verified behavior. The module-level ``mcp`` tools keep
    reading ``server.db.DEFAULT_DB`` regardless — ``db_path`` parameterizes
    ONLY /healthz and the badge route.

    ``payment_config`` injects the x402 gate config for tests; ``None`` means
    env-derived via ``PaymentConfig.from_env()`` when the middleware stack
    builds at startup (the mode banner and placeholder-payTo warning fire
    there — proven in the live uvicorn log).
    """
    # Orchestrator-locked JSON response mode: plain application/json bodies,
    # still Streamable HTTP (verified Inspector-compatible; NOT the banned
    # legacy SSE transport — this only selects the response format).
    mcp_app = mcp.http_app(path="/", json_response=True)

    @asynccontextmanager
    async def app_lifespan(app):
        # Startup checks WARN (never raise): the server must boot even on an
        # empty checkout so /healthz can report 503 with the remedy known.
        if not Path(db_path).exists():
            log.warning(
                "database missing: %s — run python -m indexer.refresh", db_path
            )
        if not (Path(static_dir) / "index.html").exists():
            log.warning(
                "leaderboard missing: %s — run python -m indexer.refresh",
                Path(static_dir) / "index.html",
            )
        yield

    # Omitting the MCP lifespan is the #1 documented mounting mistake
    # (RuntimeError on every MCP call) — always combine it in.
    app = FastAPI(
        title="TrustLens",
        lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan),
    )

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        """MCPS-03: 200 with counts when scores exist, fixed 503 otherwise.

        Connection-per-request; the ENTIRE body is guarded so this route
        never raises and never leaks exception text (STRIDE T-03-14).
        Phase 4 must keep this route free (never payment-gated).
        """
        try:
            conn = connect_ro(db_path)
            try:
                agents = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
                scores = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
                env = conn.execute(
                    "SELECT score_version, MAX(data_as_of) AS data_as_of"
                    " FROM scores GROUP BY score_version LIMIT 1"
                ).fetchone()
            finally:
                conn.close()
            if scores > 0 and env is not None:
                return JSONResponse(
                    {
                        "status": "ok",
                        "agents": agents,
                        "scores": scores,
                        "score_version": env["score_version"],
                        "data_as_of": env["data_as_of"],
                    }
                )
        except (sqlite3.Error, OSError):
            log.exception("healthz probe failed (returning fixed 503 body)")
        return JSONResponse(status_code=503, content=dict(_UNAVAILABLE))

    @app.get("/badge/{agent_id}.svg")
    def badge(agent_id: str) -> Response:
        """WEB-02: shields-style SVG; unknown ids get a neutral badge, never 404.

        Allowlist regex runs BEFORE any DB touch (STRIDE T-03-13: rejected
        ids never reach a query; the route touches no filesystem at all).
        A DB failure also degrades to the neutral badge — embeds must render.
        """
        svg = badge_svg(None, None)  # neutral "N/A" not-found badge
        if _AGENT_ID.fullmatch(agent_id):
            try:
                conn = connect_ro(db_path)
                try:
                    row = conn.execute(
                        "SELECT grade, score FROM scores WHERE agent_id = ?",
                        (agent_id,),
                    ).fetchone()
                finally:
                    conn.close()
                if row is not None:
                    svg = badge_svg(row["grade"], row["score"])
            except (sqlite3.Error, OSError):
                log.exception("badge lookup failed for %r (serving neutral badge)", agent_id)
        return Response(
            content=svg,
            media_type="image/svg+xml",
            headers={"Cache-Control": "max-age=3600"},
        )

    # Locked route order: healthz/badge registered above, /mcp mount next,
    # static at / LAST (Starlette matches in registration order — a catch-all
    # static mount registered earlier would shadow everything).
    Path(static_dir).mkdir(parents=True, exist_ok=True)
    app.mount("/mcp", mcp_app)
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="site")

    # Middleware always runs before routing, so adding after mounts is fine.
    # add_middleware is LIFO: X402Middleware, registered AFTER McpPathRewrite,
    # runs OUTERMOST and therefore sees RAW paths — both /mcp and /mcp/. Its
    # prefix predicate (path == "/mcp" or path.startswith("/mcp/")) is what
    # makes the bare OKX pre-registration curl (POST /mcp, no body) answer
    # 402; an exact-match gate provably fails it with 400 (04-RESEARCH
    # negative proof). Kwargs pass through Starlette to X402Middleware.__init__.
    app.add_middleware(McpPathRewrite)
    app.add_middleware(X402Middleware, config=payment_config)
    return app
