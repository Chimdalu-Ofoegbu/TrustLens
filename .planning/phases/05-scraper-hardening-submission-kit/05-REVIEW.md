---
phase: 05-scraper-hardening-submission-kit
reviewed: 2026-07-11T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - indexer/scraper.py
  - indexer/refresh.py
  - tests/test_scraper.py
  - tests/test_submission_language.py
  - README.md
  - submission/demo-script.md
  - submission/x-post-draft.md
  - submission/listing-copy.md
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-07-11
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Phase 5 delivers a genuinely well-hardened scraper. The security posture the plan promised is real and verified in code: `_cache_path` uses `sha256(url)` as the sole path component (no traversal, V12); `detail_url` constrains ids to `^\d+$` before URL build (no SSRF, V13); logs use `%r` for url/id/name (log-injection + cp1252 safe, V7); politeness (cache-first, sleep-between, 15s timeout, single attempt) is correctly implemented; and no `eval`/`exec`/unbounded recursion touches the untrusted `appState` JSON. The offline-default guarantee holds — `scrape_agents` is imported lazily inside the `--scrape` branch only, so the default path never loads httpx-heavy scraper code, and `test_no_server_module_imports_scraper` enforces the request-path exclusion. Merge determinism is proven: an empty scraped list preserves census dict-insertion order and object identity byte-for-byte. No real secrets or wallet addresses appear in any submission file or the README. Category stays DERIVED (Option B) — the raw okx.ai code never reaches `AgentRecord.category`.

Three defects warrant fixing. The most important: `parse_appstate` catches `(ValueError, KeyError, TypeError)` but **not** `AttributeError`, and one field cast (`approval.rstrip("%")`) raises exactly `AttributeError` when `approvalRate` arrives as a JSON number instead of a string — a plausible format drift for attacker-influenceable marketplace JSON. This breaks the module's documented "every failure mode ... never raises" contract at the `parse_appstate` boundary. It does NOT change refresh's exit code (the broad `except Exception` in `scrape_agents` still swallows it), so the graceful-degradation-of-refresh guarantee survives — but the swallow is not "total" at the function that claims to be total, and any direct caller (the test suite already calls `parse_appstate` directly; any future reuse) gets an exception instead of `None`. Two lower-severity issues: successful `--scrape` records persist under `source="census"` (wrong provenance), and a legitimately free agent (`serviceLowestFee` numeric `0`) silently loses its price.

## Warnings

### WR-01: `parse_appstate` does not catch `AttributeError`; a numeric `approvalRate` raises instead of soft-missing

**File:** `indexer/scraper.py:158-178` (specifically the cast at line 174 and the `except` at line 176)
**Issue:** The field-cast block catches `(ValueError, KeyError, TypeError)`. But `positive_pct=float(approval.rstrip("%"))` calls `.rstrip` on `approval = ov.get("approvalRate")`. `str.rstrip` exists only on strings; if `approvalRate` is a JSON number (`"approvalRate": 100`) — a completely ordinary shape for marketplace JSON, and this input is explicitly modeled as UNTRUSTED third-party data — `(100).rstrip("%")` raises `AttributeError`, which is **not** a subclass of any caught type (verified: `issubclass(AttributeError, (ValueError, KeyError, TypeError))` is `False`). The exception escapes `parse_appstate`, contradicting the module docstring ("every failure mode ... logs exactly one WARNING and returns None/[], never raises") and stage-3's own docstring ("cast every field ... bad value -> ValueError"). The only reason refresh's exit code is unaffected is the belt-and-suspenders `except Exception` in `scrape_agents` (line 207) — but that catch does NOT log the intended field-level WARNING and, critically, `parse_appstate` is a public exported symbol that the test suite (`tests/test_scraper.py:58-116`) already calls directly with no wrapper. A drifted real page would raise straight out of any such call site. The same class of gap applies to any future non-str field (e.g. a name arriving as a number would break `name_key`, though `unicodedata.normalize` on a non-str raises `TypeError`, which *is* caught — `approvalRate` is the one live hole).
**Fix:** Add `AttributeError` to the caught tuple so the function honors its own total-swallow contract:
```python
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        log.warning("appState field cast miss url=%r: %s", url, exc.__class__.__name__)
        return None
```
Optionally coerce defensively at the source instead (belt-and-suspenders): `approval = ov.get("approvalRate"); pct = float(str(approval).rstrip("%")) if approval is not None else None`. Add a regression fixture/test with `"approvalRate": 100` (numeric) asserting `None` + one WARNING, mirroring the existing degradation parametrize.

### WR-02: Successful `--scrape` records persist with `source="census"` (wrong provenance)

**File:** `indexer/refresh.py:238-245` (merge then persist) vs `indexer/refresh.py:96-102` (`_persist_records` default `source="census"`)
**Issue:** After `records = merge(records, scraped)`, `main()` calls `_persist_records(args.db, records, field_warnings, captured_at, generated_at=..., web_out=...)` with **no** `source=` argument, so every persisted snapshot — including the genuinely scraped ones that overrode census rows — is tagged `source="census"`. The Phase 5 seam was designed precisely so scraped rows carry `source="scrape"` (see `db.py:31`, `persist` docstring "source='scrape' later", and the snapshots DDL default). The existing test `tests/test_scraper.py:239` only exercises the *empty*-scrape case (asserting `source != 'census'` count is 0, which passes trivially because nothing was scraped), so it does not catch this — a *successful* scrape would mislabel real scrape provenance as census. This is a data-quality/audit defect, not a crash: the snapshots time-series can no longer distinguish scrape-sourced observations from census ones. Note the current `DEMO_AGENT_IDS` set overrides an existing census id (3345), so with live scraping enabled this mislabels a real row today.
**Fix:** Split provenance so scraped rows are tagged correctly. Simplest correct approach is to persist the two provenances separately (census rows as `census`, scraped rows as `scrape`) rather than merging into one `source`. If a single-pass persist is preferred, at minimum pass an accurate aggregate source, e.g. `source="scrape" if scraped else "census"`, and add a test that scrapes a non-empty record and asserts a `source='scrape'` snapshot row exists. Given the census-is-floor semantics, per-record source tagging (record carries its own origin) is the durable fix.

### WR-03: A legitimately free agent (`serviceLowestFee` numeric `0`) silently loses its price

**File:** `indexer/scraper.py:161, 170-171`
**Issue:** `fee = ov.get("serviceLowestFee")`, then `price_usdt=float(fee) if fee else None` and `price_raw=str(fee) if fee else ""`. The `if fee` truthiness guard treats JSON numeric `0` (a valid "free" price) as absent, dropping it to `price_usdt=None` / `price_raw=""`. Same for a string `"0"`? — no: `"0"` is truthy, so string zero survives; the hole is specifically the numeric-`0` and numeric-`0.0` JSON shapes (and `""`/`None`, which correctly map to absent). Since the field is untrusted marketplace JSON of unverified type, a free agent published as `"serviceLowestFee": 0` would be indistinguishable from an agent with no price at all, which then feeds price-fairness scoring differently. Lower severity than WR-01/02 because okx.ai's observed shape is the string `"0.01"` and the demo set is a single paid agent, but it is a real fidelity gap for the untrusted-input contract.
**Fix:** Distinguish "missing" from "zero" explicitly:
```python
        fee = ov.get("serviceLowestFee")
        price_usdt = float(fee) if fee not in (None, "") else None
        price_raw = str(fee) if fee not in (None, "") else ""
```
Wrap remains inside the existing try/except so a non-numeric `fee` still soft-misses. Add a `"serviceLowestFee": 0` fixture asserting `price_usdt == 0.0`.

## Info

### IN-01: README test count is stale (says 314; actual is 317)

**File:** `README.md:36`
**Issue:** "The full suite runs green (314 passing)" — `pytest --collect-only` reports **317 tests collected** after Phase 5 added the scraper and submission-language tests. A hardcoded count drifts every time tests are added and is exactly the kind of number a hackathon judge may spot-check against a live run. Same section's Docker line and the "prints `272 agents, 272 snapshots, source=census`" claim (README.md:22) are paraphrases — the real summary line is `"... %d snapshots appended, %d field warning(s), source=census"` (refresh.py:250-251); harmless but not literal.
**Fix:** Either update to 317, or (better) drop the exact integer: "The full suite runs green with a >=90% coverage gate scoped to `scoring/` (currently 100%)." Avoids all future drift.

### IN-02: `T-05-09` response-size cap is accepted, not mitigated — reconfirm the acceptance is intended

**File:** `indexer/scraper.py:120` (`client.get(url, timeout=TIMEOUT_S)`)
**Issue:** There is no response-body size cap; httpx buffers the whole body into memory. The plan's threat model (`05-01-PLAN.md` T-05-09) explicitly marks this **accept** with rationale (15s timeout + single attempt + ~50-100KB okx.ai pages + bounded demo set bound the exposure). This is a documented, deliberate acceptance for the timeboxed demo tier, so it is NOT a defect against the phase contract — flagging only so the reviewer confirms the acceptance is still intended before any future move toward a full crawl (INDX-05), where an unbounded hostile response would be a real DoS vector. If/when the id set grows beyond the fixed `DEMO_AGENT_IDS`, add a streamed size cap.
**Fix (only if acceptance is revisited):** Stream with an early abort, e.g. iterate `client.stream("GET", url)` and break once accumulated bytes exceed a cap (say 5 MB), returning `None` + WARNING. Not required for v1.

### IN-03: `int(ov.get("usageCount", 0))` rejects a stringified-float count as a soft miss (acceptable, noted)

**File:** `indexer/scraper.py:172`
**Issue:** `sold=int(ov.get("usageCount", 0))` raises `ValueError` for a stringified float like `"539.0"` (verified: `int("539.0")` raises) — which is correctly caught and soft-missed. This is safe and consistent with the "fail to a clean miss" design, but it means a real page that ever renders `usageCount` as `"539.0"` (rather than the observed integer `539`) would drop the entire record instead of parsing 539. Contrast `parse_sold` in the census path, which tolerates decimals. Purely a robustness observation; no action needed unless okx.ai's shape is confirmed to vary.
**Fix (optional):** `sold=int(float(ov.get("usageCount", 0) or 0))` to tolerate float-shaped counts, keeping the try/except guard.

---

_Reviewed: 2026-07-11_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
