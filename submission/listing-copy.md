# TrustLens — OKX.AI ASP Listing Copy (SUBM-03)

Fields to copy into the OKX.AI ASP listing form. All copy is neutral analytics language. Placeholders (`<host>`, `<base>`) are filled at deploy time — no real domain is committed here.

The **Tagline** line below is the primary tagline and is enforced at ≤80 characters by `tests/test_submission_language.py`. Keep it on its own line in the `**Tagline:** <text>` form.

---

**Name:** TrustLens

**Tagline:** Deterministic trust scores for OKX.AI agents, in one paid MCP call

**Category:** Software Services

**Price:** 0.01 USDT per call

**Endpoint URL:** `https://<host>/mcp`

**Methodology URL:** `<base>/#methodology`

**Description:**

TrustLens is a pay-per-call Agent-to-MCP (A2MCP) service that returns a hiring-trust score for any listed OKX.AI agent, so humans and other agents can answer "should I hire this agent?" before they pay. One paid MCP call returns a 0–100 TrustScore, an A–F grade, and a component breakdown built from four signals: review authenticity, rating-vs-sales anomalies, sales velocity, and price fairness versus category. Every component carries a plain-language reason, and thin evidence is flagged with low confidence — factual analytics, never an accusation about any agent. It is a marketplace hiring-trust score — distinct from creditworthiness (Factor), raw data feeds (TO1), and dispute arbitration (Internet Court). Results are deterministic (a `score_version` and `data_as_of` stamp plus pure scoring functions mean the same call returns the same bytes) and settle at 0.01 USDT per call on X Layer with zero gas via the x402 standard. Full scoring methodology: `<base>/#methodology`.

---

## Tagline alternates (all ≤80 chars, banned-word-clean)

The primary above (66 chars) is recommended. Any of these is a valid drop-in — each is character-counted and within the okx.ai 80-char limit:

| Tagline | Chars |
|---------|-------|
| Deterministic trust scores for OKX.AI agents, in one paid MCP call | 66 |
| Evidence-based hiring-trust scores for OKX.AI agents via one paid MCP call | 74 |
| Hiring-trust scores for OKX.AI agents — one paid MCP call, deterministic JSON | 77 |
| TrustScore for any OKX.AI agent — evidence-based, deterministic, one paid call | 78 |
| Should you hire this OKX.AI agent? One paid MCP call, one deterministic verdict | 79 |

(Rejected as over-limit: "One paid MCP call returns a deterministic hiring-trust score for any OKX.AI agent" = 81 chars.)

---

## Field notes (HUMAN-ONLY at submission)

- **Category:** the form's display value is "Software services" (okx.ai's internal filter code is `SOFTWARE_SERVICES`). "Software Services" is the brief's label; select the matching option in the form.
- **Endpoint URL:** replace `<host>` with the deployed public HTTPS host (the endpoint is the `/mcp` path). The x402 pre-registration check (`curl -i -X POST https://<host>/mcp` → 402) should pass before you submit.
- **Methodology URL:** replace `<base>` with the same deployed base; the leaderboard's methodology section lives at `<base>/#methodology`.
- **Price:** 0.01 USDT per call maps to atomic units `"10000"` (6 decimals) in the x402 requirements — already handled by the server; enter `0.01` in the form.
- Submitting the listing is a human-only step (a locked stop condition). This file supplies the exact field values to paste; it does not submit anything.
