# Phase 2: Scoring Engine - Research

**Researched:** 2026-07-11
**Domain:** Deterministic trust-scoring over sparse marketplace data (pure Python, SQLite persistence)
**Confidence:** HIGH — every formula in this document was executed against the real 272-agent database; distributions, rankings, and byte-determinism are observed results, not predictions

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Component set (locked verbatim from the brief)**
1. **Sales volume & velocity**
2. **Review-count-vs-sales ratio**
3. **Rating credibility** — "5.0 with <5 sales = low confidence, flagged not accused"
4. **Price-vs-category percentile** (uses Phase 1's derived categories)
5. **Listing age/consistency**
Every component returns a `reason` string. Component list is fixed — do not add or remove components.

**Data reality constraints (locked — from Phase 1 empirical work)**
- Census provides NO review counts and NO listing ages. Components 2 and 5 MUST be defined over what actually exists: rating presence/positive_pct/sold for the review-signal ratio; snapshots history (first_seen/last_seen, snapshot series) for age/consistency. On the first snapshot, history-dependent signals MUST degrade to an explicit "insufficient history" state — never fabricate.
- Known field states over the 272 real agents: 90 rated / 182 unrated (rating echo rule), 28 NULL prices, sold ranges 0–1550, categories per the pinned 9-bucket distribution (70/45/41/30/27/22/17/15/5).
- All inputs come from the SQLite DB via Phase 1 modules (`indexer.db.connect()` etc.); scoring functions themselves are pure (take plain rows/values, no I/O, no wall clock — `as_of`/`generated_at` injected by callers).

**Credibility envelope (locked — from project FEATURES research)**
- Dual encoding: integer 0–100 + letter grade A–F with published band thresholds (exact bands are discretion but MUST be constants, documented, and test-pinned)
- Explicit **NR ("Not Rated / insufficient data") state** plus a per-score `confidence` field (e.g. high/medium/low) instead of guessing on thin rows
- Versioned scoring: a `score_version` constant embedded in every output; bump on any formula/weight change
- Dual timestamps in outputs: `generated_at` (injected at compute time) and `data_as_of` (snapshot captured_at)
- Per-response disclaimer string: statistical estimate over public marketplace data, not a statement of fact

**Neutral language (locked — SCOR-03)**
- Fixed reason vocabulary: factual observations with observed-vs-benchmark numbers ("pattern consistent with…", "outside category norm (X vs median Y)", "insufficient data")
- BANNED anywhere in scoring output or code strings: "fraud", "scam", "fake", "manipulat*" (any casing) — enforce with a banned-vocabulary test over all reason templates and rendered outputs for all 272 agents
- Flags describe data patterns, never seller intent or guilt

**Persistence (locked)**
- `scores` table added via the additive DDL mechanism in `indexer/db.py`'s pattern (CREATE IF NOT EXISTS tuple); columns must carry: agent_id, score, grade, confidence, score_version, generated_at, data_as_of, components JSON (deterministically serialized: sorted keys, fixed float formatting)
- Refresh pipeline computes and persists scores for all agents after indexing (wire into `indexer/refresh.py` refresh flow without breaking its exit-code contract or determinism)
- CRITICAL inherited gate: comments/strings in any file matched by the 01-03 grep gates must not contain the uppercase literal "UNIQUE"; keep parameterized SQL only; no wall-clock reads inside scoring/ or indexer/

**Determinism & coverage (locked — SCOR-01, SCOR-04)**
- Same row + same category stats + same as_of → byte-identical output (stable ordering, explicit rounding)
- pytest coverage ≥90% on `scoring/` enforced via pyproject config (`--cov=scoring --cov-fail-under=90` per STACK.md pattern) — the gate must run as plain `python -m pytest`
- Edge cases with explicit tests: 0 sales, missing rating, missing price, "1.55K"-derived 1550 sold, NR state, first-snapshot insufficient-history

**Git & conduct (locked)**
- Commits authored by the user's git identity only; NEVER any AI attribution
- Conventional commits per task (`feat(02-XX): …`); 2-attempt stop rule on unresolved errors

### Claude's Discretion
- Exact weights, band thresholds, and formulas (must be constants, documented in code, and test-pinned; researcher should dry-run candidates against the real 272-agent DB to avoid degenerate distributions)
- Module layout inside `scoring/` (e.g. components.py / engine.py / persist.py)
- Confidence-level rubric details
- Reason string templates (within the locked vocabulary)

### Deferred Ideas (OUT OF SCOPE)
- Longitudinal velocity/consistency signals from recurring scrapes — v2 (INDX-05); v1 degrades gracefully
- Real review-count data from agent detail pages — Phase 5 scraper may enrich; design the component to accept it when present
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCOR-01 | Pure, deterministic scoring functions produce 0–100 TrustScore + A–F grade + component breakdown for any agent row | Full formula spec below, prototyped as pure functions; dry-run over 272 agents twice → byte-identical output (cross-process diff verified); compute+persist = 30ms total |
| SCOR-02 | Five components implemented with `reason` strings; review-signal and age components degrade honestly | Exact per-component formulas with reason templates below; review-signal ratio derived from rating-presence/positive_pct/sold only; velocity+age return explicit "insufficient history" on single snapshot (verified: all 272 agents have exactly 1 distinct captured_at) |
| SCOR-03 | Neutral, factual wording — never accusatory | Reason templates use only observed-vs-benchmark numbers; banned-vocab regex `(?i)(fraud|scam|fake|manipulat)` run over all 272 rendered score cards → 0 hits (verified); templates never embed agent names/taglines (1 real tagline contains a banned substring — id 2361) |
| SCOR-04 | pytest ≥90% coverage on `scoring/` incl. edge cases | pyproject `addopts` pattern sandbox-verified in 4 scenarios (pass / subset-fail / --no-cov / missing-package); edge-case inventory below includes all locked cases plus 4 newly discovered ones (FundingArb rated-no-pct, positive_pct=0.0 trio, price=0.00 (8 agents), duplicate snapshot rows) |
</phase_requirements>

## Summary

Phase 2 is a pure-computation phase with zero new dependencies: five component functions (stdlib `math`/`json` only) + an aggregation engine + a persistence module wired into the existing refresh transaction. The entire technical risk was "do the formulas discriminate on this specific, extremely sparse dataset?" — so this research **built the DB and dry-ran two formula iterations over all 272 real agents**. The final (v2) formulas produce **A:12, B:9, C:19, D:54, F:27, NR:151** — every band populated, all mandated sanity checks passing: CoinWM (1.55K sold) ranks #1 at 95/A/high; the 42-agent "5.0 rating with <5 sales" cohort is 100% low-confidence, lands D(34)/F(8), and none reach the top 20; CoinAnk (1370 sold, unrated) scores 73/B/medium with the neutral observation "no displayed rating despite 1370 units sold — 87% of agents with 20+ sales display one (20 of 23)".

The dataset is brutally sparse — median sold is **0** (151 agents have zero sales AND no rating; empirically `sold==0 ⟺ unrated`), 59 of 90 rated agents show a perfect 5.0, and 76 of 89 positive_pct values are exactly 100.0. This forces two design decisions the dry-run validated: (a) **NR = zero evidence on both axes** (`sold == 0 AND rating IS NULL`) — exactly the 151 zero-signal agents, honest per the FEATURES anti-feature guidance, leaving 121 scoreable agents that spread across all five grades; (b) **missing components are excluded and weights renormalize** rather than fabricating neutral values. Iteration v1→v2 fixed one real perversity the dry-run exposed: a punitive credibility subscore made a 5.0/100%-positive/1-sale agent rank *below* an unrated 1-sale agent; a credibility floor (`0.30 + 0.70×support`) restored the invariant "displaying a rating never ranks you below having none."

Integration facts verified against the live repo: the snapshots table currently holds 1632 rows but only **1 distinct captured_at** (reruns duplicate by design) so velocity/age must count `DISTINCT captured_at`; existing tests use a subset assertion for tables (`{"agents","snapshots"} <= tables`) so the additive `scores` DDL breaks nothing; the coverage gate (`addopts = "--cov=scoring --cov-fail-under=90"`) was sandbox-proven to pass on full runs and must land in the same plan as the scoring package + tests (landing it earlier fails the existing 78 tests at 0% coverage).

**Primary recommendation:** Implement the v2 formulas exactly as specified below (constants pinned by tests), persist via DELETE+INSERT inside the existing `_persist_records` transaction, and pin golden values from the dry-run table (CoinWM 95/A, 3345 94/A, CoinAnk 73/B, Messari 32/F, 2662 NR).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Component subscores + reasons | `scoring/` pure functions | — | No I/O, no clock; plain values in → dict out (locked) |
| Marketplace/category stats (percentile pools, rating base-rate) | `scoring/` (stats builder over rows) | — | Pure precomputation from the same snapshot; keeps components pure |
| Aggregation, grade bands, NR rule, confidence | `scoring/` engine | — | Deterministic constants, test-pinned |
| Deterministic components-JSON serialization | `scoring/` engine/persist boundary | — | `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)` |
| `scores` table DDL | `indexer/db.py` DDL tuple | — | Locked: additive CREATE IF NOT EXISTS tuple; db.py docstring says "Phase 2 appends its scores table to this tuple" |
| Reading agents/snapshots + writing scores | `scoring/persist.py` | `indexer/refresh.py` (passes the connection) | scoring never imports indexer; refresh owns the connection + transaction |
| generated_at / data_as_of injection | `indexer/refresh.py` (CLI/caller) | — | No wall clock in indexer/ or scoring/; default = captured_at (deterministic) |
| Serving scores | Phase 3 (out of scope) | — | Persisted shape must be servable without recomputation |

## Standard Stack

### Core

**Zero new dependencies.** Phase 2 uses only the Python standard library on top of the already-pinned toolchain.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `math` (stdlib) | 3.11+ | `log10` for volume/support scaling | No numpy/scipy — unlisted deps are banned |
| `json` (stdlib) | 3.11+ | Deterministic components serialization | `sort_keys` + fixed separators is the canonical determinism pattern |
| `sqlite3` (stdlib) | 3.11+ | scores persistence (persist.py only) | Locked stack; connection passed in by refresh.py |
| pytest / pytest-cov | 9.1.1 / 7.1.0 | Coverage gate | **Verified installed and working in this environment** (78 tests pass; sandbox gate test green) |

**Version verification:** performed empirically against the live environment rather than a registry — `python -m pytest -q` → 78 passed; `pip show pytest-cov` → 7.1.0; Python 3.14.2. [VERIFIED: local environment 2026-07-11]

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib `statistics`/manual percentile | numpy percentile | numpy is an unlisted runtime dep — forbidden; manual mid-rank percentile is ~4 lines and deterministic |
| DELETE+INSERT for scores | ON CONFLICT upsert | Upsert leaves stale rows if an agent vanishes from a future census; DELETE+INSERT in one transaction is simpler and self-cleaning at 272 rows |

**Installation:** nothing to install.

## Architecture Patterns

### System Architecture Diagram

```
python -m indexer.refresh (offline, deterministic)
    │
    ├── load_census(csv) ──► [AgentRecord × 272]
    │
    └── _persist_records(db_path, records, captured_at)
            connect() ─► init_db()            ◄─ DDL tuple now includes scores table
            with conn:  (ONE atomic transaction)
                persist(records)              ◄─ agents upsert + snapshots append (existing)
                scoring.persist.compute_all(conn, generated_at, data_as_of)   ◄─ NEW
                    │  SELECT agents ORDER BY id
                    │  SELECT agent_id, COUNT(DISTINCT captured_at) FROM snapshots GROUP BY agent_id
                    ▼
                scoring.stats.build(rows) ──► Stats (category price pools, market pool,
                    │                         rating-display base rate at 20+ sales)
                    ▼
                scoring.engine.score_agent(row, stats, distinct_snapshots)   ◄─ PURE
                    │  five components → subscores + reasons
                    │  NR rule / weighted aggregate / grade / confidence
                    ▼
                serialize components (sorted keys, fixed formatting)
                    ▼
                DELETE FROM scores; INSERT × 272                              ◄─ no commit inside
            conn commit on `with` exit ──► scores table (Phase 3 reads it)
```

Trace for the primary use case: census row → AgentRecord → agents/snapshots rows → Stats + pure scoring → serialized score row → Phase 3 SELECT.

### Recommended Project Structure

```
scoring/
├── __init__.py       # re-exports: score_agent, compute_all, SCORE_VERSION, DISCLAIMER
├── stats.py          # Stats built from plain agent rows (pure; no DB)
├── components.py     # five pure component functions → component dict
├── engine.py         # score_agent(row, stats, distinct_snapshots) → ScoreCard;
│                     # grade bands, NR rule, confidence rubric, serialize_components()
└── persist.py        # compute_all(conn, generated_at, data_as_of) → (scored, nr)
                      # the ONLY module that touches sqlite3; no commits (caller's transaction)
```

`pyproject.toml` `[tool.setuptools] packages` gains `"scoring"` (the existing comment says exactly this).

### Pattern 1: Pure component signature

**What:** Every component takes plain values and returns the same dict shape; `score: None` is the explicit insufficient-data state.
**When to use:** All five components.

```python
# verified in dry-run prototype (this session)
def c_rating_credibility(rating: float | None, sold: int) -> dict:
    if rating is None:
        return {"score": None, "observed": None, "benchmark": None, "flagged": False,
                "reason": "insufficient data — no rating displayed to evaluate"}
    support = min(1.0, math.log10(1 + sold) / math.log10(1 + SUPPORT_REF))
    score = round(100 * (rating / 5.0) * (CRED_FLOOR + (1 - CRED_FLOOR) * support))
    ...
```

### Pattern 2: Stats precomputed once per refresh, passed in

**What:** Percentile pools and the rating-display base rate are computed from the full agent list once, then passed to every `score_agent` call. Components stay pure; category benchmarks stay consistent across all 272 agents in one run.
**Why:** Locked determinism ("same row + same category stats + same as_of → byte-identical") makes category stats an explicit input.

### Pattern 3: Persistence inside the caller's transaction

**What:** `compute_all(conn, ...)` never commits — identical contract to `upsert_agent`/`insert_snapshot`. Wiring it inside `_persist_records`'s existing `with conn:` block makes agents+snapshots+scores one atomic unit: the DB can never hold new snapshots with stale scores.
**Verified:** existing exit-code tests keep passing conceptually — sqlite errors inside the block already map to exit 2 via the existing `except (OSError, sqlite3.Error)` in `main()`; the db-path-is-a-directory test (test_refresh.py:337) fails at connect, before scoring runs.

### Anti-Patterns to Avoid

- **Fabricating neutral subscores for missing data:** locked out ("never fabricate"). Exclude the component; renormalize weights; surface the reason.
- **Punitive credibility on thin evidence:** v1 scored 5.0-with-1-sale credibility at 18/100 → a fully-rated agent ranked below a naked listing. Thin evidence should floor near "no information" (CRED_FLOOR), not near zero. The flag — not the subscore — carries the warning.
- **Counting raw snapshot rows for history:** the real DB has 6× duplicate snapshot rows for one captured_at. Use `COUNT(DISTINCT captured_at)`.
- **Embedding listing text in reasons:** agent id 2361's tagline contains a banned substring; names carry CJK/quotes/newlines. Reasons are templates + numbers + category names only.
- **`{:g}` formatting for prices:** renders 1.5e-05 as scientific notation in user-facing text. Use fixed-decimal formatting (helper below).

## The Empirical Formula Specification (v2 — dry-run verified)

All constants live in `scoring/` as module-level names, documented and test-pinned. [VERIFIED: executed over all 272 agents, this session]

### Constants

```python
SCORE_VERSION = "1.0.0"
SOLD_REF = 500          # volume log anchor: >= 500 units -> 100
SUPPORT_REF = 50        # rating-support anchor: >= 50 units -> full support
THIN_SALES = 5          # brief: "5.0 with <5 sales = low confidence"
CRED_FLOOR = 0.30       # thin evidence -> neutral-low credibility, never punitive-zero
RATING_EXPECTED_SALES = 20   # sales level at which a displayed rating is the marketplace norm
MIN_CATEGORY_PRICED = 5      # below this, price percentile falls back to marketplace pool
PRICE_DEV_SPAN = 45          # price subscore = 100 - 45 * deviation  (range 55..100)
WEIGHTS = {
    "sales_volume_velocity": 0.30,
    "review_signal_ratio":   0.20,
    "rating_credibility":    0.25,
    "price_vs_category":     0.15,
    "listing_age_consistency": 0.10,
}
GRADE_BANDS = (("A", 85), ("B", 70), ("C", 55), ("D", 40), ("F", 0))   # first match, score >= cut
HIGH_CONF_SOLD = 50
LOW_CONF_SOLD = 5
```

Why absolute log anchors instead of data-derived percentiles for volume/support: a percentile anchor would re-score every agent when *other* agents change, breaking "same row + same stats → same score" explainability. The price component is percentile-based **by locked requirement** (category-relative is its point).

### Component 1 — `sales_volume_velocity` (weight 0.30)

- **Inputs:** `sold`, `distinct_snapshots` (= `COUNT(DISTINCT captured_at)` for the agent).
- **Formula:** `score = round(100 * min(1, log10(1 + sold) / log10(1 + 500)))`. Always scored (sold=0 → 0).
- **Velocity degradation (locked):** when `distinct_snapshots < 2`, append to reason: `"; sales velocity unavailable — insufficient history (single snapshot)"`. With ≥2 distinct snapshots (v2 data), blend a sold-delta-per-day term — design seam only; UNREACHABLE and untestable on current data beyond the degradation branch.
- **Reason templates:**
  - `"{sold} unit(s) sold (volume scale tops out at 500+); sales velocity unavailable — insufficient history (single snapshot)"`
  - sold=0: `"no completed sales observed in the snapshot; …"`
- **Anchor points (verified):** 0→0, 1→11, 2→18, 9→37, 25→52, 98→74, 175→83, 371→95, ≥500→100.

### Component 2 — `review_signal_ratio` (weight 0.20)

Derived **only** from rating presence, positive_pct, sold (locked — no review counts exist). Rating display is the marketplace's own review-evidence signal; the "ratio" is observed-signal vs expected-signal-at-this-volume.

| Case | Score | Reason template |
|------|-------|-----------------|
| rated, positive_pct present, sold ≥ 5 | `round(40 + 60 * positive_pct/100)` | `"rating displayed with {pct:g}% positive across {sold} sales"` |
| rated, positive_pct NULL (real case: id 2169) | 70 | `"rating displayed; positive-review share not shown on the listing ({sold} sales)"` |
| rated, sold < 5 | `min(base, 65)` | `"rating displayed with {pct:g}% positive on only {sold} sale(s) — limited volume behind the review signal"` |
| unrated, sold ≥ 20 | 35 | `"no displayed rating despite {sold} units sold — {pct}% of agents with 20+ sales display one ({rated_hi} of {total_hi})"` |
| unrated, sold < 20 | **None** (insufficient) | `"insufficient data — no displayed rating and only {sold} sale(s)"` |

The base rate is computed in Stats from the same snapshot: currently 20 of 23 agents with ≥20 sales display a rating → 87%. [VERIFIED]

### Component 3 — `rating_credibility` (weight 0.25)

- unrated → **None**: `"insufficient data — no rating displayed to evaluate"`.
- rated: `support = min(1, log10(1 + sold) / log10(1 + 50))`; `score = round(100 * (rating/5) * (0.30 + 0.70 * support))`.
- **Mandatory flag (brief verbatim case):** `flagged = (rating == 5.0 and sold < THIN_SALES)`; reason: `"perfect 5.0 rating backed by only {sold} sale(s) — pattern consistent with limited review history; low confidence, flagged for thin data (not an assessment of conduct)"`.
- Other reasons: sold ≥ 50 → `"{rating:g}/5 rating supported by {sold} sales"`; else `"{rating:g}/5 rating with moderate volume behind it ({sold} sale(s))"`.
- **Anchor points (verified):** 5.0@1550→100, 4.9@547→98, 5.0@2 sales→50 (flagged), 5.0@1→42 (flagged), 2.0@1→17.
- The `CRED_FLOOR = 0.30` exists because v1 (no floor) produced the perverse ordering documented in Dry-Run Iteration below.

### Component 4 — `price_vs_category` (weight 0.15)

- price NULL (28 real rows) → **None**: `"insufficient data — no listed price to compare against category"`.
- Pool: the agent's category price list if it has ≥5 priced agents, else the marketplace pool (only "Other Services", 3 priced, falls back). Pools sorted ascending; built once in Stats.
- Percentile (mid-rank, self included, deterministic under ties): `p = (count_less + 0.5 * count_equal) / n`.
- `deviation = abs(p - 0.5) * 2`; `score = round(100 - 45 * deviation)` → range [55, 100]. Price extremity is an *observation*, never a heavy penalty.
- Reasons (locked phrasing "outside category norm (X vs median Y)"):
  - deviation ≤ 0.5: `"price {price} USDT within {pool} norm (P{p} among {n} priced agents; median {med} USDT)"`
  - else: `"price {price} USDT {below|above} {pool} norm ({price} vs median {med} USDT, P{p} among {n})"`
- Price formatting: `f"{p:.8f}".rstrip("0").rstrip(".")` — renders 1.5e-05 as `0.000015`, and handles price 0.00 (8 real agents). Free (0.00) prices land at the low percentile and read "below category norm" — factual.

### Component 5 — `listing_age_consistency` (weight 0.10)

- `distinct_snapshots < 2` (ALL 272 agents today) → **None**: `"insufficient history — listing observed in a single snapshot ({first_seen[:10]}); age and consistency not yet measurable"`.
- Design seam for ≥2 snapshots (v2 data, do not over-build): age = days between min/max captured_at on a log anchor; consistency = penalize field regressions across snapshots. Only the degradation branch is reachable/testable in v1.

### Aggregation, NR, grades, confidence

```python
# NR rule — zero transaction evidence AND zero review evidence
if sold == 0 and rating is None:          # empirically exactly the 151 zero-sales agents
    score, grade, confidence = None, "NR", "low"    # components still rendered
else:
    scored = {k: c for k, c in components.items() if c["score"] is not None}
    total_w = sum(WEIGHTS[k] for k in scored)                 # renormalize
    score = round(sum(WEIGHTS[k] * c["score"] for k, c in scored.items()) / total_w)
    grade = next(g for g, lo in GRADE_BANDS if score >= lo)
    if flagged or sold < LOW_CONF_SOLD or len(scored) <= 2:
        confidence = "low"
    elif len(scored) >= 4 and sold >= HIGH_CONF_SOLD and rating is not None:
        confidence = "high"
    else:
        confidence = "medium"
```

- NR agents still persist a full components object (C1 shows 0-sales observation, C4 shows price if present, others insufficient) — NR is a successful response, not an error.
- With C5 always insufficient in v1, fully-populated agents renormalize over 0.90 total weight. Documented, not a bug.
- Grade-band story for the methodology page: A = high volume + strong verified rating; B = solid volume + strong rating (or exceptional volume without rating signal); C = modest-volume rated; D = thin evidence; F = minimal evidence or negative review signals; NR = no transaction or review evidence yet.

## Dry-Run Results (all 272 real agents)

### Final grade distribution (v2)

| Grade | Count | Confidence breakdown | Population characteristics |
|-------|-------|----------------------|---------------------------|
| A (85–100) | 12 | 12 high | sold ≥ ~98, rating ≥ 4.6 |
| B (70–84) | 9 | 2 high, 7 medium | sold 23–57 well-rated, plus CoinAnk (1370 sold, unrated) |
| C (55–69) | 19 | 17 medium, 2 low | sold 5–20 rated agents |
| D (40–54) | 54 | 52 low, 2 medium | the 5.0-thin cohort (34 of 42) + unrated with some sales |
| F (0–39) | 27 | 27 low | 1–2 sales with minimal/negative signals |
| NR | 151 | 151 low | sold=0 AND unrated (exactly the zero-evidence cohort) |

Scored: 121; NR: 151. Confidence overall: 14 high / 26 medium / 232 low.

### Score histogram (121 scored agents)

```
10-19:  1 | 20-29:  1 | 30-39: 25 | 40-49: 45 | 50-59: 14
60-69: 14 | 70-79:  7 | 80-89:  7 | 90-99:  7
```

### Top 10 (score, grade, confidence — with dominant component reasons)

| # | Score | Agent | Facts | Notable component evidence |
|---|-------|-------|-------|---------------------------|
| 1 | 95 A high | 3118 CoinWM Open API | 1550 sold, 5.0, 100% | vol 100; credibility 100 ("supported by 1550 sales"); price 71 ("0.002 below category norm vs median 0.1") |
| 2 | 94 A high | 2135 Newsliquid | 371 sold, 5.0, 100% | vol 95; signal 100; credibility 100 |
| 3 | 94 A high | 3345 这个能吃吗？ | 539 sold, 5.0, 100% | vol 100; credibility 100; price 65 (P11 among 28 in Lifestyle & Health) |
| 4 | 92 A high | 2023 Onchain Data Explorer | 547 sold, 4.9, 92.86% | signal 96; price 58 ("0.000015 below category norm" — subscript-price row renders correctly) |
| 5 | 90 A high | 1500 AlphaCopy | 175 sold, 4.6, 95.45% | price 91 ("within category norm, P40 among 67") |
| 6 | 90 A high | 1719 OnChain Arb Scout | 147 sold, 4.6, 97.06% | balanced across all four live components |
| 7 | 90 A high | 2012 Barker Yield Agent | 300 sold, 4.9, 100% | vol 92 |
| 8 | 89 A high | 1891 WorldCupCaller | 172 sold, 4.7, 96% | price 79 (P73 among 15) |
| 9 | 88 A high | 2123 Fan Token Intel MCP | 98 sold, 5.0, 100% | vol 74 |
| 10 | 87 A high | 2118 Otto AI | 163 sold, 4.8, 100% | price 62 (below norm) |

### Bottom of the scored population (NR excluded; lowest observed scores, plus flagged-cohort context)

| Score | Agent | Facts | Why |
|-------|-------|-------|-----|
| 32 F low | 2082 算命老中医 | 1 sold, unrated, 1.88 USDT | vol 11; review signal + credibility insufficient; price above norm (P80) |
| 31 F low | 3255 Wokey.AI 中转站 | 1 sold, unrated | two-component score (vol 11 + price 72) |
| 31 F low | 3417 AlgoVault Quant Signal | 1 sold, unrated | same shape |
| 31 F low | 3643 OAIA Coin | 1 sold, unrated, 1.0 USDT | price above norm (P81 among 36) |
| 30 F low | 3116 美股分析 | 1 sold, unrated | vol 11 + price 68 |
| 29 F low | 3460 xbird | 1 sold, unrated, 0.001 USDT | price below norm (P11 among 23) |
| 11 F low | 3117 ChainProbe | 1 sold, unrated, no price | single-component score (vol only) — floor of the scored population |
| 32 F low | 3152 Messari | 1 sold, **2.0 rating, 0% positive** | credibility 17; review signal 40 — negative signals rank at the bottom as they should |
| 36 F low | 2067 AI Trends Content Agent | 1 sold, 5.0, 100% | *(context, not strict bottom-10)* thin-perfect: flagged, credibility 42, low conf |
| 39/38 F low | 2162 / 2823 / 3216 (1-sale 5.0 agents) | 1 sold, 5.0, 100%, priced | *(context)* top of F band — flagged thin-perfect with price data |

### Mandated sanity checks — all pass

| Check | Result |
|-------|--------|
| 42 agents with 5.0 rating and <5 sales flagged low-confidence, not top-ranked | ✅ all 42 `confidence="low"` + `flagged=true`; none in top 20; grades D:34, F:8 |
| CoinWM (1.55K sold) ranks high on volume | ✅ rank 1 of 121, score 95, A, high |
| Unrated-high-sales shows review-signal observation neutrally | ✅ CoinAnk 73/B/medium, rank 21; reason: "no displayed rating despite 1370 units sold — 87% of agents with 20+ sales display one (20 of 23)" |
| No degenerate distribution | ✅ all six states populated (12/9/19/54/27/151) |
| Byte-identical determinism | ✅ within-run double-serialization identical AND full cross-process rerun diff identical |
| Banned vocabulary in rendered outputs | ✅ 0 hits over all 272 full score cards |
| Name-collision twins (2791/2662, same name_key) | ✅ scored independently by id: 41/D vs NR |
| Agent 4137 (prose sold cell → stored 0, unrated) | ✅ NR — honest, no fabrication |
| FundingArb 2169 (rating 5.0, positive_pct NULL, 6 sold) | ✅ 56/C/medium via the rated-no-pct branch |

### Iteration history (why v2, not v1)

v1 used `credibility = 100 × (rating/5) × support` with no floor. Distribution was fine (A:12 B:9 C:16 D:36 F:48 NR:151) and all sanity checks passed, **but** the dry-run exposed a perverse ordering: agent 2067 (5.0 rating, 100% positive, 1 sale, no price) scored 28 — *below* agent 3116 (no rating at all, 1 sale, priced) at 30. Displaying verified-positive review evidence must never rank an agent below an identical agent with zero review evidence. v2 added `CRED_FLOOR = 0.30` (credibility floors near "no information" instead of near zero); the pair became 36 vs 30 (correct order), and the thin-perfect cohort moved from mostly-F (27F/15D) to mostly-D (34D/8F) — better matching "flagged, not accused". No other checks regressed; distribution remained discriminating.

### Golden values for test pinning (from the verified run)

| Agent | id | score | grade | confidence |
|-------|----|-------|-------|------------|
| CoinWM Open API | 3118 | 95 | A | high |
| 这个能吃吗？ | 3345 | 94 | A | high |
| CoinAnk OpenAPI | 2013 | 73 | B | medium |
| CertiK | 1965 | 82 | B | high |
| FundingArb | 2169 | 56 | C | medium |
| Coin Oracle | 2177 | 46 | D | low |
| 链上任务助手 | 2791 | 41 | D | low |
| Messari | 3152 | 32 | F | low |
| 链上任务助手 (twin) | 2662 | None | NR | low |
| ASP赛道情报 · NicheScope | 4137 | None | NR | low |

Band edges observed: A/B cut between 85 (id 2438) and 82 (CertiK); B/C between 73 (2013/1718) and 69 (1409); C/D between 55 (1412) and 54 (2543/2161); D/F between 40 (3407/2065) and 39 (3216/2823). Regenerate goldens from the implementation, don't hand-compute (Python `round()` is banker's rounding — half-even).

## Deterministic Serialization Plan

- **Components column:** `json.dumps(components, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` — one object keyed by component name; sorted keys give a stable key order at every nesting level. [VERIFIED: byte-identical across reruns and across processes]
- **Numeric policy:** subscores and final score are `int`; weights are the literal constants (repr-stable); `observed`/`benchmark` carry the raw stored values (floats already fixed by Phase 1 parsing); any *derived* float embedded in JSON must pass through `round(x, 6)`. Reason-string prices use the fixed-decimal formatter (never scientific notation).
- **Rounding:** Python `round()` (IEEE-754 half-even) used consistently; deterministic across CPython platforms. Golden tests pin outputs of the real implementation.
- **Iteration order:** score all agents from `SELECT * FROM agents ORDER BY id`; pools sorted ascending; ties in percentile handled by mid-rank formula — no set/dict iteration feeds any output.
- **CJK safety:** `ensure_ascii=False` + UTF-8 TEXT column round-trips CJK; reason templates themselves contain no listing text.

## Persistence: DDL + refresh wiring

### scores DDL (append to `indexer/db.py`'s `DDL` tuple)

```sql
CREATE TABLE IF NOT EXISTS scores (
    agent_id      TEXT PRIMARY KEY REFERENCES agents(id),
    score         INTEGER,
    grade         TEXT NOT NULL,
    confidence    TEXT NOT NULL,
    score_version TEXT NOT NULL,
    generated_at  TEXT NOT NULL,
    data_as_of    TEXT NOT NULL,
    components    TEXT NOT NULL
)
```

- `score` is nullable — NR rows persist `NULL` + `grade='NR'`. [VERIFIED: round-trips]
- **Grep-gate compliance:** one row per agent is enforced by the primary key — no uniqueness-constraint keyword appears anywhere; keep the uppercase literal "UNIQUE" out of ALL added comments/strings in db.py, refresh.py, and scoring/ (the Phase 1 gate greps db.py; CONTEXT extends it to files matched by the 01-03 gates). Write "one row per agent via primary key" in comments instead. [VERIFIED: `"UNIQUE" not in SCORES_DDL`]
- FK enforcement is already ON via `connect()` — inserting a score for a nonexistent agent raises `IntegrityError`. [VERIFIED]

### Write pattern (scoring/persist.py)

```python
INSERT_SCORE = (
    "INSERT INTO scores (agent_id, score, grade, confidence, score_version,"
    " generated_at, data_as_of, components) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)

def compute_all(conn, generated_at: str, data_as_of: str) -> tuple[int, int]:
    """Score every agent and rewrite the scores table. Caller owns the transaction."""
    rows = [dict(r) for r in conn.execute("SELECT * FROM agents ORDER BY id")]
    snap = dict(conn.execute(
        "SELECT agent_id, COUNT(DISTINCT captured_at) FROM snapshots GROUP BY agent_id"))
    stats = build_stats(rows)
    conn.execute("DELETE FROM scores")          # self-cleaning: vanished agents leave no stale rows
    ...per-agent INSERT with parameterized values...
```

- No commit inside (same contract as `upsert_agent`); parameterized SQL only.
- Full compute+persist for 272 agents: **30ms**. [VERIFIED]

### refresh.py wiring (preserves exit-code contract + determinism)

- Call `compute_all(conn, generated_at, captured_at)` inside `_persist_records`, within the existing `with conn:` block, after `persist(...)` — agents+snapshots+scores become one atomic transaction, and sqlite errors flow to the existing `except (OSError, sqlite3.Error)` in `main()` → exit 2. No new exit codes.
- `generated_at`: injected, never wall clock (locked). Default `generated_at = captured_at` (byte-identical reruns for the seed census); optionally add `--generated-at` CLI flag for operators. For the seed data: `generated_at == data_as_of == "2026-07-10T00:00:00Z"`.
- Logging: add one INFO line from `indexer.refresh` (e.g. `"scores computed: 121 scored, 151 not rated, version=1.0.0"`). Existing caplog tests filter on logger `indexer.census` + WARNING only — unaffected. [VERIFIED: tests/test_refresh.py:232-264]
- `RefreshSummary`: either leave untouched (recommended-minimal) or append fields **with defaults** (`scored: int = 0`, `not_rated: int = 0`) — existing tests assert attributes only, never construct it. [VERIFIED: grep]
- Existing schema test uses `{"agents", "snapshots"} <= tables` (subset) — additive scores table breaks nothing. [VERIFIED: tests/test_db.py:53]
- NOTE: after wiring, `tests/test_refresh.py::test_cli_main` (bare run over the real census) will exercise the full scoring path — any scoring crash breaks the existing suite. The dry-run proves the formulas handle all 272 real rows.

## Coverage Plan (SCOR-04) — sandbox-verified

### pyproject.toml changes

```toml
[tool.setuptools]
packages = ["indexer", "scoring"]          # comment already reserves this

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=scoring --cov-report=term-missing --cov-fail-under=90"
```

No `[tool.coverage.run]` section needed — `--cov=scoring` alone scopes measurement to the `scoring` package (indexer/tests don't dilute or inflate the number). [VERIFIED: sandbox]

### Verified behavior matrix

| Scenario | Result | Consequence for planning |
|----------|--------|--------------------------|
| Full `python -m pytest` with scoring package + its tests | Gate green; only scoring/ files in report; 100% shown for fully-covered sandbox | This is the SCOR-04 acceptance command |
| Subset run not importing scoring (`pytest tests/test_parse.py`) | Tests pass but run FAILS: "Required test coverage of 90% not reached. Total coverage: 0.00%" | Known footgun — document `--no-cov` for partial runs in the plan |
| Subset with `--no-cov` | Clean pass | The documented escape hatch |
| addopts present but scoring/ package absent | Existing tests fail (0% coverage → gate) or collection error if tests import scoring | **Sequencing constraint: the pyproject addopts change MUST land in the same plan/commit as the scoring package and its first tests, never earlier** |

Current baseline: 78 tests pass in 5.63s with no gate. pytest-cov 7.1.0 + pytest 9.1.1 installed and compatible. [VERIFIED: this environment]

Coverage reach: `scoring/` is pure functions + one thin persist module — table-driven tests over the formula spec plus one integration test through `compute_all` on a tmp_path DB will clear 90% comfortably. Only the C5 ≥2-snapshot future branch risks dead code — keep it to the degradation branch + a seam, or cover the future branch with a synthetic two-snapshot fixture (recommended: synthetic fixture, since `insert_snapshot` makes two-captured_at DBs trivial to build).

## Banned-Vocabulary Test Design (SCOR-03)

Regex: `re.compile(r"(?i)(fraud|scam|fake|manipulat)")` — covers all casings and `manipulat*` stems.

Two enforcement layers, both required by CONTEXT:

1. **Source scan:** read every file under `scoring/` as raw text; assert no match. Catches templates, comments, and any string constant. (The test file itself lives in `tests/` — outside the scanned tree, so the regex literal doesn't self-trip.)
2. **Rendered scan over all 272 real agents:** load the census via `indexer.census.load_census()` (offline, deterministic — same pattern tests/test_category.py already uses), build rows + stats, render every full score card (serialized components + grade + confidence + any disclaimer/envelope constants), assert no match on each.

Verified feasibility: the v2 prototype rendered all 272 cards with **0 hits**. Two structural guarantees keep it that way: reason templates never interpolate agent names/taglines (id 2361's tagline contains a banned substring — the passthrough of listing text is Phase 3's concern, outside scoring outputs), and category names (the only non-numeric interpolation) are the 9 fixed bucket names, all clean.

Also scan the `DISCLAIMER` constant and any grade-band description strings shipped in `scoring/`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Deterministic JSON | custom key-ordering serializer | `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)` | stdlib is already canonical + byte-stable |
| Percentiles | numpy/scipy/statistics.quantiles | 4-line mid-rank formula over a sorted list | unlisted deps banned; `statistics.quantiles` interpolation semantics are overkill and harder to pin |
| Schema migration for scores | ALTER/migration machinery | append to the existing `DDL` tuple (CREATE IF NOT EXISTS) | locked mechanism; init_db is already idempotent |
| Score-row freshness management | upsert + staleness tracking | DELETE all + INSERT all per refresh in one transaction | 272 rows, 30ms; self-cleaning |
| Clock handling | freezegun/monkeypatching now() | `generated_at`/`as_of` as explicit parameters | locked: no wall-clock reads in scoring/ or indexer/ |

**Key insight:** this phase's entire dependency surface is the stdlib; every "library decision" is really a determinism decision.

## Common Pitfalls

### Pitfall 1: Counting snapshot rows instead of distinct capture times
**What goes wrong:** the live DB already holds 1632 snapshot rows for 272 agents (six refresh runs, same captured_at — duplication is locked Phase 1 behavior). Naive `COUNT(*) ≥ 2` would unlock velocity/age on fabricated history.
**How to avoid:** `COUNT(DISTINCT captured_at)` per agent (verified = 1 for all agents today).
**Warning signs:** any velocity/age subscore that is not the insufficient-history state on current data.

### Pitfall 2: Coverage gate lands before the scoring package
**What goes wrong:** adding `addopts = "--cov=scoring --cov-fail-under=90"` in a plan that precedes the scoring code makes the existing 78 tests fail at 0% coverage (sandbox-verified).
**How to avoid:** one plan delivers scoring package + scoring tests + pyproject change together (or pyproject last).

### Pitfall 3: Punitive subscores on thin evidence invert rankings
**What goes wrong:** v1's floorless credibility ranked a 5.0/100%-positive/1-sale agent below an unrated 1-sale agent.
**How to avoid:** CRED_FLOOR=0.30 (v2, verified); the *flag* carries the warning, the subscore stays near neutral.
**Warning signs:** any rated agent scoring below an otherwise-identical unrated agent.

### Pitfall 4: Banker's rounding surprises in golden tests
**What goes wrong:** hand-computed expected values disagree with `round()` (half-even: `round(68.5)=68`).
**How to avoid:** generate golden values by running the implementation once, review them against this document's table, then pin.

### Pitfall 5: Listing text leaking into reasons
**What goes wrong:** interpolating name/tagline into a reason string can (a) trip the banned-vocab gate (id 2361), (b) inject newlines/CJK into logs, (c) turn a neutral observation into an implied statement about a named vendor.
**How to avoid:** reasons = fixed templates + numbers + category names only; the banned-vocab rendered-scan over all 272 agents enforces it permanently.

### Pitfall 6: Scientific notation in user-facing numbers
**What goes wrong:** `f"{1.5e-05:g}"` renders "1.5e-05" in a reason string (the real price of agent 2023).
**How to avoid:** `f"{p:.8f}".rstrip("0").rstrip(".")` (verified renders "0.000015").

### Pitfall 7: The uppercase literal gate
**What goes wrong:** a comment like "no UNIQUE constraint here" in db.py (or other 01-03-gated files) breaks the inherited grep gate even though the DDL is clean.
**How to avoid:** primary key gives one-row-per-agent without the keyword; phrase comments in lowercase or alternative wording (Phase 1 already did this — keep it).

### Pitfall 8: Fabricating "insufficient" states as errors or zeros
**What goes wrong:** treating NR/None components as 0 silently drags weighted scores; treating NR agents as errors breaks Phase 3's "NR is a successful response" contract.
**How to avoid:** `score: None` + weight renormalization + NR persists a full row with `score NULL` (verified round-trip).

## Code Examples

### Deterministic mid-rank percentile (ties-stable)

```python
# verified against all 9 category pools (this session)
def percentile(pool: list[float], value: float) -> float:
    """pool must be sorted ascending; self-inclusive mid-rank; deterministic under ties."""
    less = sum(1 for x in pool if x < value)
    equal = sum(1 for x in pool if x == value)
    return (less + 0.5 * equal) / len(pool)
```

### Log-anchored scale

```python
def log_scale(value: float, ref: float) -> float:
    """0 at value=0, 1.0 at value>=ref, log-shaped between."""
    return min(1.0, math.log10(1 + value) / math.log10(1 + ref))
```

### Deterministic serialization + banned-vocab gate (test side)

```python
BANNED = re.compile(r"(?i)(fraud|scam|fake|manipulat)")

def serialize_components(components: dict) -> str:
    return json.dumps(components, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

# rendered-scan pattern (verified 0 hits over 272 agents):
for row in rows:
    card = serialize_components(comps) + grade + confidence + DISCLAIMER
    assert not BANNED.search(card), row["id"]
```

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Always-return-a-number scoring | Explicit NR + confidence (BBB/Fakespot convention, locked in FEATURES) | 151 of 272 agents are honestly NR instead of fabricated mid-scores |
| Opaque single score | Component breakdown + FICO-style reasons with observed-vs-benchmark numbers | Already locked; formulas above emit `{score, weight, observed, benchmark, reason}` per component |
| Wall-clock age scoring | Injected `as_of`/`generated_at` + snapshot-derived history | Deterministic reruns; locked by CONTEXT and PITFALLS research |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Rating display on okx.ai implies review activity exists (rating presence is a valid review-signal proxy) | Component 2 | LOW — reasons only state display facts ("no displayed rating despite N sold"), true regardless of the platform's display rule. [ASSUMED from data pattern: rating always co-occurs with positive% except one row] |
| A2 | Weights/bands (0.30/0.20/0.25/0.15/0.10; 85/70/55/40) are tuned to THIS snapshot; future censuses may shift the distribution | Constants | LOW — locked discretion area; any change bumps `score_version` (locked policy). Distribution re-check belongs in any future data-refresh phase |
| A3 | The ≥2-snapshot velocity/age design (deltas + log-age) is unvalidated — no multi-snapshot data exists | Components 1, 5 | NONE for v1 (unreachable branch, deferred by CONTEXT); design seam only |

All other claims in this document are `[VERIFIED]` by execution against the real database or the real test suite in this session.

## Open Questions

1. **Reason-template final wording polish** — discretion area; the dry-run wording is functional but e.g. "positive-review share not shown on the listing" can be improved. Recommendation: planner freezes templates in components.py; the banned-vocab + golden tests then pin them.
2. **`--generated-at` CLI flag on refresh** — recommended (default `captured_at` keeps determinism) but optional; scores are correct either way. Decide in planning.
3. **RefreshSummary extension vs separate log line** — both verified safe; recommend the minimal separate INFO line, leaving the frozen dataclass untouched.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | everything | ✓ | 3.14.2 | — (satisfies >=3.11) |
| pytest | SCOR-04 gate | ✓ | 9.1.1 | — |
| pytest-cov | SCOR-04 gate | ✓ | 7.1.0 | — |
| sqlite3 (stdlib) | persistence | ✓ | stdlib | — |
| data/trustlens.db | dry-runs/integration tests | ✓ (built this session: 272 agents) | — | rebuild via `python -m indexer.refresh` |

**Missing dependencies:** none.

## Security Domain

### Applicable ASVS Categories (Level 1; offline computation module)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | offline module; no auth surface |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes | inputs are Phase-1-validated DB rows; formulas must tolerate NULLs (rating/positive_pct/price) and extreme values without raising — verified over all real rows incl. 0.0 prices and 0% positive |
| V6 Cryptography | no | none needed; do not hand-roll any |
| V8 Data Protection | yes | scores derive only from public marketplace data; no secrets touched; DB stays gitignored |

### Known Threat Patterns for this module

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via agent fields | Tampering | Parameterized `?` placeholders only (locked; Phase 1 test suite already round-trips `"Rob'); DROP TABLE agents;--"`) |
| Log/output injection via listing text (names/taglines carry newlines, CJK, banned words) | Tampering/Repudiation | Reasons never interpolate listing text; refresh logging keeps the Phase 1 row+id-only convention |
| Defamation via output wording (the phase's dominant real-world risk) | Information disclosure (legal) | Banned-vocab dual-layer test (source + 272 rendered cards); observed-vs-benchmark phrasing; flags describe data patterns, never intent |
| Nondeterministic paid outputs (billing disputes) | Repudiation | Pure functions, injected timestamps, byte-identical serialization — all verified |

## Sources

### Primary (HIGH confidence — direct execution this session)
- `data/trustlens.db` built via `python -m indexer.refresh` (272 agents) — all distributions, cohorts, dry-run scores, rerun byte-identity, FK behavior, 30ms timing
- Dry-run prototypes v1/v2 (scratchpad `scoring_proto.py` / `scoring_proto_v2.py`) — grade distributions, top/bottom rankings, sanity checks, banned-vocab scan
- Coverage sandbox (scratchpad `covbox/`) — 4-case pytest-cov gate behavior matrix
- Live repo: `indexer/db.py`, `indexer/refresh.py`, `indexer/parse.py`, `indexer/census.py`, `indexer/category.py`, `indexer/models.py`, `tests/test_db.py`, `tests/test_refresh.py`, `pyproject.toml` — integration surface + existing-test compatibility
- `python -m pytest -q` → 78 passed; `pip show pytest-cov` → 7.1.0

### Secondary (HIGH confidence — project canon, previously verified)
- `.planning/phases/02-scoring-engine/02-CONTEXT.md` — locked decisions (constraints copied verbatim above)
- `.planning/research/FEATURES.md` — credibility envelope, NR-as-success, neutral-vocabulary conventions (SecurityScorecard/BBB/Fakespot/ReviewMeta patterns)
- `.planning/research/ARCHITECTURE.md` — precompute-on-refresh, writer/reader split, scoring purity anti-patterns
- `.planning/research/PITFALLS.md` — clock injection (Pitfall 11), banned-words shield, coverage-gate traps
- `.planning/phases/01-foundation-data-indexer/01-VERIFICATION.md` — verified field-state counts (90/182 rated, 28 NULL prices, edge-row values)

### Tertiary
- none — no external web claims were needed; every decision is grounded in executed evidence or locked project canon

## Metadata

**Confidence breakdown:**
- Formulas & distribution: HIGH — executed over all 272 real agents, two iterations, cross-process byte-identical
- Persistence & wiring: HIGH — DDL + DELETE/INSERT + FK + rerun idempotence simulated on a scratch DB copy; existing-test compatibility grep-verified
- Coverage gate: HIGH — sandbox-verified in four scenarios in the real environment
- Future multi-snapshot velocity/age: LOW by necessity — no data exists; deferred by CONTEXT, only the degradation branch ships

**Research date:** 2026-07-11
**Valid until:** stable for the v1 build (data snapshot is frozen at 2026-07-10); re-run the dry-run distribution check if a new census/scrape lands before formulas are pinned
