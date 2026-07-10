# Phase 2: Scoring Engine - Context

**Gathered:** 2026-07-10
**Status:** Ready for planning
**Source:** PRD Express Path (../trustlens-claude-code-prompt.md) + Phase 1 empirical realities

<domain>
## Phase Boundary

Deliver `scoring/` — pure, deterministic, unit-tested functions producing a 0–100 TrustScore + A–F grade + component breakdown for any indexed agent, persisted to a `scores` table by the refresh pipeline (precompute-on-refresh per locked architecture). Requirements: SCOR-01, SCOR-02, SCOR-03, SCOR-04. The MCP server that serves these scores is Phase 3.

</domain>

<decisions>
## Implementation Decisions

### Component set (locked verbatim from the brief)
1. **Sales volume & velocity**
2. **Review-count-vs-sales ratio**
3. **Rating credibility** — "5.0 with <5 sales = low confidence, flagged not accused"
4. **Price-vs-category percentile** (uses Phase 1's derived categories)
5. **Listing age/consistency**
Every component returns a `reason` string. Component list is fixed — do not add or remove components.

### Data reality constraints (locked — from Phase 1 empirical work)
- Census provides NO review counts and NO listing ages. Components 2 and 5 MUST be defined over what actually exists: rating presence/positive_pct/sold for the review-signal ratio; snapshots history (first_seen/last_seen, snapshot series) for age/consistency. On the first snapshot, history-dependent signals MUST degrade to an explicit "insufficient history" state — never fabricate.
- Known field states over the 272 real agents: 90 rated / 182 unrated (rating echo rule), 28 NULL prices, sold ranges 0–1550, categories per the pinned 9-bucket distribution (70/45/41/30/27/22/17/15/5).
- All inputs come from the SQLite DB via Phase 1 modules (`indexer.db.connect()` etc.); scoring functions themselves are pure (take plain rows/values, no I/O, no wall clock — `as_of`/`generated_at` injected by callers).

### Credibility envelope (locked — from project FEATURES research)
- Dual encoding: integer 0–100 + letter grade A–F with published band thresholds (exact bands are discretion but MUST be constants, documented, and test-pinned)
- Explicit **NR ("Not Rated / insufficient data") state** plus a per-score `confidence` field (e.g. high/medium/low) instead of guessing on thin rows
- Versioned scoring: a `score_version` constant embedded in every output; bump on any formula/weight change
- Dual timestamps in outputs: `generated_at` (injected at compute time) and `data_as_of` (snapshot captured_at)
- Per-response disclaimer string: statistical estimate over public marketplace data, not a statement of fact

### Neutral language (locked — SCOR-03)
- Fixed reason vocabulary: factual observations with observed-vs-benchmark numbers ("pattern consistent with…", "outside category norm (X vs median Y)", "insufficient data")
- BANNED anywhere in scoring output or code strings: "fraud", "scam", "fake", "manipulat*" (any casing) — enforce with a banned-vocabulary test over all reason templates and rendered outputs for all 272 agents
- Flags describe data patterns, never seller intent or guilt

### Persistence (locked)
- `scores` table added via the additive DDL mechanism in `indexer/db.py`'s pattern (CREATE IF NOT EXISTS tuple); columns must carry: agent_id, score, grade, confidence, score_version, generated_at, data_as_of, components JSON (deterministically serialized: sorted keys, fixed float formatting)
- Refresh pipeline computes and persists scores for all agents after indexing (wire into `indexer/refresh.py` refresh flow without breaking its exit-code contract or determinism)
- CRITICAL inherited gate: comments/strings in any file matched by the 01-03 grep gates must not contain the uppercase literal "UNIQUE"; keep parameterized SQL only; no wall-clock reads inside scoring/ or indexer/

### Determinism & coverage (locked — SCOR-01, SCOR-04)
- Same row + same category stats + same as_of → byte-identical output (stable ordering, explicit rounding)
- pytest coverage ≥90% on `scoring/` enforced via pyproject config (`--cov=scoring --cov-fail-under=90` per STACK.md pattern) — the gate must run as plain `python -m pytest`
- Edge cases with explicit tests: 0 sales, missing rating, missing price, "1.55K"-derived 1550 sold, NR state, first-snapshot insufficient-history

### Git & conduct (locked)
- Commits authored by the user's git identity only; NEVER any AI attribution
- Conventional commits per task (`feat(02-XX): …`); 2-attempt stop rule on unresolved errors

### Claude's Discretion
- Exact weights, band thresholds, and formulas (must be constants, documented in code, and test-pinned; researcher should dry-run candidates against the real 272-agent DB to avoid degenerate distributions)
- Module layout inside `scoring/` (e.g. components.py / engine.py / persist.py)
- Confidence-level rubric details
- Reason string templates (within the locked vocabulary)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project & requirements
- `.planning/PROJECT.md` — constraints, stop conditions
- `.planning/REQUIREMENTS.md` — SCOR-01..04 definitions

### Research
- `.planning/research/FEATURES.md` — credibility envelope, neutral-vocabulary patterns, anti-features
- `.planning/research/ARCHITECTURE.md` — precompute-on-refresh, scores table, writer/reader split
- `.planning/research/PITFALLS.md` — clock injection, coverage-gate traps

### Phase 1 outputs (the substrate)
- `indexer/models.py`, `indexer/parse.py`, `indexer/category.py`, `indexer/db.py`, `indexer/census.py`, `indexer/refresh.py` — import, don't reimplement
- `.planning/phases/01-foundation-data-indexer/01-VERIFICATION.md` — verified field-state counts
- `data/okx-marketplace-census-2026-07-10.csv` — real data for dry-runs

</canonical_refs>

<specifics>
## Specific Ideas

- Brief verbatim: "rating credibility (5.0 with <5 sales = low confidence, flagged not accused)"; "Every component returns a `reason` string"; wording "NEVER accusatory"
- Acceptance: `pytest` passes with ≥90% coverage on `scoring/`
- Downstream (Phase 3) will serve: score card JSON per agent (score, grade, components with reasons, confidence, score_version, generated_at, data_as_of, methodology_url) — design the persisted shape so Phase 3 can serve it without recomputation
- Dry-run requirement: whatever formulas are chosen must be executed against the full real DB during research/planning; the resulting score distribution must discriminate (not all agents in one grade) and top/bottom agents must be explainable

</specifics>

<deferred>
## Deferred Ideas

- Longitudinal velocity/consistency signals from recurring scrapes — v2 (INDX-05); v1 degrades gracefully
- Real review-count data from agent detail pages — Phase 5 scraper may enrich; design the component to accept it when present

</deferred>

---

*Phase: 02-scoring-engine*
*Context gathered: 2026-07-10 via PRD Express Path*
