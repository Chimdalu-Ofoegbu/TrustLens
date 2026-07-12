# TrustLens — Operator Runbook (deploy → register → submit)

The human-only steps to take TrustLens live on OKX.AI. The build is complete and verified
(320 tests, 100% scoring coverage, x402 gate proven); everything here is an action a human
must perform (deploy, wallet, submission) — the build prepares the materials and stops at
these stop conditions.

All commands run from the `trustlens/` repo root.

> **Deadlines:** submit for OKX marketplace review **July 10–11**; the service must be
> **LIVE before July 17, 2026 23:59 UTC**. Do Steps 1–3 first — they gate everything else.

---

## Step 0 — Pre-flight (decisions + accounts)

| What | Why | Notes |
|---|---|---|
| A hosting account | The ASP endpoint must be a public HTTPS URL | Fastest: a Docker-native PaaS (Fly.io / Render / Railway). OKX suggests HK/Singapore regions. VM alternative in Step 2. |
| An OKX Agentic Wallet | Registration happens through it; it receives 0.01 USDT/call | Log in during Step 4 (human-only). |
| A funded X Layer wallet address | This is `TRUSTLENS_PAY_TO` | Only the **public address** goes in env — never a private key. |
| OKX API credentials (`OKX_API_KEY`, `OKX_SECRET_KEY`, `OKX_PASSPHRASE`) | For the real payment-SDK swap (Step 3) | Generated from your OKX account; treat as secrets. |
| Node.js ≥ 18 | MCP Inspector + Onchain OS CLI | — |
| An X (Twitter) account | Launch post (Step 7) | — |

---

## Step 1 — Docker smoke test (local; closes acceptance criterion #7)

The one automated check that couldn't run during the build (Docker Desktop's engine would not
start on the build machine). It proves the exact image you'll deploy.

**1a. Start Docker Desktop**, wait for "Engine running", then verify:
```bash
docker info        # prints server info when the engine is up
```
If it errors: fully quit and reopen Docker Desktop (as admin on Windows); ensure WSL2 is on
(`wsl --status`).

**1b–1d. Build, check, tear down.** `docker compose up` runs in the **foreground** and holds the
terminal (it streams logs and never returns a prompt), so run it **detached** with `-d` for a
smoke test:
```bash
docker compose up --build -d                       # -d returns your prompt immediately
curl -s http://localhost:8000/healthz              # -> {"status":"ok","agents":272,...}
curl -s http://localhost:8000/ | grep -c "agent-"  # -> 272 leaderboard rows
npx --yes @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/list
docker compose down                                # stop AFTER the checks pass
```
(Alternatively, run `docker compose up --build` in one terminal and the checks in a second one,
then `Ctrl+C` + `docker compose down`.)

**Where the `agents:272` stat lives:** it's a field in the JSON that the `/healthz` endpoint
returns — you see it by hitting `http://localhost:8000/healthz` (curl or browser) **while the
container is running**, i.e. *before* `docker compose down`. On first start the entrypoint
self-seeds the DB + leaderboard from the bundled census (offline, a few seconds). The
`"data_as_of":"2026-07-10T00:00:00Z"` field is the census capture date (from the CSV filename),
not today's date — deliberately wall-clock-free so scores stay byte-deterministic.

✅ healthz `agents:272` + 272 leaderboard rows + 4 tools listed = AC7 closed, image is deploy-ready.

---

## Step 2 — Deploy to an HTTPS host  **[HUMAN-ONLY]**

A single Docker service on port 8000 needing a public HTTPS domain. Pick one path.

### Path A (fastest): Docker-native PaaS — recommended
Fly.io shown; Render/Railway are analogous (all give automatic HTTPS):
```bash
# one-time
fly auth login
# from the repo root (Fly detects the Dockerfile)
fly launch --no-deploy --region sin      # sin = Singapore; hkg = Hong Kong
```
- Decline any Postgres/Redis offer (you use SQLite).
- In the generated `fly.toml`: internal port **8000**, health check on `/healthz`.
- Set env (Step 3), then `fly deploy`. Your `<host>` is `https://<app>.fly.dev`.

### Path B: your own VM + auto-TLS reverse proxy
On an HK/Singapore VM with Docker + a domain A-record pointed at it:
```bash
docker compose up -d --build     # app on :8000
```
Front it with Caddy for automatic Let's Encrypt HTTPS — `Caddyfile`:
```
your-domain.com {
    reverse_proxy localhost:8000
}
```
```bash
caddy run
```

**Deliverable:** a live `https://<host>/` leaderboard and `https://<host>/mcp` endpoint.

---

## Step 3 — Production config, SDK swap, pre-registration check

**3a. Create `.env`** (gitignored — never commit real values):
```bash
cp .env.example .env
```
```bash
TRUSTLENS_PAY_TO=0xYOUR_REAL_X_LAYER_WALLET_ADDRESS
TRUSTLENS_PRICE_USDT=0.01
X_LAYER_RPC=https://rpc.xlayer.tech
X402_MOCK=                        # MUST stay EMPTY in production
TRUSTLENS_BASE_URL=https://<host> # real HTTPS base, no trailing slash
```
> **Critical:** `X402_MOCK` empty (or absent) in production. Exactly `1` enables the mock
> verifier that accepts ANY payment signature. Empty = fail-closed (every unpaid call → 402).
> On a PaaS, set these as platform secrets (e.g. `fly secrets set ...`) instead of a file.

**3b. Wire the real payment SDK.** In `server/payments.py`, replace the fail-closed
`UnconfiguredVerifier` at the `make_verifier` / `PaymentVerifier` seam with `okxweb3-app-x402`'s
facilitator, authenticated with your OKX creds **as deploy secrets** (never committed):
```
OKX_API_KEY=...   OKX_SECRET_KEY=...   OKX_PASSPHRASE=...   # HUMAN-ONLY stop condition
```

**3c. Redeploy, then run the OKX pre-registration check** against the live host:
```bash
curl -i -X POST https://<host>/mcp
```
Expected: `HTTP/1.1 402 Payment Required` + uppercase `PAYMENT-REQUIRED` header. Decode it:
```bash
curl -is -X POST https://<host>/mcp | grep -i '^payment-required:' | cut -d' ' -f2 | base64 -d
# -> scheme "exact", network "eip155:196", amount "10000", your payTo
```
Confirm free surfaces: `curl -s https://<host>/healthz` (200), `curl -Is https://<host>/` (200).

✅ A live 402 + `PAYMENT-REQUIRED` on `POST /mcp` is what OKX's check looks for — must pass before Step 4.

---

## Step 4 — Wallet login, Onchain OS, register + list  **[HUMAN-ONLY]**

**4a. Install Onchain OS:**
```bash
npx skills add okx/onchainos-skills --yes -g
```
**4b. Log into your OKX Agentic Wallet.**

**4c. Registration prompt 1 — paste EXACTLY:**
```
Help me register an A2MCP ASP on OKX.AI using Onchain OS
```
Fields (from `submission/listing-copy.md`):
- Service name: `TrustLens`
- Description: the description paragraph in listing-copy.md
- Price per call: `0.01`
- Endpoint URL: `https://<host>/mcp`

**4d. Listing prompt 2 — paste EXACTLY:**
```
Help me list my ASP on OKX.AI using Onchain OS
```
- Tagline: `Deterministic trust scores for OKX.AI agents, in one paid MCP call` (66 chars)
- Category: **Software Services** (form code `SOFTWARE_SERVICES`)
- Methodology URL: `https://<host>/#methodology`

**4e. Review completes within ~24h** to your registered wallet email.

---

## Step 5 — Verify the live listing

After the approval email:
1. Confirm **TrustLens** shows on okx.ai/agents (Software Services, 0.01 USDT).
2. Trigger a real paid `score_agent` call; confirm a full card returns and 0.01 USDT settles to
   `TRUSTLENS_PAY_TO` on X Layer.
3. Inspector against the public endpoint:
   ```bash
   npx --yes @modelcontextprotocol/inspector --cli https://<host>/mcp --method tools/list
   ```

✅ "Live" milestone — must be true **before July 17 23:59 UTC**.

---

## Step 6 — Record the 90-second demo

`submission/demo-script.md` — five beats on real, verified data:
1. Problem: trust an agent before paying?
2. `score_agent("这个能吃吗？")` → A / 94 / high (539 sales).
3. Anomaly: `score_agent` on GlassDesk (id 3465) → D / 45 / low (5.0 rating on 1 sale),
   flagged-not-accused (verbatim engine reason).
4. Agent-calling-agent: one agent checks another's TrustScore before hiring.
5. Leaderboard + 0.01 USDT/call settling on-chain.

Start the service (`docker compose up` or your live host), screen-record while running the
script's commands top to bottom, narrate, keep it ≤90s, export the video.

---

## Step 7 — Post the launch thread  **[HUMAN-ONLY]**

`submission/x-post-draft.md` — a 6-tweet thread (neutral, banned-word-clean). Tweak to your
voice, attach the demo video + live listing link, post **with #OKXAI**.

---

## Step 8 — Submit the hackathon Google Form  **[HUMAN-ONLY]**

Gather: live listing URL, demo video, X thread link, repo (110 clean commits), pitch (README
intro + listing-copy description). Fill in and submit.

---

## Ordering & fallbacks

- **Critical path to live:** 1 → 2 → 3 → 4 → 5. Then 6 → 7 → 8 after approval.
- **If Docker Desktop won't start:** you don't strictly need local Docker if you deploy via a
  PaaS that builds server-side (Path A) — push and let the platform build the Dockerfile, then
  verify against the live `https://<host>` with the same curl/Inspector checks.
- **Two-attempt rule:** if a step errors twice unresolved (SDK swap contradicts the x402 wire
  format, registration agent rejects the endpoint), stop and reassess rather than forcing it.

---

## Reference: verified facts

- **Ports/surfaces:** one port 8000 — `/` leaderboard, `/healthz`, `/mcp`, `/badge/{id}.svg`.
- **x402:** `POST /mcp` (no payment) → 402 + base64 `PAYMENT-REQUIRED` (scheme `exact`,
  network `eip155:196`, amount `"10000"` = 0.01 USDT @ 6 decimals). Free: `/healthz`, `/`,
  `/badge/*`, MCP `initialize`/`tools/list`.
- **Env vars (5):** `TRUSTLENS_PAY_TO`, `TRUSTLENS_PRICE_USDT`, `X_LAYER_RPC`, `X402_MOCK`,
  `TRUSTLENS_BASE_URL` — see `.env.example`.
- **Listing:** name TrustLens · tagline 66 chars (≤80) · Software Services · 0.01 USDT ·
  endpoint `https://<host>/mcp` · methodology `https://<host>/#methodology`.
- **Data freshness:** `data_as_of` reflects the census capture date (2026-07-10 from the
  filename), wall-clock-free by design for byte-deterministic scores; override with
  `python -m indexer.refresh --captured-at <ISO>` only when the data is genuinely from that date.
