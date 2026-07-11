# Phase 5: Scraper, Hardening & Submission Kit - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning
**Source:** PRD Express Path (../trustlens-claude-code-prompt.md) + OKX docs + Phases 1-4 reality

<domain>
## Phase Boundary

The final phase: make TrustLens submission-ready. (a) Polite okx.ai scraper wired into the existing refresh pipeline with graceful CSV fallback (INDX-04); (b) README with local-run/deploy/Inspector/ASP-registration/curl-check/SDK-swap docs (OPS-02); (c) full suite green including the e2e x402-mocked call (OPS-03 — largely satisfied by Phase 4, formalized here); (d) submission kit — demo-script, x-post-draft, listing-copy (SUBM-01..03). Requirements: INDX-04, OPS-02, OPS-03, SUBM-01, SUBM-02, SUBM-03.

</domain>

<decisions>
## Implementation Decisions

### Scraper (locked — INDX-04 verbatim + brief politeness rules)
- New module `indexer/scraper.py`; the CSV remains the PRIMARY seed path (okx.ai 403s bots and is a JS SPA — proven in earlier research). The scraper is the OPTIONAL refresh enrichment, timeboxed ~2h of build effort.
- Politeness (all locked): ≤1 req/sec rate limit; `User-Agent: TrustLens/1.0`; on-disk response cache (e.g. `data/cache/` keyed by URL hash, gitignored); `httpx` sync client (already a dep); `BeautifulSoup(..., "html.parser")` (stdlib backend, no lxml).
- Targets: okx.ai/agents listing + `https://www.okx.ai/agents/<id>` detail pages.
- Graceful degradation is the core deliverable: EVERY failure path — 403/blocked, empty SPA shell (no parseable data), markup change (selectors miss), network error, timeout — logs a WARNING and falls back to census CSV data without crashing. The refresh exit-code contract (0/1/2) and determinism are preserved.
- Integration: the scraper feeds the SAME loader path as the census (source-tagged 'scrape' vs 'census' per the Phase 1 seam); when the scraper yields nothing usable, the census rows stand. A CLI flag gates it (e.g. `python -m indexer.refresh --scrape`); default refresh stays offline/CSV-only so all existing tests and determinism hold.
- Category enrichment: if a detail page yields a real listed category, store it with `category_source='listed'` (the Phase 1 seam) — BUT reasons/leaderboard already treat category as derived; scraped categories are validated against the canonical 9-bucket set (Phase 2 WR-02 fix) before use so scraped text can't break neutral language.
- Tests: canned-response fixtures ONLY (no live network in tests) — feed the parser saved HTML samples + simulate each failure mode (403 response, empty-shell HTML, changed markup, timeout) and assert graceful CSV fallback + warning. Never hit okx.ai in the test suite.

### README (locked — OPS-02 verbatim)
- `README.md` covering, in order: what TrustLens is (neutral framing) + the 4 tools; local run (`pip install -e .[dev]`, `python -m indexer.refresh`, `uvicorn server.main:app --port 8000`); the leaderboard at `/`, `/healthz`, `/mcp`; running tests + the coverage gate; Docker (`docker compose up` — one port; note the entrypoint self-seeds); MCP Inspector test instructions (the exact verified `npx --yes @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/list` command + a tools/call example incl. the CJK-name quirk); the x402 pre-registration curl check verbatim (`curl -i -X POST https://<host>/mcp` → expect 402 + PAYMENT-REQUIRED); env-var config table (all 5 vars, pointing at .env.example); the mock→real-SDK swap (X402_MOCK vs dropping in okxweb3-app-x402 at the PaymentVerifier seam); deploy steps (any HTTPS-capable host; OKX suggests HK/Singapore nodes; needs a public HTTPS domain); and the EXACT OKX ASP registration steps.
- ASP registration section MUST quote verbatim (from OKX docs, in PROJECT.md): install Onchain OS (`npx skills add okx/onchainos-skills --yes -g`), log into the Agentic Wallet, then the two agent prompts — **"Help me register an A2MCP ASP on OKX.AI using Onchain OS"** (fields: service name, description, price per call, endpoint URL) and **"Help me list my ASP on OKX.AI using Onchain OS"** — review completes ≤24h to the registered wallet email. Clearly mark which steps are HUMAN-ONLY (deploy, wallet login, submission) per the stop conditions.
- Neutral analytics language throughout; link the methodology page.

### OPS-03 (locked)
- Confirm/round out the pytest suite: scoring functions (done), MCP tool schemas (done), one e2e call against a local server with x402 mocked (done in Phase 4). This phase ensures the suite is green as a whole and adds the scraper's canned-response tests. No coverage-gate change.

### Submission kit (locked — SUBM-01..03 verbatim)
- `submission/demo-script.md` — 90-second storyboard: problem (can you trust a marketplace agent before paying?) → live MCP call from Claude (score_agent on a real agent) → score card with an anomaly flag (e.g. a 5.0-rating-thin-sales agent shown flagged-not-accused) → agent-calling-agent flow (one agent checks another's TrustScore before hiring) → leaderboard + on-chain revenue (the 0.01 USDT/call settling). Must be executable against a clean-clone `docker compose up`; note the Docker-engine human step.
- `submission/x-post-draft.md` — launch thread with #OKXAI; neutral, factual, no accusations; highlights the one-call hiring-trust verdict + determinism + on-chain pay-per-call.
- `submission/listing-copy.md` — ASP listing fields: name (TrustLens), tagline ≤80 chars (enforce the limit), description, category "Software Services", price 0.01 USDT. Plus the endpoint URL placeholder and the methodology URL.
- All copy uses neutral analytics language; the banned-vocabulary test's spirit applies (no fraud/scam/fake/manipulat anywhere in submission text) — consider extending the test to scan submission/ md files too.

### Stop conditions (locked — reaffirm)
- This phase PREPARES materials; it does NOT deploy, register, post, or fill the hackathon form. The final orchestrator output is the ordered human checklist. The Docker container smoke test (Phase 3 HUMAN-UAT) folds into that checklist.

### Git & conduct (locked)
- Commits authored by the user's git identity only; NEVER any AI attribution; conventional commits `feat(05-XX): ...`
- No new runtime deps; 2-attempt stop rule; scraper build timeboxed (if okx.ai proves fully unscrapeable, the graceful-fallback + canned tests are the deliverable, which is the designed outcome).

### Claude's Discretion
- Scraper module structure, cache key scheme, exact selectors (best-effort; fallback is what's tested)
- README section ordering/formatting within the required content
- Demo-script beat timing; x-post thread length; listing description wording (within neutral-language + char limits)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/PROJECT.md` — OKX ASP registration prompts (verbatim), scraper politeness rules, x402 facts, stop conditions
- `.planning/REQUIREMENTS.md` — INDX-04, OPS-02, OPS-03, SUBM-01..03 verbatim
- `.planning/research/PITFALLS.md` — scraper design (okx.ai 403s/SPA), CSV-primary rationale
- `.planning/research/FEATURES.md` — differentiation vs Factor/TO1/Internet Court (for demo + listing copy), badge/methodology norms
- `indexer/census.py`, `indexer/refresh.py` — the loader seam the scraper feeds; source-tagging; exit-code contract to preserve
- `indexer/category.py` — CANONICAL_CATEGORIES for validating scraped categories
- `server/main.py`, `Dockerfile`, `docker-compose.yml`, `.env.example` — referenced by the README
- `.planning/phases/03-mcp-server-leaderboard/03-HUMAN-UAT.md` — the Docker smoke test that folds into the final checklist
- `.planning/phases/04-x402-payment-layer/04-VERIFICATION.md` — the verified curl check + Inspector commands to quote in README

</canonical_refs>

<specifics>
## Specific Ideas

- Brief verbatim: "README with: local run, deploy steps (any HTTPS-capable host; OKX docs suggest HK/Singapore nodes), MCP Inspector test instructions, and the exact ASP registration steps/prompt from the OKX tutorial"
- Demo anomaly-flag beat: use a real census agent that scores low-confidence (a 5.0-rating/<5-sales agent) — shows the "flagged not accused" neutral framing live
- Listing: differentiation line — TrustLens is a marketplace HIRING-trust score (review authenticity, rating-vs-sales anomalies, sales velocity, price fairness), distinct from creditworthiness (Factor), raw data feeds (TO1), or arbitration (Internet Court)
- Price 0.01 USDT/call; tagline MUST be ≤80 chars (count it)

</specifics>

<deferred>
## Deferred Ideas

- Live scraping in CI/tests — never (canned responses only)
- INDX-05 recurring snapshot scheduling — v2
- Actual deploy / registration / posting / Google Form — human steps in the final checklist
</deferred>

---

*Phase: 05-scraper-hardening-submission-kit*
*Context gathered: 2026-07-11 via PRD Express Path*
