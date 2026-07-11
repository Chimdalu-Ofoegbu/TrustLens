"""Canned-response tests for the polite okx.ai scraper (INDX-04 / OPS-03).

OFFLINE ONLY — the suite NEVER constructs a real httpx.Client against okx.ai.
Every network path is exercised through saved HTML fixtures + httpx.MockTransport.
Covers the 05-RESEARCH "Test Fixtures" table: the real-shape success parse and
all six graceful-degradation modes (403/5xx, timeout, empty-SPA, changed-markup,
missing-keys, zero-score-unrated), plus merge semantics, the exit-code invariant
(a total scrape failure keeps refresh at exit 0 with 272 census rows), and the
offline rule (no server/* module imports the scraper).

Run the subset with `python -m pytest tests/test_scraper.py --no-cov`
(the --cov=scoring gate reports 0% on a scraper-only run — 05-RESEARCH Pitfall 3).
"""
import logging
import sqlite3
from pathlib import Path

import httpx
import pytest

from indexer.models import AgentRecord
from indexer.scraper import (
    _cache_path,
    detail_url,
    fetch,
    parse_appstate,
    scrape_agents,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CSV_PATH = REPO_ROOT / "data" / "okx-marketplace-census-2026-07-10.csv"
SEED_TS = "2026-07-10T00:00:00Z"

URL_3345 = "https://www.okx.ai/agents/3345"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _mock_client(handler) -> httpx.Client:
    """An httpx.Client whose transport is a MockTransport — never hits network."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def _agent(id_: str, sold: int = 0) -> AgentRecord:
    """A minimal census-style record for merge tests (category stays derived)."""
    return AgentRecord(
        id=id_, name=f"Agent {id_}", name_key=f"agent {id_}", category="Other Services",
        tagline="", price_usdt=None, price_raw="", sold=sold, rating=None,
        positive_pct=None,
    )


# --- 1. success parse over the real-shape saved page -------------------------

def test_parse_success_real_page():
    rec = parse_appstate(_read("okx_detail_3345.html"), URL_3345)
    assert rec is not None
    assert rec.id == "3345"
    assert rec.sold == 539
    assert rec.rating == 5.0
    assert rec.price_usdt == 0.01
    assert rec.price_raw == "0.01"
    assert rec.positive_pct == 100.0
    # Option B: the scraper never overwrites category with the raw okx.ai code.
    assert rec.category_source == "derived"
    assert rec.category in {  # derived from listing text, not "LIFESTYLE"
        "Security & Trust", "Sports & Prediction", "Lifestyle & Health",
        "Creative & Media", "Social & News", "Developer Tools & Infra",
        "Trading & DeFi", "Market Data & Analytics", "Other Services",
    }
    # CJK name round-trips exactly through UTF-8 fixture + parse.
    assert rec.name == "这个能吃吗？"


# --- 2. degradation modes: each returns None + exactly one WARNING ------------

@pytest.mark.parametrize("fixture", [
    "okx_detail_empty_spa.html",
    "okx_detail_changed_markup.html",
    "okx_detail_missing_keys.html",
])
def test_parse_degradation_returns_none_with_warning(fixture, caplog):
    with caplog.at_level(logging.WARNING, logger="indexer.scraper"):
        rec = parse_appstate(_read(fixture), URL_3345)
    assert rec is None
    warnings = [r for r in caplog.records
                if r.name == "indexer.scraper" and r.levelno == logging.WARNING]
    assert len(warnings) == 1
    # Log hygiene: the url is rendered, no traceback/raw body leaks.
    assert "\n" not in warnings[0].getMessage()


def test_parse_truncated_json_returns_none(caplog):
    # appState present but the JSON is truncated -> JSONDecodeError caught.
    broken = '<script id="appState" type="application/json">{"appContext":{"init</script>'
    with caplog.at_level(logging.WARNING, logger="indexer.scraper"):
        rec = parse_appstate(broken, URL_3345)
    assert rec is None
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_parse_zero_score_is_unrated():
    # score "0.0" must yield rating None (the unrated rule), never 0.0.
    html = (
        '<script id="appState" type="application/json">'
        '{"appContext":{"initialProps":{"AgentDetailPage":{"overview":'
        '{"agentId":"9","name":"Z","score":"0.0","approvalRate":"100%",'
        '"usageCount":3,"serviceLowestFee":"0.01"}}}}}</script>'
    )
    rec = parse_appstate(html, URL_3345)
    assert rec is not None
    assert rec.rating is None
    assert rec.sold == 3


# --- 3. fetch degradation: 403 and timeout, no exception escapes --------------

def test_fetch_403_returns_none_warning(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr("indexer.scraper.CACHE_DIR", tmp_path)  # never touch repo cache
    client = _mock_client(lambda req: httpx.Response(403))
    try:
        with caplog.at_level(logging.WARNING, logger="indexer.scraper"):
            out = fetch(client, URL_3345)
    finally:
        client.close()
    assert out is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "403" in warnings[0].getMessage()


def test_fetch_timeout_returns_none_warning(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr("indexer.scraper.CACHE_DIR", tmp_path)

    def _boom(req):
        raise httpx.ConnectTimeout("boom")

    client = _mock_client(_boom)
    try:
        with caplog.at_level(logging.WARNING, logger="indexer.scraper"):
            out = fetch(client, URL_3345)  # must NOT raise httpx.HTTPError
    finally:
        client.close()
    assert out is None
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_fetch_cache_hit_no_network(tmp_path, monkeypatch):
    # A pre-written cache file is served with zero network + zero sleep.
    monkeypatch.setattr("indexer.scraper.CACHE_DIR", tmp_path)
    monkeypatch.setattr(
        "indexer.scraper.time.sleep",
        lambda *_: (_ for _ in ()).throw(AssertionError("slept on a cache hit")),
    )
    p = _cache_path(URL_3345)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("<html>cached</html>", encoding="utf-8")

    called = []
    client = _mock_client(lambda req: called.append(req) or httpx.Response(200))
    try:
        out = fetch(client, URL_3345)
    finally:
        client.close()
    assert out == "<html>cached</html>"
    assert called == []  # transport handler was never invoked


def test_fetch_200_writes_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("indexer.scraper.CACHE_DIR", tmp_path)
    body = _read("okx_detail_3345.html")
    client = _mock_client(lambda req: httpx.Response(200, text=body))
    try:
        out = fetch(client, URL_3345)
    finally:
        client.close()
    assert out == body
    assert _cache_path(URL_3345).is_file()  # body was cached under the sha256 name


# --- 4. merge: census is the floor, scrape wins per-id -----------------------

def test_merge_scrape_wins_census_floor():
    from indexer.refresh import merge

    census = [_agent("A", sold=1), _agent("B", sold=2)]
    scraped = [_agent("B", sold=99)]  # fresher B
    out = {r.id: r for r in merge(census, scraped)}
    assert len(out) == 2
    assert out["A"].sold == 1        # census-only id stands
    assert out["B"].sold == 99       # scrape wins for the id it parsed


def test_merge_scrape_adds_new_id():
    from indexer.refresh import merge

    out = {r.id: r for r in merge([_agent("A")], [_agent("C", sold=7)])}
    assert set(out) == {"A", "C"}
    assert out["C"].sold == 7


# --- 5. scrape_agents swallows everything -> [] ------------------------------

def test_scrape_agents_all_403_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("indexer.scraper.CACHE_DIR", tmp_path)
    client = _mock_client(lambda req: httpx.Response(403))
    try:
        out = scrape_agents([URL_3345, "https://www.okx.ai/agents/9999"], client=client)
    finally:
        client.close()
    assert out == []  # never raises, always a list


def test_scrape_agents_success_returns_record(tmp_path, monkeypatch):
    monkeypatch.setattr("indexer.scraper.CACHE_DIR", tmp_path)
    body = _read("okx_detail_3345.html")
    client = _mock_client(lambda req: httpx.Response(200, text=body))
    try:
        out = scrape_agents([URL_3345], client=client)
    finally:
        client.close()
    assert len(out) == 1
    assert out[0].id == "3345"
    assert out[0].category_source == "derived"


def test_detail_url_rejects_non_numeric_id():
    # V13/SSRF guard: a non-numeric id can never build a fetch URL.
    assert detail_url("3345") == URL_3345
    with pytest.raises(ValueError):
        detail_url("../evil")


# --- 6. THE Pitfall-1 guard: scrape failure never changes the exit code ------

def test_refresh_scrape_all_403_still_exits_0_with_census(tmp_path, monkeypatch):
    """--scrape with a total scrape failure -> exit 0, 272 census rows intact.

    scrape_agents is imported locally inside refresh.main(); patching the source
    name (indexer.scraper.scrape_agents) to return [] simulates every URL 403ing
    (scrape_agents already swallows that to []) without any network.
    """
    from indexer import refresh

    monkeypatch.setattr("indexer.scraper.scrape_agents", lambda *a, **k: [])
    db = tmp_path / "scrape.db"
    rc = refresh.main([
        "--scrape",
        "--csv", str(CSV_PATH),
        "--db", str(db),
        "--captured-at", SEED_TS,
        "--web-out", str(tmp_path / "index.html"),
    ])
    assert rc == 0
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0] == 272
        # Default provenance is preserved: the merged batch persists as census.
        assert conn.execute(
            "SELECT COUNT(*) FROM snapshots WHERE source != 'census'"
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_refresh_no_scrape_flag_unchanged(tmp_path):
    # Sanity: the default path (no --scrape) still exits 0 with 272 rows.
    from indexer import refresh

    db = tmp_path / "plain.db"
    rc = refresh.main([
        "--csv", str(CSV_PATH), "--db", str(db), "--captured-at", SEED_TS,
        "--web-out", str(tmp_path / "index.html"),
    ])
    assert rc == 0
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0] == 272
    finally:
        conn.close()


# --- 7. offline rule: no server/* module imports the scraper -----------------

def test_no_server_module_imports_scraper():
    server_dir = REPO_ROOT / "server"
    offenders = []
    for py in server_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if "indexer.scraper" in text or "import scraper" in text:
            offenders.append(py.name)
    assert offenders == [], f"scraper is offline-only; imported under server/: {offenders}"
