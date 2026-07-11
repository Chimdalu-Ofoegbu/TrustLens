"""Leaderboard page contract tests (WEB-01/WEB-02, 03-UI-SPEC.md).

Pins the rendered page against the approved design contract: 272 ranked rows
(scored desc, NR after, id-asc ties), exact copywriting strings, methodology
content, filter/sort DOM hooks, self-containment, byte determinism, hostile
marketplace text neutralized by escaping (STRIDE T-03-01), and the banned
vocabulary source scan extended over web/build.py (mirror of the
tests/test_scoring_golden.py pattern).

All builds write into pytest tmp dirs only — never into the repo
(research Pitfall 7).
"""
import hashlib
import html as html_mod
import re
from pathlib import Path

import pytest

from indexer.db import connect, init_db, upsert_agent
from indexer.models import AgentRecord
from indexer.refresh import refresh
from scoring import DISCLAIMER, GRADE_DESCRIPTIONS
from web.build import build

REPO_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = REPO_ROOT / "data" / "okx-marketplace-census-2026-07-10.csv"
BUILD_SOURCE = REPO_ROOT / "web" / "build.py"
SEED_TS = "2026-07-10T00:00:00Z"
# The regex literal lives here in tests/, outside the scanned tree.
BANNED = re.compile(r"(?i)(fraud|scam|fake|manipulat)")

TOTAL = 272
SCORED = 121
NOT_RATED = 151

# First <td> of each agent row is the rank cell.
ROW_RANK = re.compile(r'<tr id="agent-[^"]*"><td class="num" data-v="[^"]*">([^<]*)</td>')


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    """Build once from the REAL census into a tmp dir; all content tests share it."""
    d = tmp_path_factory.mktemp("web")
    refresh(CSV_PATH, d / "t.db", SEED_TS)  # library call — writes no page (build wired into refresh in plan 03-03)
    out = d / "index.html"
    build(d / "t.db", out)
    return out.read_text(encoding="utf-8"), out


# --- 1. row count + ordering (WEB-01 locked ordering) --------------------------


def test_row_count_and_rank_ordering(page):
    html, _ = page
    assert html.count('<tr id="agent-') == TOTAL
    ranks = ROW_RANK.findall(html)
    assert len(ranks) == TOTAL
    assert ranks == [str(i) for i in range(1, SCORED + 1)] + ["—"] * NOT_RATED


# --- 2. anchors + headings (success-criterion strings) -------------------------


def test_anchors_and_headings(page):
    html, _ = page
    assert 'id="methodology"' in html
    assert ">About the methodology<" in html
    assert 'id="badge"' in html
    assert ">TrustLens Verified badge<" in html


# --- 3. badge embed block (WEB-02) ---------------------------------------------


def test_badge_embed_block(page):
    html, _ = page
    assert "/badge/AGENT_ID.svg" in html
    assert "#agent-AGENT_ID" in html
    assert "Replace AGENT_ID with your agent's id from the table above." in html
    assert 'id="snippet-html"' in html
    assert 'id="snippet-md"' in html
    assert 'viewBox="0 0 110 20"' in html  # live inline example badge


# --- 4. copywriting contract strings verbatim ----------------------------------


def test_copywriting_contract_strings(page):
    html, _ = page
    assert "Evidence-based trust scores for OKX.AI marketplace agents" in html
    assert "272 agents · data as of 2026-07-10 · methodology v1.0.0" in html
    assert (
        "NR = Not Rated — insufficient transaction or review evidence to score."
        in html
    )
    assert "4 MCP tools at /mcp" in html
    assert "No agents match this filter." in html
    # DISCLAIMER contains no escapable characters, so the raw constant appears
    # verbatim in both the methodology section and the footer.
    assert html_mod.escape(DISCLAIMER) == DISCLAIMER
    assert html.count(DISCLAIMER) >= 2


# --- 5. methodology content ------------------------------------------------------


def test_methodology_content(page):
    html, _ = page
    for grade, meaning in GRADE_DESCRIPTIONS.items():
        assert meaning in html, grade
    assert "renormalized rather than guessed" in html
    assert "OKX.AI does not publish agent categories" in html
    for weight in ("30%", "25%", "20%", "15%", "10%"):
        assert weight in html


# --- 6. filter/sort DOM hooks ------------------------------------------------------


def test_filter_and_sort_dom_hooks(page):
    html, _ = page
    assert '<select id="cat"' in html
    assert html.count("<option") == 10  # All categories + the 9 buckets
    creative = html_mod.escape("Creative & Media")
    trading = html_mod.escape("Trading & DeFi")
    assert creative in html and trading in html
    assert html.index(creative) < html.index(trading)  # alphabetical order
    assert 'aria-live="polite"' in html
    assert 'data-k="score"' in html
    assert "aria-sort" in html  # set by the inline sort script
    assert html.count('<th scope="col"') == 9
    assert html.count('data-v="') >= TOTAL * 6  # sortable cells carry raw values


# --- 7. CJK + formatting facts (research-verified census edges) ----------------------


def test_cjk_and_number_formatting_edges(page):
    html, _ = page
    assert "这个能吃吗？" in html            # CJK agent name renders as text
    assert "0.000015" in html               # subscript-price edge case, fixed decimal
    assert "1,550" in html                  # 1.55K-sold edge case, thousands separator
    assert "e-05" not in html               # never scientific notation
    assert "e-06" not in html


# --- 8. self-containment (WEB-01 "no external requests") -------------------------------


def test_self_contained_no_external_requests(page):
    html, _ = page
    assert "<link" not in html
    assert "<script src" not in html
    assert "@import" not in html
    assert "url(http" not in html
    assert "fonts.googleapis" not in html


# --- 9. determinism ----------------------------------------------------------------------


def test_build_is_byte_deterministic(page, tmp_path):
    _, out = page
    db_path = out.parent / "t.db"
    first = tmp_path / "a.html"
    second = tmp_path / "b.html"
    build(db_path, first)
    build(db_path, second)
    digest_a = hashlib.sha256(first.read_bytes()).hexdigest()
    digest_b = hashlib.sha256(second.read_bytes()).hexdigest()
    assert digest_a == digest_b
    assert first.read_bytes() == out.read_bytes()  # and identical to the fixture build


# --- 10. XSS hostile fixture (STRIDE T-03-01 proof) -----------------------------------------


def test_hostile_marketplace_text_is_neutralized(tmp_path):
    db_path = tmp_path / "hostile.db"
    conn = connect(db_path)
    try:
        init_db(conn)
        record = AgentRecord(
            id="9001",
            name='<script>alert(1)</script>"onmouseover=',
            name_key="x",
            category="Other Services",
            category_source="derived",
            tagline='multi\nline "quoted" & <b>tag</b>',
            price_usdt=1.0,
            price_raw="1",
            sold=10,
            rating=4.0,
            positive_pct=90.0,
        )
        with conn:
            upsert_agent(conn, record, SEED_TS)
            conn.execute(
                "INSERT INTO scores VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("9001", 50, "C", "medium", "1.0.0", SEED_TS, SEED_TS, "{}"),
            )
    finally:
        conn.close()

    out = tmp_path / "hostile.html"
    build(db_path, out)
    html = out.read_text(encoding="utf-8")

    assert "<script>alert" not in html          # never live markup
    assert "&lt;script&gt;alert" in html        # rendered as escaped text
    assert '"onmouseover' not in html           # can never terminate an attribute
    assert "&quot;onmouseover" in html          # the escaped form is present


# --- 11. banned vocabulary (UI-SPEC hard constraint — source scan) ----------------------------
# Scans web/build.py SOURCE, not the rendered page: real marketplace taglines
# may legitimately contain these words as quoted third-party data; the rule
# covers OUR copy/template strings, which all live in build.py.


def test_banned_vocabulary_absent_from_build_source():
    assert not BANNED.search(BUILD_SOURCE.read_text(encoding="utf-8"))


# --- 12. weight budget (UI-SPEC performance budget) --------------------------------------------


def test_page_weight_within_budget(page):
    _, out = page
    assert out.stat().st_size <= 300 * 1024
