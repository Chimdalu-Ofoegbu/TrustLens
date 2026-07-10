# Feature Research

**Domain:** Marketplace trust/reputation scoring sold as a paid agent-callable data API (A2MCP on OKX.AI)
**Researched:** 2026-07-10
**Confidence:** HIGH

**Scope note:** The product surface is FIXED by the brief (4 MCP tools: `score_agent`, `compare_agents`, `category_leaderboard`, `marketplace_stats`; static leaderboard page; badge snippet; 0.01 USDT/call). This research answers what makes that surface *credible and complete*, drawn from established trust-score products: SecurityScorecard, FICO/VantageScore, BBB, Fakespot, ReviewMeta, Trustpilot, GoPlus. Table stakes here = conventions those products treat as non-negotiable in outputs and presentation.

## Feature Landscape

### Table Stakes (Users Expect These)

Every established trust-score product converges on the same output envelope. Missing any of these makes the score look amateur or legally careless.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Dual score encoding: 0–100 integer + A–F letter grade | Industry-wide convention: SecurityScorecard maps 100–0 to A–F (F = ≤60); BBB scores 100 points → A+–F; Fakespot grades A–F. Numbers for machines, grades for humans | LOW | Integer score (no decimals — false precision). Fixed, published band thresholds (e.g. A=90–100 … F=<60) |
| Published grade-band interpretation | Users must know what "B" means. SecurityScorecard publishes breach-likelihood per band; Fakespot documents "A/B = reliable, C = mixed, D/F = insufficient reliable reviews" | LOW | One table on methodology section + repeated in tool descriptions |
| Per-component breakdown with individual sub-scores | SecurityScorecard: 10 factors each scored; BBB: 13 rating elements; FICO: score factors. A single opaque number is not credible | MEDIUM | The 5 prescribed components (sales volume/velocity, review-vs-sales ratio, rating credibility, price-vs-category percentile, listing age/consistency), each with score + weight |
| FICO-style reason strings per component, ordered by impact | Credit-industry norm (legally mandated for credit via ECOA adverse-action codes): ranked plain-language "why the score is what it is". myFICO lists factors most-influential-first | MEDIUM | Neutral template strings per component, e.g. "Review count is high relative to units sold (ratio 3.2 vs category median 0.8)". Deterministic templates, not free text |
| Confidence field + explicit "insufficient data" state | BBB assigns "NR (Not Rated)" when information is insufficient rather than guessing; Fakespot D/F literally means "insufficient reliable reviews". Scoring thin data as if complete destroys credibility | MEDIUM | `confidence: high/medium/low` + grade `NR` (or `INSUFFICIENT_DATA`) when inputs are missing (e.g. census rows with missing ratings). NR is a *successful* response, not an error |
| Public methodology page | Every credible scorer publishes one: SecurityScorecard's Scoring Methodology deep-dive, BBB's "Overview of Ratings", Trustpilot's TrustScore explanation. Black-box scores read as arbitrary | LOW | Methodology section on the leaderboard page (already in brief): components, weights, band table, data sources, update cadence, limitations |
| Versioned scoring model (`score_version`) | Credit scores are versioned (FICO 8/9/10, VantageScore 3.0/4.0); SecurityScorecard methodology 3.0. Consumers must know which formula produced a number | LOW | Constant like `"1.0.0"` in every response; bump on any formula/weight change; note version on methodology page |
| `generated_at` + `data_as_of` timestamps | SecurityScorecard: "every score backed by data — view the specific finding and timestamp". Paid API consumers need freshness to decide cache vs re-buy | LOW | `generated_at` = response time (ISO 8601 UTC); `data_as_of` = snapshot date of census/scrape. Two fields, not one — score is computed from a snapshot |
| Deterministic output: same input + same snapshot → identical JSON | Paid data APIs at $0.001–$0.01/call sell reproducibility. An agent paying per call must be able to verify, cache, and compare results; non-determinism = billing disputes | MEDIUM | Pure-function scoring over SQLite snapshot. No LLM in the response path. Stable sort orders + deterministic tie-breaks (score desc, then agent id) in leaderboard/compare |
| MCP `outputSchema` + `structuredContent` on all 4 tools | MCP spec (2025-06-18): if `outputSchema` is declared, "Servers MUST provide structured results that conform to this schema"; structured content SHOULD also be serialized into a text block for backwards compat. Agent callers parse schemas, not prose | MEDIUM | FastMCP generates output schemas from return-type annotations. Fixed key set, no optional-key surprises; `null` + reason over absent keys |
| Per-response neutral disclaimer + methodology link | ReviewMeta prints on every analysis: results are "an ESTIMATE, and not a statement of fact" and "do not necessarily prove the presence or absence of 'fake' reviews". This is the defamation shield | LOW | One constant string in every JSON response: score "reflects statistical patterns in public marketplace data; it is not an allegation of misconduct" + methodology URL |
| Neutral analytics wording for anomaly flags | Fakespot scores *review reliability*, explicitly "does not give an opinion on the … company"; ReviewMeta reports PASS/WARN/FAIL on named statistical *tests*. Opinions based on disclosed facts are defamation-protected; accusations of fact are not | MEDIUM | Fixed vocabulary: "pattern consistent with…", "outside category norm (observed X vs median Y)", "insufficient data to evaluate". Always show the numbers behind the flag. Never "fraud/scam/fake/manipulated" |
| Marketplace-rating passthrough alongside TrustScore | Fakespot/ReviewMeta always show the platform rating next to their grade — the score *contextualizes* the marketplace, never silently replaces it | LOW | Echo okx.ai rating, positive %, units sold, price in `score_agent` responses; agents shouldn't need a second call for basics |
| Leaderboard credibility furniture | Trust sites show data recency and coverage or are assumed stale: last-updated stamp, N agents covered, link to source listing | LOW | "272 agents · data as of 2026-07-10 · methodology v1.0.0" header; each row links to `okx.ai/agents/<id>` |
| Badge that links back to a live, verifiable score page | Trustpilot TrustBox and shields.io convention: badge = image + hyperlink to the profile/score it claims. An unlinked badge is unverifiable and worthless | LOW | Self-hosted SVG per agent (`/badge/<id>.svg` showing grade + score) + copy-paste HTML and Markdown snippets `[![TrustLens B 82](…/badge/3345.svg)](…/#agent-3345)` |
| Distinct error vs no-data semantics | MCP spec separates protocol errors, tool-execution errors (`isError: true`), and valid results. Unknown agent id = execution error; known agent with thin data = valid NR response | LOW | Error payloads also deterministic and schema-conforming |

### Differentiators (Competitive Advantage)

Directly against the named competition: Factor Credit Desk/Bureau (agent *creditworthiness* for lending), TO1 Intelligence (raw wash-trade/uptime *data feeds*), Internet Court MCP (dispute *arbitration*).

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| One-call hiring verdict (score + grade + reasons in a single deterministic JSON) | Factor answers "will it repay?", TO1 sells raw signals you must interpret, Internet Court acts after a dispute. TrustLens answers the pre-purchase question "should I hire this agent?" in one 0.01 USDT call — cheapest possible integration for a buying agent | Already in scope | This is the positioning; bake it into tool descriptions and listing copy |
| `compare_agents` head-to-head with per-component winners | Credit bureaus and data feeds don't do decision-support comparison. An agent choosing between two similar services gets a direct, explainable tiebreak | LOW (reuses scorer) | Deterministic winner logic + "differs on: …" reason strings; ties broken explicitly and stated |
| Category-relative scoring (price percentile, ratio vs category median) | Absolute thresholds misfire across categories; percentile context ("price is P85 for its category") is how SecurityScorecard normalizes (z-scores vs similar-size footprints). Makes reasons quantitative and fair | MEDIUM | Needs category extraction + per-category medians in SQLite; also powers `category_leaderboard` |
| Confidence-aware scoring as a first-class output | Most marketplace scores hide uncertainty. Explicit confidence + NR handling turns the census's known dirty rows (missing ratings, "1.55K sold" parsing) into a demonstrable strength during demo | MEDIUM | Confidence derives from field completeness + parse quality per agent |
| Evidence-linked reason codes (credit-bureau UX applied to agent marketplace) | FICO-style ranked reasons with observed-vs-benchmark numbers are rare outside credit. Judges and buyers can audit every point of the score | MEDIUM | Every component: `{score, weight, observed, benchmark, reason}` |
| Free leaderboard as funnel for the paid API | Fakespot/ReviewMeta model: free human-facing checker drives adoption; the paid surface is the machine API. Leaderboard doubles as live demo + marketing | Already in scope | Leaderboard shows grades free; per-agent JSON detail is the paid call |
| Badge = zero-cost distribution loop | Agents embedding "TrustLens Verified B (82)" advertise TrustLens on their own listings; clicks land on the leaderboard; verification calls are paid | LOW | Ship the snippet generator on the leaderboard; grade+score in badge, shields.io visual style |
| Reproducibility guarantee as a paid-API promise | `score_version` + `data_as_of` + deterministic engine = "same call, same snapshot, same bytes". Sellable trust property no LLM-backed competitor can match; also makes ≥90% test coverage straightforward | LOW (falls out of table stakes) | State the guarantee in methodology + listing copy |
| `marketplace_stats` as the macro credibility view | Mirrors SecurityScorecard's industry reports: distribution of grades, category counts, median prices. Gives journalists/judges a one-call ecosystem summary nobody else on OKX.AI sells | LOW | Aggregates over SQLite; fully deterministic |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Accusatory labels ("fraud", "scam", "fake reviews detected", "manipulated") | Punchy demo copy; feels decisive | Defamation exposure: false statements of fact about named businesses are actionable; every surviving product (Fakespot, ReviewMeta) scores *data reliability*, never seller guilt. Also banned by PROJECT.md | Fixed neutral vocabulary: "pattern consistent with…", "ratio outside category norm (X vs median Y)", "insufficient data to evaluate" + per-response disclaimer |
| LLM-generated verdict prose in API responses | "AI product" appeal for an AI hackathon | Non-deterministic paid outputs = unverifiable billing, uncacheable results, untestable to 90% coverage; injects hallucination risk into a *trust* product | Deterministic template reason strings; keep AI framing in the pitch ("built for agents"), not the response path |
| "Safe to hire" / "Verified safe" endorsements or guarantees | Buyers want a yes/no | Converts a statistical opinion into a warranty; FICO explicitly frames reason codes as "why the score isn't higher", never "why you were denied". "TrustLens Verified" must mean "scored by TrustLens", not "endorsed by TrustLens" | Score + grade + confidence + published methodology; badge text shows grade/score, methodology page defines what verification means |
| Scoring thin-data agents anyway (always return a number) | "Every agent should have a score" — complete-looking leaderboard | A confident 50/100 on garbage input is indistinguishable from a real 50; one obviously-wrong score poisons trust in all scores | BBB-style `NR` + `insufficient_data` reasons; leaderboard shows NR rows unranked at bottom |
| Live re-scrape of okx.ai per paid call | "Freshest data per call" | 1 req/s politeness cap makes calls slow/flaky; same call minutes apart returns different bytes (breaks reproducibility); hammers okx.ai | Score from the SQLite snapshot; expose `data_as_of`; refresh via offline/scheduled polite scrape |
| Adjusted/"true" rating that removes "fake" reviews (ReviewMeta-style) | Familiar, dramatic before/after | Implies specific reviews are fake = implicit accusation; requires review-level data the census doesn't have | "Rating credibility" *component* scoring the plausibility of the rating-vs-sales relationship, with observed numbers |
| Pay-to-improve, dispute-for-fee, or seller-paid placement | Obvious revenue line | Structural conflict of interest — the core criticism BBB has faced for years; instantly discredits the score | Revenue stays per-call only; methodology page states "agents cannot pay to alter scores" |
| Extra tools/surfaces (webhooks, alerts, history API, auth, accounts, admin) | Feels more "complete" | Brief fixes the surface at 4 tools; every addition dilutes the 7-day timeline and violates scope discipline | Ship the 4 tools well; list ideas in listing-copy roadmap section if needed |
| Decimal-precision scores (82.37) | Looks rigorous | False precision the underlying census data cannot support; all reference products present integers/letter bands | Integer 0–100 + grade + confidence |
| Third-party badge dependency (shields.io endpoint as the only badge) | Zero SVG work | External dependency + latency on your credibility artifact; endpoint badge JSON is a shields.io-specific contract | Self-host tiny SVG (template string, ~30 lines); optionally *also* document shields.io endpoint compatibility later |

## Feature Dependencies

```
Indexer/SQLite snapshot (census CSV + polite scraper)
    └──requires──> nothing (root)

Scoring engine (5 components, pure function)
    └──requires──> Indexer snapshot
                       └──requires──> category medians/percentiles (computed at index time)

Grade bands + confidence/NR state
    └──requires──> Scoring engine

Reason strings (observed vs benchmark, neutral vocabulary)
    └──requires──> Scoring engine components + category benchmarks

score_version / generated_at / data_as_of envelope
    └──requires──> Scoring engine (version constant) + Indexer (snapshot date)

4 MCP tools with outputSchema + structuredContent
    └──requires──> Envelope + reason strings
    └──requires──> x402 layer (402 challenge before serving)

Leaderboard page (ranked table, filters, methodology section)
    └──requires──> Scoring engine + grade bands
    └──enhances──> paid API (marketing funnel)

Badge SVG + embed snippet
    └──requires──> Leaderboard page (link target) + Scoring engine (grade/score)
    └──enhances──> distribution loop back to paid API

Neutral-wording vocabulary + disclaimer ──constrains──> Reason strings, leaderboard copy, badge text, listing copy

Live per-call scraping ──conflicts──> Deterministic outputs + reproducibility guarantee
LLM-generated prose ──conflicts──> outputSchema conformance + testability
```

### Dependency Notes

- **Reason strings require category benchmarks:** neutral wording only works when it cites numbers ("observed 3.2 vs median 0.8") — compute medians/percentiles at index time so responses stay a pure lookup.
- **Badge requires the leaderboard first:** an unlinked badge is unverifiable; the badge href must resolve to a live score.
- **Wording vocabulary is a cross-cutting constraint, not a phase:** define the phrase list + banned-word list before writing any reason string, page copy, or listing copy; enforce with a test that greps outputs for banned words ("fraud", "scam", "fake", "manipulated").
- **Determinism conflicts with live scraping:** scoring must read only the snapshot; the scraper writes a new snapshot (new `data_as_of`) out-of-band.

## MVP Definition

### Launch With (v1)

Everything here is required for the score to be *credible* — the fixed surface with the full conventional envelope.

- [ ] Deterministic scoring engine: 0–100 integer + A–F grade + NR state, 5 components each `{score, weight, observed, benchmark, reason}` — the credibility core
- [ ] Confidence field derived from data completeness; dirty census rows (missing ratings, "1.55K", subscript prices) degrade confidence, never crash
- [ ] Response envelope on all 4 tools: `score_version`, `generated_at`, `data_as_of`, marketplace passthrough fields, constant disclaimer + methodology URL
- [ ] MCP `outputSchema` declared + `structuredContent` returned on all 4 tools (spec MUST when schema declared)
- [ ] Neutral-wording vocabulary + banned-word test — defamation shield across API, site, badge, listing copy
- [ ] Leaderboard: sortable ranked table, category filter, methodology section (components, weights, band table, limitations, "cannot pay to alter scores"), last-updated + coverage header, NR rows unranked
- [ ] Badge: self-hosted SVG per agent + copy-paste HTML/Markdown snippet linking to the agent's leaderboard entry
- [ ] x402 402-challenge flow with `X402_MOCK=1` — the paid-API mechanics the hackathon judges

### Add After Validation (v1.x)

- [ ] shields.io endpoint-format JSON (`/badge/<id>.json`) — trigger: anyone asks for README-ecosystem badges beyond the self-hosted SVG
- [ ] Score deltas ("score changed +4 since last snapshot") — trigger: second scrape snapshot exists; adds freshness narrative to leaderboard
- [ ] Per-component weight tuning against scraped detail pages (review counts, listing age) — trigger: scraper reliably enriches beyond census columns

### Future Consideration (v2+)

- [ ] Correction/inquiry channel for listed agents (BBB/Trustpilot analog) — defer: requires identity verification ≈ auth, explicitly out of scope
- [ ] Historical trend API / webhooks — defer: new surface beyond the fixed 4 tools; needs sustained snapshot history
- [ ] Cross-marketplace coverage — defer: post-hackathon product bet

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Score + grade + component breakdown + reasons | HIGH | MEDIUM | P1 |
| Confidence + NR insufficient-data state | HIGH | MEDIUM | P1 |
| Envelope (version, timestamps, disclaimer, passthrough) | HIGH | LOW | P1 |
| outputSchema + structuredContent on 4 tools | HIGH | MEDIUM | P1 |
| Neutral vocabulary + banned-word test | HIGH (risk shield) | LOW | P1 |
| Methodology section on leaderboard | HIGH | LOW | P1 |
| Badge SVG + embed snippet | MEDIUM | LOW | P1 (in brief) |
| Category-relative benchmarks in reasons | HIGH | MEDIUM | P1 |
| compare_agents per-component winners | MEDIUM | LOW | P1 (in brief) |
| marketplace_stats aggregates | MEDIUM | LOW | P1 (in brief) |
| shields.io endpoint JSON | LOW | LOW | P2 |
| Score deltas between snapshots | MEDIUM | MEDIUM | P2 |
| Correction channel, history API, webhooks | MEDIUM | HIGH | P3 |

## Competitor Feature Analysis

| Feature | Factor Credit Desk/Bureau | TO1 Intelligence | Internet Court MCP | Our Approach |
|---------|---------------------------|------------------|--------------------|--------------|
| Question answered | "Will this agent repay credit?" (lending) | "Here are raw wash-trade/uptime signals" (feeds) | "Who wins this dispute?" (post-hoc arbitration) | "Should I hire this agent?" — pre-purchase, one call |
| Output shape | Credit score for lenders | Raw data streams to interpret | Case rulings | Deterministic JSON verdict: score + grade + ranked reasons + confidence |
| Explainability | Credit-style, lending-oriented | None (buyer interprets) | Narrative ruling | FICO-style reason codes with observed-vs-benchmark numbers, methodology-linked |
| Comparison support | No | No (DIY from feeds) | No | `compare_agents` head-to-head with per-component winners |
| Human-facing surface | Unknown/minimal | Feed docs | Case interface | Free public leaderboard + embeddable badge funnel |
| Reproducibility | Unknown | Feed = point-in-time | Judgment ≠ reproducible | Guaranteed: `score_version` + `data_as_of` + pure-function engine |

## Sources

**Score presentation & methodology transparency (HIGH confidence — official docs):**
- SecurityScorecard scoring: A–F over 0–100, 10 factors, z-score normalization vs similar footprints, evidence-with-timestamp transparency, published methodology PDF — [How SecurityScorecard calculates your scores](https://support.securityscorecard.com/hc/en-us/articles/8366223642651-How-SecurityScorecard-calculates-your-scores), [Methodology Deep Dive 3.0](https://securityscorecard.com/wp-content/uploads/2026/04/MethodologyDeepDive-3.0-Ebook_021026_SD.pdf)
- FICO reason codes: ranked most-influential-first plain-language factors; "indication of why your score isn't higher", ECOA adverse-action context — [myFICO: What Are Credit Score Reason Codes?](https://www.myfico.com/credit-education/blog/reason-codes), [US FICO Score Reason Codes](https://www.fico.com/en/latest-thinking/product-sheet/us-fico-score-reason-codes), [VantageScore ReasonCode](https://vantagescore.com/consumers/reasoncode)
- BBB: 100-point scale → A+–F across 13 elements; "NR (No Rating)" for insufficient information — [BBB Overview of Ratings](https://www.bbb.org/all/overview-of-ratings)

**Review-authenticity wording norms (HIGH for patterns; MEDIUM for legal framing):**
- Fakespot: A–F grades score *review reliability only*; "does not give an opinion on the quality of the product, service, or company" — [Fakespot FAQ](https://www.fakespot.com/faq)
- ReviewMeta: PASS/WARN/FAIL named statistical tests; "does not necessarily prove the presence or absence of 'fake' reviews"; "an ESTIMATE, and not a statement of fact"; shows every test's numbers — [ReviewMeta FAQ](https://reviewmeta.com/blog/faq/), [ReviewMeta](https://reviewmeta.com/)
- Defamation principle (fact vs opinion; avoid accusations, disclose the basis) — [Minc Law: When Are Online Reviews Considered Defamation?](https://www.minclaw.com/when-online-reviews-defamation/), [KJK: Can My Business Sue Over Fake Reviews?](https://kjk.com/2025/10/10/can-my-business-sue-over-negative-or-fake-online-reviews/)

**Deterministic structured output for agent-callable tools (HIGH — official spec, fetched 2026-07-10):**
- MCP 2025-06-18 Tools spec: `outputSchema` declared → "Servers MUST provide structured results that conform to this schema"; `structuredContent` + backwards-compatible serialized text block; `isError` execution-error semantics — [MCP Specification: Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- Crypto-native risk-output convention (factual boolean risk items, severity levels, neutral "detects potential security risks" framing) — [GoPlus Token Security API](https://gopluslabs.io/en/token-security-api), [GoPlus Token Risk Classification](https://whitepaper.gopluslabs.io/goplus-network/user-security-network/security-data-layer/token-risk-classification)

**Badge embed conventions (HIGH — official sources):**
- shields.io: SVG badges embedded via Markdown/HTML image + link; static, dynamic, and endpoint badge types — [shields.io](https://shields.io/), [badges/shields GitHub](https://github.com/badges/shields)
- Trustpilot TrustBox: copy-paste HTML snippet, badge links back to live profile, customizable trust signals — [TrustBox widget overview](https://help.trustpilot.com/s/article/TrustBox-widget-overview?language=en_US), [TrustBox widgets](https://business.trustpilot.com/features/trustbox-widgets)

**Project context:** `.planning/PROJECT.md` (fixed surface, neutral-language constraint, competitor differentiation, census edge cases)

---
*Feature research for: marketplace trust-score A2MCP service (TrustLens)*
*Researched: 2026-07-10*
