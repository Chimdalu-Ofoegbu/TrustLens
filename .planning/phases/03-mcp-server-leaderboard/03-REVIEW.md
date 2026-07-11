---
phase: 03-mcp-server-leaderboard
reviewed: 2026-07-11T12:51:38Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - web/__init__.py
  - web/build.py
  - web/badge.py
  - server/__init__.py
  - server/db.py
  - server/tools.py
  - server/app.py
  - server/main.py
  - indexer/refresh.py
  - Dockerfile
  - docker-compose.yml
  - .dockerignore
  - pyproject.toml
  - .gitignore
  - tests/conftest.py
  - tests/test_web_build.py
  - tests/test_web_badge.py
  - tests/test_server_tools.py
  - tests/test_server_app.py
  - tests/test_refresh_web.py
findings:
  critical: 0
  warning: 2
  info: 7
  total: 9
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-07-11T12:51:38Z
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

Adversarial review of the Phase 3 surface (leaderboard builder + badge generator, MCP server core, one-port host app, refresh wiring, Docker packaging) against the 03-0X-PLAN threat models. Verification included executing the badge allowlist regex against a newline-bearing input, exercising the empty-DB build path, confirming `__pycache__` directories exist in all four COPY'd packages, checking `int(w*100)` truncation, and running the full suite (229 passed, scoring coverage 100%, gate green).

The security core holds up well:

- **XSS (T-03-01):** every DB-sourced string in `web/build.py` passes through `html.escape` — text nodes (`name`, `cat`, `grade`, `conf`) and attribute contexts (`id="agent-{aid}"`, `title="{tagline_v}"`, `data-v` for name/category) with `quote=True`. Numeric cells are Python-formatted from typed columns (`sold` is `INTEGER NOT NULL`; nullable `rating`/`price_usdt` have explicit None branches). Methodology/badge-snippet content is constants or escaped. The one unescaped page interpolation (`$example_badge`) receives only `badge_svg()` output built from engine-written columns (see IN-04).
- **SQL injection (T-03-05):** the single `sqlite3.connect` in `server/` is the `mode=ro` URI in `connect_ro`; every query is `?`-parameterized; the LIKE ladder escapes `\` before `%`/`_` with an `ESCAPE '\'` clause; `limit` (1–50) and `ids` (2–10) caps are enforced before any query runs.
- **Error channel (T-03-06):** all 4 tools wrap their entire bodies; unexpected exceptions become a fixed neutral JSON `ToolError` with `from None`, real exceptions logged server-side only. `/healthz` returns a fixed 503 body on any `sqlite3.Error`/`OSError` (missing DB raises `OperationalError` → caught); `/badge` degrades to the neutral badge on DB failure.
- **Determinism (MCPS-02):** no wall clock or randomness anywhere in served responses or the built page; envelope values come from stored rows; rerun byte-identity is test-pinned.
- **Read-only guarantee:** confirmed — `server/` opens exactly one kind of connection (`mode=ro`); the only filesystem write in server code is `mkdir` of the static dir (not the DB).
- **Docker secrets/env hygiene:** `.env`, `.git`, `.planning`, `data/*.db(+wal/shm)`, `tests`, `web/dist` all excluded from the build context; compose `env_file` tolerant of absence; no secrets or hardcoded addresses anywhere.

Two Warnings (a weakened defense-in-depth control and a build-context hygiene gap) and seven Info items follow. No Critical findings.

## Warnings

### WR-01: Badge allowlist regex `$` anchor admits a trailing newline

**File:** `server/app.py:21` (used at `server/app.py:129`)
**Issue:** `_AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")` is documented (docstring + T-03-13) as the control that guarantees "rejected ids never reach a query." In Python regex, `$` also matches immediately before a trailing `\n`, so `_AGENT_ID.match("3345\n")` returns a match (verified by execution). A request to `/badge/3345%0A.svg` therefore passes the allowlist and the newline-bearing string reaches the DB query. Practical impact today is nil — the query is parameterized and the lookup misses, yielding the neutral badge — but the stated security invariant is bypassed, and the control is what Phase 4's payment-free `/badge/*` route will continue to rely on.
**Fix:**
```python
_AGENT_ID = re.compile(r"[A-Za-z0-9_-]{1,32}\Z")
...
if _AGENT_ID.fullmatch(agent_id):
```
(`\Z` anchors at the true end of string; `fullmatch` removes the need for `^`.)

### WR-02: `.dockerignore` bare patterns miss nested `__pycache__` — local bytecode baked into the image

**File:** `.dockerignore:5-6`
**Issue:** Docker `.dockerignore` patterns without a leading `**/` match only at the build-context root. `__pycache__` and `*.py[cod]` therefore exclude only root-level entries, while `COPY indexer/ indexer/`, `COPY scoring/`, `COPY server/`, and `COPY web/` copy the nested `__pycache__/` directories that exist in all four packages (verified present). Consequences: (a) local `.pyc` files embed absolute build-machine paths (`C:\Users\Ben\...`) in `co_filename`, leaking username/machine layout into a distributable image (T-03-18 adjacency); (b) image bloat; (c) bytecode compiled by the local Python (3.14) ships in a 3.13 image (magic-number mismatch makes it dead weight, not a crash — but it is pure cruft).
**Fix:**
```
**/__pycache__
**/*.py[cod]
```

## Info

### IN-01: Dockerfile layer ordering re-installs all dependencies on every source change

**File:** `Dockerfile:4-10`
**Issue:** `RUN pip install --no-cache-dir .` sits after the source `COPY` lines, so any one-line source edit invalidates the install layer and re-resolves/re-downloads every dependency. Image correctness is unaffected (pins live in `pyproject.toml`), and the file is a verbatim transcription of the approved research primitive — this is a build-ergonomics note, not a defect.
**Fix:** Add a dependency layer keyed only on `pyproject.toml` (e.g., `RUN pip install --no-cache-dir fastapi==0.139.0 "fastmcp>=3,<4" uvicorn==0.51.0 httpx==0.28.1 beautifulsoup4==4.15.0` before the source COPYs, or a generated requirements file), then `pip install --no-deps .` after copying sources.

### IN-02: Page-build failure logs "database error" naming the DB path

**File:** `indexer/refresh.py:214-215`
**Issue:** A failed leaderboard build (e.g., unwritable `--web-out` parent) raises `OSError` inside `_persist_records` and is caught by `except (OSError, sqlite3.Error)` — exit code 2 is correct and test-pinned — but the operator sees `database error at data/trustlens.db: ...` when the DB stage actually committed fine and the failure is at the web-out path. Misleading during incident triage only.
**Fix:** `log.error("environment error (db %s, web-out %s): %s", args.db, args.web_out, exc)` — or split the build into its own try/except with a distinct message (still returning 2).

### IN-03: `int(WEIGHTS[key] * 100)` truncates instead of rounding

**File:** `web/build.py:527`
**Issue:** Float truncation renders correct values for the current weights (verified: 30/25/20/15/10) but silently produces `28%` for a hypothetical `0.29` weight (`int(0.29*100) == 28`). Latent only — any weight change must bump `SCORE_VERSION` and the pinned test would catch a wrong percentage — but the pattern is a footgun.
**Fix:** `weight=round(WEIGHTS[key] * 100)`.

### IN-04: `badge_svg` interpolates `score` unescaped, trusting the type contract

**File:** `web/badge.py:42,55`
**Issue:** `right = f"{grade} {score}"` places `score` into the SVG without validation. All current callers pass `scores.score` (INTEGER column, single writer = scoring engine) or literals, so no live injection path exists — but this is the shared generator behind the public `/badge/{id}.svg` endpoint, and SQLite's dynamic typing means a corrupted/foreign DB could theoretically store TEXT there. One cast makes the contract enforced rather than assumed.
**Fix:** `right = grade if grade == "NR" or score is None else f"{grade} {int(score)}"`.

### IN-05: Tools resolve the DB via a CWD-relative default; missing DB reports "internal" not "unavailable"

**File:** `server/db.py:32`, `server/tools.py:183` (all four tools)
**Issue:** `DEFAULT_DB = Path("data/trustlens.db")` is resolved against the process CWD. Docker (`WORKDIR /app`) and repo-root runs are fine, but launching `uvicorn server.main:app` from any other directory makes every tool fail — and because `connect_ro` raising `sqlite3.OperationalError` is swallowed by the generic guard, the client sees `{"error": "internal", "detail": "unexpected server error"}` rather than the accurate `unavailable` wording used for an empty scores table. Neutral and non-leaking (so not a Warning), but the misclassification will cost debugging time and the create_app(db_path=...) parameter deliberately does not reach the tools (documented).
**Fix:** Catch `sqlite3.OperationalError` around `db.connect_ro()` in the tools and raise `_err(_unavailable_payload())`; optionally anchor `DEFAULT_DB` to the repo root (`Path(__file__).resolve().parents[1] / "data" / "trustlens.db"`) or a `TRUSTLENS_DB` env var in Phase 4.

### IN-06: `real_db` fixture trusts any pre-existing `data/trustlens.db`

**File:** `tests/conftest.py:15-18`
**Issue:** The session fixture seeds the repo DB only when the file is absent; it never verifies the existing DB matches the seed contract (SEED_TS, census CSV). A developer who ran `indexer.refresh` with a different `--captured-at` (or against a future CSV) gets confusing golden-test failures (`generated_at != "2026-07-10T00:00:00Z"`) with no hint that the fixture served a stale DB. Test-reliability note.
**Fix:** Cheap guard in the fixture: query `MAX(data_as_of)` and re-seed (or fail with a clear message) when it differs from `SEED_TS`.

### IN-07: Test pins an unpinned transitive dependency's error message text

**File:** `tests/test_server_tools.py:245`
**Issue:** `assert "Input should be a valid string" in res.content[0].text` pins pydantic's validation message verbatim. pydantic arrives as an unpinned transitive of `fastmcp>=3,<4`, so a future message-wording change breaks the test on fresh installs even though behavior (is_error=True) is unchanged. Test-reliability note.
**Fix:** Assert on the stable part: `res.is_error is True` plus a case-insensitive check for `"string"` (or the JSON-RPC error code), rather than the full sentence.

---

## Verified non-findings (checked, no defect)

- **`string.Template` stray-`$` (T-03-03):** the entire `_PAGE` body contains `$` only in the 11 substituted placeholders, all supplied in `substitute()`; the inline JS is `$`-free. Empty-DB build path executes cleanly (verified: renders "0 agents", em-dash date, N/A badge).
- **JS `data-v` sort keys vs escaped attributes:** `getAttribute` returns entity-decoded values, so string sorts compare raw names — no escaping-induced misordering.
- **`McpPathRewrite` scope mutation:** shallow-copies the scope dict before rewriting `path`/`raw_path` (ASGI `raw_path` excludes the query string, so `b"/mcp/"` is correct); Phase-4 LIFO middleware comment is accurate (`add_middleware` inserts outermost, so X402 added later runs before the rewrite and must match `startswith("/mcp")`).
- **healthz DB-failure path:** missing file, zero-byte DB, and empty scores all resolve to the fixed 503 body (`sqlite3.Error`/`OSError` caught; no exception text serialized); test 6 pins the exact field set.
- **`%2F`/`%5C` traversal on `/badge`:** both paths pinned by tests (slash-decoded path falls through to StaticFiles' anti-traversal 404; backslash reaches the route and the allowlist rejects). The residual newline case is WR-01.
- **compare/category caps:** enforced before any query; negative/zero `LIMIT` can never reach SQLite.
- **Wall clock/randomness:** none in `web/`, `server/`, or the refresh delta; suite-verified byte-determinism end to end.
- **Docker CMD guard:** `[ -f a ] && [ -f b ] || refresh; exec uvicorn` precedence is correct (seeds when either artifact is missing); a failed seed still boots uvicorn so `/healthz` can report 503 with the remedy — consistent with the HEALTHCHECK marking the container unhealthy.
- **Root container user / no restart policy:** explicitly accepted and documented in the 03-05 threat register (T-03-20/21) — not re-flagged.
- **Full suite:** 229 passed, 0 failed; scoring coverage 100% (gate ≥90% green); the single pytest warning is a third-party `StarletteDeprecationWarning` from `fastapi.testclient`, not project code.

---

_Reviewed: 2026-07-11T12:51:38Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
