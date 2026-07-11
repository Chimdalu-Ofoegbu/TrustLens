# TrustLens — 90-Second Demo Script (SUBM-01)

A five-beat storyboard: **problem → live MCP call → the anomaly beat → agent-calling-agent → leaderboard + on-chain revenue.** Every number below is real, taken from the built 272-agent database (`python -m indexer.refresh`), not staged. Total run time ≈ 90 seconds.

All framing is neutral analytics language: TrustLens reports *what the data shows* and flags thin evidence — it never makes an allegation about any agent's conduct.

---

## Setup (run before recording)

The whole demo runs against a clean clone with one command:

```bash
docker compose up
```

The entrypoint self-seeds the SQLite store and the leaderboard from the bundled census on first start, then serves the leaderboard (`/`), `/healthz`, and the MCP endpoint (`/mcp`) on one port (`http://localhost:8000`). Give it a few seconds, then confirm with `curl -s http://localhost:8000/healthz`.

- **HUMAN-ONLY: start the Docker Desktop engine first.** The engine must be running before `docker compose up` (`docker info` must succeed). This is a carried Phase-3/4 environment step and is the only manual prerequisite for the recording.
- Keep two panes visible: a terminal for the MCP calls and a browser on `http://localhost:8000/` for the leaderboard beat.
- Warm the database cache once (run Beat 2's call before recording) so the live call returns in well under a second.

---

## The Storyboard

| Beat | ~Sec | On-screen action | Narration |
|------|------|------------------|-----------|
| **1. The problem** | 0–15 | Title card: "Can you trust a marketplace agent before you pay it?" Cut to the OKX.AI marketplace — hundreds of agents, all showing star ratings. | "OKX.AI lists hundreds of agents. Every one shows a star rating. But a rating alone can't tell you whether it's earned over hundreds of sales or comes from a single review. Before you hire an agent — or before your agent hires another — you want one honest, evidence-based answer." |
| **2. The live call** | 15–35 | In the terminal, Claude makes a paid MCP call: `score_agent("这个能吃吗？")`. A score card returns: **A / 94 / high confidence**, rating **5.0 on 539 sales**. | "Here's a real agent, scored live through TrustLens over MCP. Grade A, TrustScore 94, high confidence — a perfect 5.0 rating, and it's backed by 539 sales. The rating is well-supported. This is what a trustworthy listing looks like." |
| **3. The anomaly beat** *(the money shot)* | 35–60 | Call `score_agent("GlassDesk")` (id 3465). A score card returns: **D / 45 / low confidence**, rating **5.0 on 1 sale**. Put the two cards side by side — both show 5.0 stars. Highlight the `rating_credibility` reason string. | "Now a second agent — GlassDesk. Same 5.0 stars. But TrustLens returns grade D, TrustScore 45, low confidence. Here's the reason, verbatim: *'perfect 5.0 rating backed by only 1 sale — pattern consistent with limited review history; low confidence, flagged for thin data (not an assessment of conduct).'* Two agents, both 5.0 — TrustLens shows *why* one is an A and one is a D. It flags thin evidence; it never makes an accusation." |
| **4. Agent-calling-agent** | 60–75 | Show a second agent programmatically calling `score_agent` on a candidate before deciding to hire it — the agent-to-MCP (A2MCP) flow, the same paid call from Beat 2/3. | "This isn't just for people. An agent can call TrustLens on another agent before hiring it — a pre-purchase trust check, agent to agent, over the same paid MCP call. Trust becomes a primitive other agents can compose." |
| **5. Leaderboard + on-chain revenue** | 75–90 | Switch to the browser: `http://localhost:8000/` — the ranked leaderboard, **272 agents**, sortable, with grade badges and a category filter. Then show the 402 → paid flow: `0.01 USDT` per call settling on X Layer. | "Every scored agent lands on the public leaderboard — 272 agents, ranked, sortable, each with a grade. And every score is a paid call: 0.01 USDT, settled on X Layer with zero gas, gated by the x402 standard. Deterministic trust scores for OKX.AI agents — in one paid MCP call." |

---

## The reason string to read aloud (Beat 3 — verbatim from the built DB)

> perfect 5.0 rating backed by only 1 sale(s) — pattern consistent with limited review history; low confidence, flagged for thin data (not an assessment of conduct)

This is the exact `rating_credibility.reason` string returned by `score_agent` for GlassDesk (id 3465). Read it as-is. The parenthetical "not an assessment of conduct" is the neutral-framing contract — keep it in.

## The two contrasted agents (Beat 2 vs Beat 3)

| Agent | id | Grade | TrustScore | Confidence | Rating | Sales |
|-------|-----|-------|-----------|-----------|--------|-------|
| 这个能吃吗？ | 3345 | A | 94 | high | 5.0 | 539 |
| GlassDesk | 3465 | D | 45 | low | 5.0 | 1 |

Both are 5.0 stars. The contrast is the whole point: the score reflects *how much evidence stands behind the rating*, not the star number alone.

## Backup heroes (if GlassDesk reads as too obscure on camera)

Both are the same "5.0 on thin sales → D / low confidence" shape, verified from the built DB. Swap in either if needed:

- **Token Radar** — id 2991, D / 52 / low, 5.0 on 3 sales.
- **Thumbnail Maker** — id 4511, D / 45 / low, 5.0 on 1 sale.

Do **not** use Factor Credit Desk (id 4502) as the demo subject — it names a competitor. Competitor names appear only in the neutral differentiation line on the listing, never as a demo subject here.

---

## Neutral-language checklist (before you hit record)

- The anomaly beat says "flagged for thin data" and "not an assessment of conduct" — never an allegation.
- No agent is described as dishonest, deceptive, or gaming anything. TrustLens reports the evidence gap; the viewer draws their own conclusion.
- The narration carries none of the banned accusatory vocabulary; this is enforced mechanically by the language gate in `tests/test_submission_language.py`, which scans this file.
