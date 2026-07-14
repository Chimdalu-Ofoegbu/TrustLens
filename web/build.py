"""Leaderboard page builder: SQLite -> one self-contained HTML file (WEB-01/02).

Build-time module rendering the approved 03-UI-SPEC.md contract with stdlib
templating only: ONE string.Template for the page plus a str.format row
template. The template body contains no literal "$" outside placeholders, so
Template.substitute doubles as a guard against stray placeholders (the inline
CSS and JS are written entirely without "$").

Security posture (STRIDE T-03-01): agent names and taglines are
attacker-influenced marketplace text (quotes, angle brackets, CJK, embedded
newlines). EVERY DB-sourced string is passed through html.escape — text nodes
and attribute values alike — before it reaches the page. Numbers are formatted
in Python and never in JS, keeping the output byte-deterministic.

Neutral vocabulary: all copy comes verbatim from the UI-SPEC Copywriting
Contract; the banned-word source scan in tests/test_web_build.py covers this
file.
"""
from __future__ import annotations

import html
import sqlite3
from pathlib import Path
from string import Template

from indexer.category import CATEGORIES
from scoring import DISCLAIMER, GRADE_BANDS, GRADE_DESCRIPTIONS, SCORE_VERSION, WEIGHTS
from web.badge import badge_svg

__all__ = ["build"]

_EM_DASH = "—"  # missing-value placeholder (UI-SPEC Table Contract)
_EN_DASH = "–"  # numeric ranges in the grade bands table

# Ranked query (research-verbatim): scored rows by score desc, NR rows after
# all scored rows, every tie broken by agent id asc — deterministic order.
_QUERY = """
SELECT a.id, a.name, a.category, a.tagline, a.price_usdt, a.sold, a.rating,
       s.score, s.grade, s.confidence, s.score_version, s.data_as_of
FROM agents a JOIN scores s ON s.agent_id = a.id
ORDER BY (s.score IS NULL), s.score DESC, a.id
"""

# Sort ordinals carried in data-v (UI-SPEC Table Contract): grade A..F map to
# 5..1, NR to empty (empty always sorts last); confidence high/medium/low map
# to 3/2/1. Unknown values fall back to empty = sorts last.
_GRADE_ORDINAL = {"A": "5", "B": "4", "C": "3", "D": "2", "F": "1", "NR": ""}
_CONFIDENCE_ORDINAL = {"high": "3", "medium": "2", "low": "1"}
_GRADE_CLASS = {"A": "a", "B": "b", "C": "c", "D": "d", "F": "f", "NR": "nr"}

# Methodology components table (UI-SPEC Copywriting Contract, block 2):
# display order is fixed by the contract; weights come from scoring.WEIGHTS.
_COMPONENT_DISPLAY = (
    ("sales_volume_velocity", "Sales volume & velocity",
     "units sold and growth across observed snapshots"),
    ("rating_credibility", "Rating credibility",
     "whether the displayed rating is supported by enough transactions"),
    ("review_signal_ratio", "Review signal ratio",
     "review and positive-percentage signal relative to units sold and category norms"),
    ("price_vs_category", "Price vs category",
     "price position within the agent's category (percentile)"),
    ("listing_age_consistency", "Listing age & consistency",
     "how long and how consistently the listing has been observed"),
)

# One row per agent, rendered via str.format (values pre-escaped/pre-formatted
# in Python — .format never re-processes braces inside substituted values).
_ROW = (
    '<tr id="agent-{aid}">'
    '<td class="num" data-v="{rank_v}">{rank}</td>'
    '<td class="c-agent" data-v="{name_v}" title="{tagline_v}">{name}</td>'
    '<td data-v="{cat_v}">{cat}</td>'
    '<td class="num" data-v="{score_v}">{score}</td>'
    '<td class="ctr" data-v="{grade_v}"><span class="chip chip-{grade_cls}">{grade}</span></td>'
    '<td class="conf" data-v="{conf_v}">{conf}</td>'
    '<td class="num" data-v="{sold_v}">{sold}</td>'
    '<td class="num" data-v="{rating_v}">{rating}</td>'
    '<td class="num" data-v="{price_v}">{price}</td>'
    "</tr>"
)

# The page template. Placeholders only — NO other "$" may appear anywhere in
# this string (Pitfall 6: Template.substitute raises on stray "$"; the inline
# JS below is deliberately written without "$" — no template literals, no
# jQuery-style helpers).
_PAGE = Template("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TrustLens — Evidence-based trust scores for OKX.AI marketplace agents</title>
<style>
/* TrustLens leaderboard — strict Bauhaus: primary triad, flat surfaces, thin
   black keylines, geometric masthead, lowercase display, mono numerals. System
   fonts only (no external requests); numbers are formatted in Python so output
   stays byte-deterministic. */
:root {
  --paper: #F2EFE6;
  --ink: #111111;
  --white: #FFFFFF;
  --red: #E1352A;
  --blue: #1F49C9;
  --green: #17A15A;
  --yellow: #F5C400;
  --orange: #F5871F;
  --muted: #6E6858;
  --line: #E6E1D3;
  --bd: 1.5px solid var(--ink);
  --bd1: 1px solid var(--ink);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: "Helvetica Neue", Helvetica, Arial, "Segoe UI", Roboto, system-ui, "Noto Sans", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
  font-size: 16px;
  line-height: 1.55;
  font-weight: 400;
  -webkit-font-smoothing: antialiased;
}
body::before {
  content: "";
  display: block;
  height: 8px;
  background: linear-gradient(90deg, var(--red) 0 33.34%, var(--yellow) 33.34% 66.67%, var(--blue) 66.67% 100%);
}
.container { max-width: 1160px; margin: 0 auto; padding: 0 24px; }
a { color: var(--blue); text-decoration: none; font-weight: 600; border-bottom: 2px solid var(--blue); }
a:hover { color: var(--ink); border-bottom-color: var(--ink); }
a:focus-visible, button:focus-visible, select:focus-visible { outline: 3px solid var(--blue); outline-offset: 2px; }
h1 { font-size: 44px; line-height: 1; font-weight: 800; margin: 0; letter-spacing: -1.6px; text-transform: lowercase; }
h2 { font-size: 22px; line-height: 1.1; font-weight: 800; margin: 0 0 16px; text-transform: lowercase; letter-spacing: -0.5px; display: flex; align-items: center; gap: 10px; }
h2::before { content: ""; width: 14px; height: 14px; background: var(--blue); display: inline-block; flex: none; }
#methodology h2::before { background: var(--red); }
p { margin: 0 0 14px; }
header { position: relative; padding: 40px 0 16px; margin-bottom: 4px; border-bottom: 3px solid var(--ink); }
header::after { content: ""; position: absolute; left: 0; bottom: -7px; width: 12px; height: 12px; background: var(--red); }
.triad { display: block; margin: 0 0 14px; }
.wm-t { color: var(--ink); }
.wm-l { color: var(--blue); }
.subtitle { margin: 12px 0 0; font-weight: 500; font-size: 16px; color: #33312A; }
.credibility { margin: 8px 0 0; color: var(--muted); font-size: 12px; line-height: 1.4; font-weight: 500; font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace; letter-spacing: 0.02em; }
.site-nav { margin-top: 14px; font-size: 13px; }
.controls { margin-top: 32px; }
.controls-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.controls-row label { font-weight: 700; text-transform: lowercase; letter-spacing: 0.02em; font-size: 13px; }
select {
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
  color: var(--ink);
  background-color: var(--white);
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='11' height='7' viewBox='0 0 11 7'><path d='M0 0h11L5.5 7z' fill='%23111111'/></svg>");
  background-repeat: no-repeat;
  background-position: right 12px center;
  border: var(--bd);
  border-radius: 0;
  padding: 8px 34px 8px 12px;
  cursor: pointer;
  -webkit-appearance: none;
  -moz-appearance: none;
  appearance: none;
}
select:hover { background-color: var(--yellow); }
#count { margin-left: 4px; color: var(--muted); font-size: 12px; line-height: 1.4; font-weight: 500; font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace; letter-spacing: 0.02em; }
.search-row { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
.search-row label { font-weight: 700; text-transform: lowercase; letter-spacing: 0.02em; font-size: 13px; }
#q { font: inherit; font-size: 13px; font-weight: 600; color: var(--ink); background: var(--white); border: var(--bd); border-radius: 0; padding: 7px 11px; width: 300px; max-width: 100%; }
#q::placeholder { color: var(--muted); font-weight: 500; }
#q:focus-visible { outline: 3px solid var(--blue); outline-offset: 2px; }
.nr-legend { margin: 14px 0 0; color: #3A372F; font-size: 13px; line-height: 1.5; font-weight: 500; background: var(--white); border: var(--bd1); border-left: 4px solid var(--yellow); padding: 8px 12px; display: inline-block; }
.table-card {
  margin-top: 24px;
  background: var(--white);
  border: var(--bd);
  border-radius: 0;
  overflow-x: auto;
}
table { width: 100%; min-width: 960px; border-collapse: collapse; font-size: 14px; line-height: 1.4; }
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}
thead th {
  position: sticky;
  top: 0;
  background: var(--ink);
  color: var(--white);
  z-index: 1;
  border-bottom: var(--bd);
  white-space: nowrap;
}
thead th:hover { background: #262626; }
th, td { padding: 9px 13px; text-align: left; }
th button {
  font: inherit;
  font-weight: 700;
  text-transform: lowercase;
  letter-spacing: 0.02em;
  color: var(--white);
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
}
th button.sorted { color: var(--yellow); }
.arrow { color: var(--yellow); font-weight: 800; }
.num { text-align: right; font-variant-numeric: tabular-nums; font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace; }
.ctr { text-align: center; }
.c-agent { max-width: 280px; font-weight: 600; }
.conf { color: var(--muted); font-weight: 500; text-transform: lowercase; font-size: 12px; }
tbody tr { border-bottom: 1px solid var(--line); }
tbody tr:target { background: #FCF2C4; box-shadow: inset 4px 0 0 var(--red); }
tbody tr:hover { background: #FBF8EF; }
.chip {
  display: inline-block;
  border-radius: 0;
  padding: 2px 9px;
  min-width: 30px;
  font-size: 12px;
  line-height: 1.5;
  font-weight: 800;
  text-align: center;
  color: var(--ink);
}
.chip-a { background: var(--green); color: var(--white); }
.chip-b { background: var(--blue); color: var(--white); }
.chip-c { background: var(--yellow); color: var(--ink); }
.chip-d { background: var(--orange); color: var(--ink); }
.chip-f { background: var(--red); color: var(--white); }
.chip-nr { background: #CFC9BB; color: #49463D; }
.empty-state { text-align: center; color: var(--muted); font-size: 16px; line-height: 1.5; font-weight: 500; }
#badge, #methodology, footer { margin-top: 56px; }
.badge-example { margin: 0 0 16px; }
.code-block {
  background: var(--ink);
  color: #F2EFE6;
  padding: 16px;
  border-radius: 0;
  overflow-x: auto;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
  font-size: 13px;
  line-height: 1.5;
  margin: 0 0 16px;
}
#copy-btn {
  font: inherit;
  font-weight: 800;
  letter-spacing: 0.02em;
  color: var(--white);
  background: var(--blue);
  border: var(--bd);
  border-radius: 0;
  padding: 9px 17px;
  cursor: pointer;
}
#copy-btn:hover { background: var(--ink); }
.copy-note { margin: 8px 0 0; color: var(--muted); font-size: 13px; line-height: 1.4; font-weight: 500; }
.card {
  background: var(--white);
  border: var(--bd);
  border-radius: 0;
  padding: 26px;
}
.m-table { border-collapse: collapse; margin: 0 0 18px; width: 100%; }
.m-table th, .m-table td { border: var(--bd1); padding: 9px 13px; text-align: left; font-size: 14px; line-height: 1.4; }
.m-table th { font-weight: 800; background: var(--yellow); text-transform: lowercase; letter-spacing: 0.02em; font-size: 13px; }
.pager { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 22px 0 0; }
.pager button {
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
  color: var(--ink);
  background: var(--white);
  border: var(--bd);
  border-radius: 0;
  padding: 7px 13px;
  cursor: pointer;
}
.pager button:hover { background: var(--yellow); }
.pager button.active { background: var(--ink); color: var(--white); }
footer { margin-top: 56px; padding: 28px 0 48px; border-top: 3px solid var(--ink); color: var(--muted); font-size: 13px; line-height: 1.6; font-weight: 500; }
.foot-top { display: flex; flex-wrap: wrap; gap: 28px 48px; }
.foot-brand { flex: 1 1 240px; min-width: 220px; }
.foot-triad { display: block; margin: 0 0 10px; }
.foot-wm { font-size: 22px; font-weight: 800; letter-spacing: -0.6px; line-height: 1; text-transform: lowercase; margin: 0 0 8px; }
.foot-tag { margin: 0; color: var(--ink); font-weight: 500; }
.foot-col { flex: 1 1 220px; min-width: 200px; }
.foot-h { font-weight: 800; text-transform: lowercase; letter-spacing: 0.02em; color: var(--ink); margin: 0 0 8px; }
.foot-col p { margin: 0; }
.foot-nav { display: flex; flex-direction: column; gap: 7px; align-items: flex-start; }
.foot-base { margin-top: 28px; padding-top: 16px; border-top: var(--bd1); }
.foot-fine { margin: 0 0 8px; }
.foot-stamp { margin: 0; font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace; font-size: 12px; letter-spacing: 0.02em; }
@media (max-width: 700px) {
  h1 { font-size: 34px; }
}
</style>
</head>
<body>
<div class="container">

<header>
<svg class="triad" width="84" height="30" viewBox="0 0 84 30" aria-hidden="true"><circle cx="12" cy="15" r="11" fill="#1F49C9" stroke="#111111" stroke-width="1.5"/><rect x="31" y="4" width="22" height="22" fill="#E1352A" stroke="#111111" stroke-width="1.5"/><polygon points="72,4 83,26 61,26" fill="#F5C400" stroke="#111111" stroke-width="1.5"/></svg>
<h1><span class="wm-t">Trust</span><span class="wm-l">Lens</span></h1>
<p class="subtitle">Evidence-based trust scores for OKX.AI marketplace agents</p>
<p class="credibility">$agent_count agents · data as of $data_as_of · methodology v$score_version</p>
<nav class="site-nav"><a href="#methodology">Methodology</a> · <a href="#badge">Verified badge</a></nav>
</header>

<section class="controls">
<div class="controls-row">
<label for="cat">Category</label>
<select id="cat">
<option value="">All categories</option>
$category_options
</select>
<span id="count" aria-live="polite">Showing $agent_count of $agent_count agents</span>
</div>
<div class="search-row">
<label for="q">Search</label>
<input type="search" id="q" placeholder="Filter by agent name" autocomplete="off" aria-controls="lb">
</div>
<p class="nr-legend">NR = Not Rated — insufficient transaction or review evidence to score. See the <a href="#methodology">methodology</a>.</p>
</section>

<section class="table-card">
<table id="lb">
<caption class="visually-hidden">Trust scores for $agent_count OKX.AI marketplace agents</caption>
<thead>
<tr>
<th scope="col" class="num"><button type="button" data-k="rank" data-t="n" aria-label="Rank">#<span class="arrow" aria-hidden="true"></span></button></th>
<th scope="col"><button type="button" data-k="name" data-t="s">Agent<span class="arrow" aria-hidden="true"></span></button></th>
<th scope="col"><button type="button" data-k="category" data-t="s">Category<span class="arrow" aria-hidden="true"></span></button></th>
<th scope="col" class="num"><button type="button" data-k="score" data-t="n">TrustScore<span class="arrow" aria-hidden="true"></span></button></th>
<th scope="col" class="ctr"><button type="button" data-k="grade" data-t="n">Grade<span class="arrow" aria-hidden="true"></span></button></th>
<th scope="col"><button type="button" data-k="confidence" data-t="n">Confidence<span class="arrow" aria-hidden="true"></span></button></th>
<th scope="col" class="num"><button type="button" data-k="sold" data-t="n">Sold<span class="arrow" aria-hidden="true"></span></button></th>
<th scope="col" class="num"><button type="button" data-k="rating" data-t="n">Rating<span class="arrow" aria-hidden="true"></span></button></th>
<th scope="col" class="num"><button type="button" data-k="price" data-t="n">Price (USDT)<span class="arrow" aria-hidden="true"></span></button></th>
</tr>
</thead>
<tbody>
$rows
<tr id="empty-row" style="display: none"><td colspan="9" class="empty-state">No agents match this filter. Select 'All categories' to see all $agent_count agents.</td></tr>
</tbody>
</table>
</section>

<nav class="pager" id="pager" aria-label="Leaderboard pages"></nav>

<section id="badge">
<h2>TrustLens Verified badge</h2>
<p>'TrustLens Verified' means this agent has been scored by TrustLens under the published methodology. It is not an endorsement or a guarantee.</p>
<div class="badge-example">$example_badge</div>
<pre class="code-block"><code id="snippet-html">$snippet_html</code>

<code id="snippet-md">$snippet_md</code></pre>
<p>Replace AGENT_ID with your agent's id from the table above.</p>
<button id="copy-btn" type="button">Copy badge snippet</button>
<p id="copy-note" class="copy-note" aria-live="polite"></p>
</section>

<section id="methodology">
<div class="card">
<h2>About the methodology</h2>
<p>TrustScore is a 0–100 score computed by a deterministic, versioned formula over public OKX.AI marketplace data. The same data snapshot always produces the same score. There is no manual adjustment and no generated prose — and agents cannot pay to alter scores.</p>
<table class="m-table">
<thead><tr><th>Component</th><th>Weight</th><th>What it measures</th></tr></thead>
<tbody>
$components_rows
</tbody>
</table>
<p>When a component has no evidence for an agent, the remaining weights are renormalized rather than guessed.</p>
<table class="m-table">
<thead><tr><th>Grade</th><th>Score range</th><th>Meaning</th></tr></thead>
<tbody>
$bands_rows
</tbody>
</table>
<p>An agent with zero recorded sales and no displayed rating is Not Rated (NR) rather than scored. NR is an honest insufficient-evidence state, not a low score. NR agents are listed after scored agents and are unranked.</p>
<p>Confidence (high / medium / low) reflects how much evidence backs a score. Thin evidence — for example a perfect rating with fewer than 5 recorded sales — lowers confidence and is flagged in the score card. A flag describes a statistical pattern; it is not an accusation.</p>
<p>Categories are derived by TrustLens from listing taglines using fixed keyword rules — OKX.AI does not publish agent categories. The first matching rule wins; agents matching no rule are grouped under 'Other Services'.</p>
<p>Methodology v$score_version · data as of $data_as_of. Any change to the formula, weights, or bands increments the version.</p>
<p>$disclaimer</p>
</div>
</section>

<footer>
<div class="foot-top">
<div class="foot-brand">
<svg class="foot-triad" width="66" height="24" viewBox="0 0 84 30" aria-hidden="true"><circle cx="12" cy="15" r="11" fill="#1F49C9" stroke="#111111" stroke-width="1.5"/><rect x="31" y="4" width="22" height="22" fill="#E1352A" stroke="#111111" stroke-width="1.5"/><polygon points="72,4 83,26 61,26" fill="#F5C400" stroke="#111111" stroke-width="1.5"/></svg>
<p class="foot-wm"><span class="wm-t">trust</span><span class="wm-l">lens</span></p>
<p class="foot-tag">Evidence-based trust scores for OKX.AI marketplace agents.</p>
</div>
<div class="foot-col">
<p class="foot-h">Programmatic access</p>
<p>4 MCP tools at /mcp — score_agent, compare_agents, category_leaderboard, marketplace_stats. Every response includes generated_at and a methodology link.</p>
</div>
<div class="foot-col">
<p class="foot-h">Explore</p>
<nav class="foot-nav"><a href="#methodology">Methodology</a><a href="#badge">Verified badge</a></nav>
</div>
</div>
<div class="foot-base">
<p class="foot-fine">$disclaimer</p>
<p class="foot-stamp">TrustLens · methodology v$score_version · data as of $data_as_of</p>
</div>
</footer>

</div>
<script>
(function () {
  "use strict";
  var table = document.getElementById("lb");
  if (!table || !table.tBodies.length) { return; }
  var tbody = table.tBodies[0];
  var emptyRow = document.getElementById("empty-row");
  var countEl = document.getElementById("count");
  var select = document.getElementById("cat");
  var qInput = document.getElementById("q");
  var copyBtn = document.getElementById("copy-btn");
  var pager = document.getElementById("pager");
  var tableCard = table.parentNode;
  var PAGE_SIZE = 50;
  var currentPage = 0;
  var rows = [];
  var i;
  var all = tbody.rows;
  for (i = 0; i < all.length; i++) {
    if (all[i].id && all[i].id.indexOf("agent-") === 0) { rows.push(all[i]); }
  }
  var TOTAL = rows.length;
  for (i = 0; i < rows.length; i++) { rows[i].setAttribute("data-i", String(i)); }

  // --- column sort: data-v drives comparison; empty values always sink ---
  var buttons = [];
  var headCells = table.tHead.rows[0].cells;
  for (i = 0; i < headCells.length; i++) {
    var b = headCells[i].getElementsByTagName("button")[0];
    if (b) { buttons.push(b); }
  }
  var currentKey = null;
  var currentDir = 1;

  function originalOrder(a, b) {
    return Number(a.getAttribute("data-i")) - Number(b.getAttribute("data-i"));
  }

  function makeComparator(idx, type, dir) {
    return function (a, b) {
      var av = a.cells[idx].getAttribute("data-v") || "";
      var bv = b.cells[idx].getAttribute("data-v") || "";
      if (av === "" || bv === "") {
        if (av === "" && bv === "") { return originalOrder(a, b); }
        return av === "" ? 1 : -1; // empty sorts last regardless of direction
      }
      var cmp = 0;
      if (type === "n") {
        cmp = Number(av) - Number(bv);
      } else if (av < bv) { // raw code-unit comparison: deterministic, locale-free
        cmp = -1;
      } else if (av > bv) {
        cmp = 1;
      }
      if (cmp === 0) { return originalOrder(a, b); }
      return cmp * dir;
    };
  }

  function clearHeaderState() {
    for (var j = 0; j < buttons.length; j++) {
      buttons[j].classList.remove("sorted");
      buttons[j].getElementsByClassName("arrow")[0].textContent = "";
      buttons[j].parentNode.removeAttribute("aria-sort");
    }
  }

  function onSortClick(btn) {
    var th = btn.parentNode;
    var key = btn.getAttribute("data-k");
    var type = btn.getAttribute("data-t");
    if (currentKey === key) { currentDir = -currentDir; } else { currentKey = key; currentDir = 1; }
    rows.sort(makeComparator(th.cellIndex, type, currentDir));
    for (var j = 0; j < rows.length; j++) { tbody.appendChild(rows[j]); }
    if (emptyRow) { tbody.appendChild(emptyRow); }
    clearHeaderState();
    btn.classList.add("sorted");
    btn.getElementsByClassName("arrow")[0].textContent = currentDir === 1 ? " ↑" : " ↓";
    th.setAttribute("aria-sort", currentDir === 1 ? "ascending" : "descending");
    currentPage = 0;
    render();
  }

  for (i = 0; i < buttons.length; i++) {
    (function (btn) {
      btn.addEventListener("click", function () { onSortClick(btn); });
    })(buttons[i]);
  }

  // --- pagination: 50 rows/page over the current filter + sort order ---
  function render() {
    var want = select ? select.value : "";
    var q = qInput ? qInput.value.trim().toLowerCase() : "";
    var matching = [];
    var j;
    for (j = 0; j < rows.length; j++) {
      var cat = rows[j].cells[2].getAttribute("data-v") || "";
      var name = rows[j].cells[1].textContent.toLowerCase();
      if ((want === "" || cat === want) && (q === "" || name.indexOf(q) !== -1)) { matching.push(rows[j]); }
    }
    var total = matching.length;
    var pageCount = total === 0 ? 1 : Math.ceil(total / PAGE_SIZE);
    if (currentPage > pageCount - 1) { currentPage = pageCount - 1; }
    if (currentPage < 0) { currentPage = 0; }
    var start = currentPage * PAGE_SIZE;
    var end = start + PAGE_SIZE;
    for (j = 0; j < rows.length; j++) { rows[j].style.display = "none"; }
    for (j = 0; j < matching.length; j++) {
      matching[j].style.display = (j >= start && j < end) ? "" : "none";
    }
    if (countEl) {
      if (total === 0) { countEl.textContent = "Showing 0 of " + TOTAL + " agents"; }
      else { countEl.textContent = "Showing " + (start + 1) + "–" + Math.min(end, total) + " of " + total + " agents"; }
    }
    if (emptyRow) { emptyRow.style.display = total === 0 ? "" : "none"; }
    renderPager(total, pageCount);
  }

  function renderPager(total, pageCount) {
    if (!pager) { return; }
    pager.textContent = "";
    if (pageCount <= 1) { return; }
    for (var p = 0; p < pageCount; p++) {
      var startN = p * PAGE_SIZE + 1;
      var endN = Math.min((p + 1) * PAGE_SIZE, total);
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = startN + "–" + endN;
      if (p === currentPage) { b.className = "active"; b.setAttribute("aria-current", "true"); }
      (function (pi) {
        b.addEventListener("click", function () {
          currentPage = pi;
          render();
          if (tableCard && tableCard.scrollIntoView) { tableCard.scrollIntoView(); }
        });
      })(p);
      pager.appendChild(b);
    }
  }

  function goToHash() {
    var h = window.location.hash;
    if (!h || h.indexOf("#agent-") !== 0) { return; }
    var target = document.getElementById(h.slice(1));
    if (!target) { return; }
    if (select) { select.value = ""; }
    if (qInput) { qInput.value = ""; }
    for (var j = 0; j < rows.length; j++) {
      if (rows[j] === target) { currentPage = Math.floor(j / PAGE_SIZE); break; }
    }
    render();
    if (target.scrollIntoView) { target.scrollIntoView(); }
  }

  // --- category filter + name search reset to the first page ---
  if (select) {
    select.addEventListener("change", function () { currentPage = 0; render(); });
  }
  if (qInput) {
    qInput.addEventListener("input", function () { currentPage = 0; render(); });
  }
  window.addEventListener("hashchange", goToHash);
  if (window.location.hash && window.location.hash.indexOf("#agent-") === 0) { goToHash(); } else { render(); }

  // --- copy badge snippet (HTML variant) ---
  if (copyBtn) {
    var note = document.getElementById("copy-note");
    var snippet = document.getElementById("snippet-html");
    var copied = function () {
      copyBtn.textContent = "Copied";
      window.setTimeout(function () { copyBtn.textContent = "Copy badge snippet"; }, 1500);
    };
    var failed = function () {
      var range = document.createRange();
      range.selectNodeContents(snippet);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      if (note) { note.textContent = "Copy failed — select the snippet text and copy manually."; }
    };
    copyBtn.addEventListener("click", function () {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(snippet.textContent).then(copied, failed);
      } else {
        failed();
      }
    });
  }
})();
</script>
</body>
</html>
""")


def _fmt_score(score: int | None) -> str:
    return _EM_DASH if score is None else str(score)


def _fmt_sold(sold: int) -> str:
    return f"{sold:,}"


def _fmt_rating(rating: float | None) -> str:
    return _EM_DASH if rating is None else f"{rating:.1f}"


def _fmt_price(price: float | None) -> str:
    """Fixed-decimal price: never scientific notation (0.000015, not 1.5e-05)."""
    if price is None:
        return _EM_DASH
    if price >= 1:
        return f"{price:.2f}"
    return f"{price:.6f}".rstrip("0").rstrip(".")


def _render_rows(rows: list[sqlite3.Row]) -> str:
    """One <tr> per agent; scored rows ranked 1..N in query order, NR unranked."""
    parts: list[str] = []
    rank = 0
    for row in rows:
        score = row["score"]
        if score is not None:
            rank += 1
            rank_txt, rank_v = str(rank), str(rank)
        else:
            rank_txt, rank_v = _EM_DASH, ""
        name = row["name"]
        category = row["category"]
        tagline = row["tagline"] or ""
        grade = row["grade"]
        confidence = row["confidence"]
        sold = row["sold"]
        rating = row["rating"]
        price = row["price_usdt"]
        price_txt = _fmt_price(price)
        parts.append(_ROW.format(
            aid=html.escape(row["id"], quote=True),
            rank_v=rank_v,
            rank=rank_txt,
            name_v=html.escape(name, quote=True),
            tagline_v=html.escape(tagline, quote=True),
            name=html.escape(name),
            cat_v=html.escape(category, quote=True),
            cat=html.escape(category),
            score_v="" if score is None else str(score),
            score=_fmt_score(score),
            grade_v=_GRADE_ORDINAL.get(grade, ""),
            grade_cls=_GRADE_CLASS.get(grade, "nr"),
            grade=html.escape(grade),
            conf_v=_CONFIDENCE_ORDINAL.get(confidence, ""),
            conf=html.escape(confidence),
            sold_v=str(sold),
            sold=_fmt_sold(sold),
            rating_v="" if rating is None else str(rating),
            rating=_fmt_rating(rating),
            price_v="" if price is None else price_txt,
            price=price_txt,
        ))
    return "\n".join(parts)


def _render_category_options() -> str:
    """The 9 fixed buckets, alphabetical, value == label (escaped both places)."""
    return "\n".join(
        f'<option value="{html.escape(c, quote=True)}">{html.escape(c)}</option>'
        for c in sorted(CATEGORIES)
    )


def _render_components_rows() -> str:
    return "\n".join(
        "<tr><td>{name}</td><td class=\"num\">{weight}%</td><td>{measures}</td></tr>".format(
            name=html.escape(name),
            weight=int(WEIGHTS[key] * 100),
            measures=html.escape(measures),
        )
        for key, name, measures in _COMPONENT_DISPLAY
    )


def _render_bands_rows() -> str:
    """Grade bands derived from GRADE_BANDS + the NR row; chips double as legend."""
    bands: list[tuple[str, str]] = []
    upper = 100
    for grade, cut in GRADE_BANDS:
        bands.append((grade, f"{cut}{_EN_DASH}{upper}"))
        upper = cut - 1
    bands.append(("NR", "no score"))
    return "\n".join(
        '<tr><td class="ctr"><span class="chip chip-{cls}">{grade}</span></td>'
        "<td>{rng}</td><td>{meaning}</td></tr>".format(
            cls=_GRADE_CLASS.get(grade, "nr"),
            grade=html.escape(grade),
            rng=html.escape(rng),
            meaning=html.escape(GRADE_DESCRIPTIONS[grade]),
        )
        for grade, rng in bands
    )


def _snippets(base_url: str) -> tuple[str, str]:
    """Escaped HTML + Markdown embed snippets; AGENT_ID/GRADE/SCORE stay literal."""
    snippet_html_raw = (
        f'<a href="{base_url}/#agent-AGENT_ID">\n'
        f'  <img src="{base_url}/badge/AGENT_ID.svg"\n'
        '       alt="TrustLens grade GRADE, score SCORE" height="20">\n'
        "</a>"
    )
    snippet_md_raw = (
        f"[![TrustLens GRADE SCORE]({base_url}/badge/AGENT_ID.svg)]"
        f"({base_url}/#agent-AGENT_ID)"
    )
    return html.escape(snippet_html_raw), html.escape(snippet_md_raw)


def build(
    db_path: str | Path,
    out_path: str | Path,
    base_url: str = "http://localhost:8000",
) -> int:
    """Render web/dist/index.html from SQLite. Returns bytes written.

    Pure read; opens its own read-only connection (space-safe URI — the repo
    path contains spaces, research Pitfall 9). Output is byte-deterministic:
    same database bytes in, same HTML bytes out — no wall clock, no randomness.
    """
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(_QUERY).fetchall()
    finally:
        conn.close()

    base_url = base_url.rstrip("/")
    if rows:
        score_version = rows[0]["score_version"]
        data_as_of = rows[0]["data_as_of"][:10]
        example_badge = badge_svg(rows[0]["grade"], rows[0]["score"])
    else:  # empty DB: still render a valid page from constants
        score_version = SCORE_VERSION
        data_as_of = _EM_DASH
        example_badge = badge_svg(None, None)
    snippet_html, snippet_md = _snippets(base_url)

    page = _PAGE.substitute(
        agent_count=str(len(rows)),
        data_as_of=html.escape(data_as_of),
        score_version=html.escape(score_version),
        category_options=_render_category_options(),
        rows=_render_rows(rows),
        example_badge=example_badge,
        snippet_html=snippet_html,
        snippet_md=snippet_md,
        components_rows=_render_components_rows(),
        bands_rows=_render_bands_rows(),
        disclaimer=html.escape(DISCLAIMER),
    )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = page.encode("utf-8")
    out.write_bytes(data)
    return len(data)
