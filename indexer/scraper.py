"""Polite okx.ai enrichment scraper. Offline CLI tier only — NEVER request-path.

INDX-04. Behind `python -m indexer.refresh --scrape` (off by default so the
whole suite and Docker self-seed stay offline/deterministic). The SOLE
guaranteed behaviour is graceful degradation: every failure mode (403/5xx,
timeout/network error, missing appState script, JSON error, missing keys,
field cast miss) logs exactly one WARNING and returns None/[], never raises.
When the scraper yields nothing usable the census rows stand unchanged.

okx.ai already ships a fully-populated `appState` JSON island in its SSR HTML
(verified 2026-07-11, 05-RESEARCH.md), so extraction is `json.loads`, not
brittle DOM-selector scraping. The parser reads
`data["appContext"]["initialProps"]["AgentDetailPage"]["overview"]` and casts
each field into the existing AgentRecord contract.

Category decision (Option B, locked 05-RESEARCH.md): okx.ai's 6-code category
set has ZERO overlap with the derived 9-bucket CANONICAL_CATEGORIES, so the
scraper enriches ONLY sold/rating/price/positive_pct and leaves `category`
DERIVED (category_source stays "derived"). A raw scraped code must never reach
a reason string (scoring/components.py refuses non-canonical category text).

Politeness (hard contract, all locked): ≤1 req/sec sleep-between network hits,
User-Agent TrustLens/1.0, on-disk cache under data/cache/ (gitignored; cache
hit = zero network, zero sleep), 15s hard timeout, single attempt (no retries).

Security: scraped appState is UNTRUSTED third-party input — every field cast is
wrapped (V5); logs use %r for url/id/name (log-injection + cp1252-console safe,
V7); cache filename is sha256(url) only, no user-controlled path segment (V12);
detail URLs are built from a fixed DEMO_AGENT_IDS set, ids constrained to ^\\d+$
if ever non-literal (V13/SSRF). No new dependency; httpx + bs4 are already pinned.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from indexer.category import derive_category
from indexer.models import AgentRecord
from indexer.parse import name_key

log = logging.getLogger("indexer.scraper")

__all__ = [
    "UA",
    "CACHE_DIR",
    "RATE_S",
    "TIMEOUT_S",
    "BASE",
    "DEMO_AGENT_IDS",
    "detail_url",
    "fetch",
    "parse_appstate",
    "scrape_agents",
]

UA = "TrustLens/1.0"
CACHE_DIR = Path("data/cache")     # already gitignored
RATE_S = 1.1                       # > 1 req/sec: sleep BETWEEN network fetches
TIMEOUT_S = 15.0
BASE = "https://www.okx.ai"

# Bounded demo set — the mechanism proof. A full 305/272-page crawl at 1 req/s
# is ~5 min and is a v2/INDX-05 concern; refresh must never block on it.
DEMO_AGENT_IDS: tuple[str, ...] = ("3345",)

_AGENT_ID = re.compile(r"^\d+$")   # V13: constrain any non-literal id before URL build


def detail_url(agent_id: str) -> str:
    """Build the okx.ai detail URL for an agent id.

    URLs are hardcoded to the okx.ai host; the id is the only variable and is
    constrained to digits so a non-literal id can never redirect the fetch to
    another host (SSRF, V13). The fixed DEMO_AGENT_IDS already satisfy this.
    """
    if not _AGENT_ID.fullmatch(str(agent_id)):
        raise ValueError(f"refusing non-numeric agent id {agent_id!r}")
    return f"{BASE}/agents/{agent_id}"


def _cache_path(url: str) -> Path:
    """data/cache/<sha256(url)>.html — sha256-of-URL is the ONLY path component.

    No user-controlled segment ever reaches the filesystem path, so a hostile
    URL cannot traverse out of the cache directory (V12).
    """
    return CACHE_DIR / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".html")


def fetch(client: httpx.Client, url: str, *, _pacer: list | None = None) -> str | None:
    """Cache-first polite GET. Returns the HTML body, or None + one WARNING.

    Control flow (locked, 05-RESEARCH Pattern 1):
    - cache hit -> return cached text with NO network and NO sleep.
    - politeness -> if a prior network fetch happened this run, sleep RATE_S
      BEFORE the request (the mutable _pacer records prior fetches so the very
      first network call does not sleep).
    - single attempt, hard timeout, no retries. Any httpx.HTTPError (timeout,
      connect error, ...) -> WARNING + None; never propagates.
    - non-200 (covers 403/5xx) -> WARNING + None.
    - 200 -> write the body under data/cache/ and return it.
    """
    pacer = _pacer if _pacer is not None else []
    p = _cache_path(url)
    if p.is_file():
        return p.read_text(encoding="utf-8")     # cache hit: no network, no sleep

    if pacer:                                    # politeness: sleep BETWEEN network calls
        time.sleep(RATE_S)
    pacer.append(url)

    try:
        r = client.get(url, timeout=TIMEOUT_S)   # single attempt, no retries
    except httpx.HTTPError as exc:
        log.warning("fetch failed url=%r: %s", url, exc.__class__.__name__)
        return None
    if r.status_code != 200:
        log.warning("fetch non-200 url=%r status=%d", url, r.status_code)
        return None                              # 403/5xx -> census fallback

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(r.text, encoding="utf-8")
    return r.text


def parse_appstate(html: str, url: str) -> AgentRecord | None:
    """Extract one AgentRecord from the appState JSON island, or None + WARNING.

    Three guarded stages (05-RESEARCH Pattern 2), each a soft parse-miss:
    1. locate the `appState` script (missing/empty -> SPA or markup change);
    2. json.loads + drill to overview (JSON error or missing key);
    3. cast every field per the verified mapping (bad value -> ValueError).

    Category stays DERIVED (Option B): derive_category from name+description,
    category_source keeps the AgentRecord default. A hostile/oversized numeric
    string yields a soft miss (None+WARNING), never a crash or poisoned record.
    """
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", attrs={"id": "appState", "type": "application/json"})
    if tag is None or not tag.string:
        log.warning("no appState script url=%r (SPA/markup change)", url)
        return None

    try:
        data = json.loads(tag.string)
        ov = data["appContext"]["initialProps"]["AgentDetailPage"]["overview"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        log.warning("appState parse miss url=%r: %s", url, exc.__class__.__name__)
        return None

    try:
        score = ov.get("score")
        rating = float(score) if score and float(score) > 0 else None
        approval = ov.get("approvalRate")
        fee = ov.get("serviceLowestFee")
        return AgentRecord(
            id=str(ov["agentId"]),
            name=ov["name"],
            name_key=name_key(ov["name"]),
            # Option B: keep category DERIVED — never store the raw okx.ai code.
            category=derive_category(ov["name"], ov.get("description", "")),
            tagline=ov.get("description", ""),
            price_usdt=float(fee) if fee else None,
            price_raw=str(fee) if fee else "",
            sold=int(ov.get("usageCount", 0)),
            rating=rating,
            # WR-01: coerce to str before rstrip so a numeric approvalRate
            # (e.g. 100, a plausible marketplace-JSON drift) parses instead of
            # raising AttributeError; None/"" stay absent, 0 stays 0.0.
            positive_pct=(
                float(str(approval).rstrip("%"))
                if approval not in (None, "")
                else None
            ),
        )
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        log.warning("appState field cast miss url=%r: %s", url, exc.__class__.__name__)
        return None


def scrape_agents(urls, *, client: httpx.Client | None = None) -> list[AgentRecord]:
    """Fetch + parse a bounded set of detail URLs. Returns records (possibly []).

    THE graceful-degradation guarantee: nothing escapes this function. Any
    per-url failure is already softened to None by fetch/parse_appstate, and
    the whole loop is additionally wrapped so an unexpected error still yields
    a partial-or-empty list instead of propagating into refresh's exit contract.

    Owns a polite httpx.Client (UA TrustLens/1.0, follow_redirects) unless one
    is injected (tests inject a MockTransport client). A scraped record's
    category_source stays "derived".
    """
    own = client is None
    if own:
        client = httpx.Client(headers={"User-Agent": UA}, follow_redirects=True)
    records: list[AgentRecord] = []
    pacer: list = []
    try:
        for url in urls:
            try:
                html = fetch(client, url, _pacer=pacer)
                if html is None:
                    continue
                rec = parse_appstate(html, url)
                if rec is not None:
                    records.append(rec)
            except Exception as exc:  # last-resort belt: a scrape can never crash refresh
                log.warning("scrape error url=%r: %s", url, exc.__class__.__name__)
                continue
    finally:
        if own:
            client.close()
    return records
