---
phase: 01-foundation-data-indexer
reviewed: 2026-07-10T22:41:40Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - pyproject.toml
  - indexer/__init__.py
  - indexer/models.py
  - indexer/parse.py
  - indexer/category.py
  - indexer/db.py
  - indexer/census.py
  - indexer/refresh.py
  - tests/test_parse.py
  - tests/test_category.py
  - tests/test_db.py
  - tests/test_refresh.py
findings:
  critical: 0
  warning: 4
  info: 3
  total: 7
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-07-10T22:41:40Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Reviewed the complete Phase 1 indexer package (parsers, category derivation, SQLite persistence, census loader, refresh CLI) and its four test files against the locked decisions in 01-CONTEXT.md, the CLAUDE.md constraints, and the STRIDE threat registers in the four plan files. The full suite passes (71 tests) and every finding below was verified by executing the code, not just reading it.

The core mitigations hold: all SQL is parameterized `?` placeholders (no f-string/concat SQL anywhere), no network or wall-clock imports exist in `indexer/`, `first_seen` is correctly absent from the upsert's `DO UPDATE SET`, `name_key` has no UNIQUE constraint, all category keywords except the two vetted regexes pass through `re.escape`, and the hostile-content round-trip and FK-enforcement tests genuinely prove what they claim. The `SUBSTRING_KEYWORDS` mechanics deviation in category.py is documented in-module and in 01-02-SUMMARY.md, and is pinned by the full-census distribution test.

However, four defects survive on the phase's own declared trust boundary (untrusted CSV content) — each contradicts an explicit contract or threat-model mitigation, and each was reproduced:

1. `parse_sold` **crashes** with ValueError on a comma-only numeric group despite the module's "parsers never raise" contract (WR-01).
2. `main()` catches only `OSError`, so unreadable (non-UTF-8) CSVs, oversized cells, and bad `--db` paths spew tracebacks instead of the documented exit codes (WR-02).
3. The log-injection mitigation (T-04-02) is incomplete: the logged `id` is itself raw cell text, and a quoted id cell with an embedded newline forges log lines (WR-03).
4. `parse_price` and `_price_token` disagree on the no-space `"5USDT"` format, letting a price echo through the rule-A gate as a genuine 5.0 rating (WR-04).

None of these fire on the committed 272-row census — which is exactly why the green suite does not detect them. They matter because these parsers and this loader are the declared contract for Phase 5's scraped (less-controlled) input.

## Warnings

### WR-01: `parse_sold` raises ValueError on comma-only numeric group — violates the "never raises" contract

**File:** `indexer/parse.py:12,31`
**Issue:** `_SOLD = re.compile(r"([\d,]+(?:\.\d+)?)\s*([KMkm])?\s*sold")` — the class `[\d,]+` accepts a group made only of commas. `", sold"` (or `",,, sold"`) fullmatches, then line 31 executes `float("".replace(...))` → `float("")` → **ValueError**. Reproduced:

```
>>> parse_sold(", sold")
ValueError: could not convert string to float: ''
```

This violates the module docstring ("Parsers never raise on malformed input", line 5), the census.py contract ("field content never raises"), and threat-model mitigations T-01-01 / T-04-04 ("Per-field NULL/0 fallback (never raises on content)"). The exception propagates uncaught through `load_census` → `refresh` → `main` (a ValueError is not `OSError`), aborting the whole refresh with a traceback on one bad cell. No data is corrupted (the crash precedes all DB writes), and the committed census never triggers it — but Phase 5 will feed these same parsers scraped text.
**Fix:**
```python
    m = _SOLD.fullmatch(s)
    if not m:
        return None
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:          # comma-only group, e.g. ", sold"
        return None             # caller stores 0 and warns
```
(Or tighten the regex to require a digit: `(\d[\d,]*(?:\.\d+)?)`.)

### WR-02: `main()` catches only `OSError` — unreadable CSV / bad `--db` produce tracebacks instead of documented exit codes

**File:** `indexer/refresh.py:137-141`
**Issue:** The module docstring promises "Exit codes: 0 success, 1 missing/unreadable csv, 2 captured-at underivable", but only `OSError` is caught. Reproduced:
- Non-UTF-8 CSV → `UnicodeDecodeError` escapes `main()` (traceback, not exit 1). A file that cannot be decoded is an "unreadable csv" by the docstring's own definition.
- `--db <existing directory>` → `sqlite3.OperationalError: unable to open database file` escapes `main()`.
- A cell exceeding `csv.field_size_limit` (128 KB) — the exact DoS bound T-04-04 cites as mitigation — raises `csv.Error`, which also escapes, converting the "mitigation" into an unhandled crash.
- Additionally, when the caught `OSError` originates from the DB side (`connect()`'s `mkdir` hitting `PermissionError`), the error message misleadingly says "failed to read census csv".

**Fix:**
```python
    try:
        summary = refresh(csv_path, args.db, captured_at)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        log.error("failed to read census csv %s: %s", csv_path, exc)
        return 1
    except sqlite3.Error as exc:
        log.error("database error at %s: %s", args.db, exc)
        return 1
```
(`import csv` is stdlib and already an indexer dependency; alternatively split the load and the persist into separate try blocks inside `refresh()` so the CSV-vs-DB origin is unambiguous.)

### WR-03: Log injection via the CSV `id` cell — T-04-02 mitigation incomplete

**File:** `indexer/census.py:68,73`
**Issue:** T-04-02's mitigation states warnings carry "row number + id ONLY, never raw cell text" — but `row_id` **is** raw cell text (`_cell` strips ends only; internal newlines survive inside a quoted id cell). Reproduced end-to-end with a crafted census file whose id cell is `"4137\nERROR indexer.census: fake injected line"`:

```
WARNING indexer.census: row 2 id=4137
ERROR indexer.census: fake injected line: sold unparseable, storing 0
```

A forged ERROR line appears in the log. `test_warning_references_row_and_id` asserts no newline in the message but only against the benign committed census, so it cannot catch this. (Note `refresh.py:129` already does this correctly by logging the filename with `%r`.)
**Fix:** Log the id with `%r` so newlines/CJK are escaped — the existing test still passes (`'4137'` contains `4137`, no raw `\n`):
```python
log.warning("row %d id=%r: sold unparseable, storing 0", row_num, row_id)
...
log.warning("row %d id=%r: price unparseable, storing NULL", row_num, row_id)
```

### WR-04: `parse_price` and `_price_token` disagree on no-space `"5USDT"` — price echo stored as a genuine rating

**File:** `indexer/parse.py:14,52-54`
**Issue:** `_PLAIN_PRICE` uses `\s*` before "USDT", so `parse_price("5USDT")` returns `5.0` — but `_price_token` only strips the suffix when the cell `endswith(" USDT")` (with a space). The two functions guarding the same invariant disagree on the same cell. Reproduced:

```
parse_price("5USDT")                                  -> 5.0
parse_rating_positive("5", "100% positive", "5USDT")  -> (5.0, 100.0)   # echo NOT detected
parse_rating_positive("5", "100% positive", "5 USDT") -> (None, 100.0)  # echo detected
```

The consequence is storing a false 5-star rating — the exact silent-corruption trap rule A exists to prevent (it needs a non-empty positive cell to fire, i.e. the paragraph-positive variant). Zero occurrences in the committed census (always `" USDT"`), and the code matches the plan's verbatim spec — so this is an inherited spec-level edge, flagged for a conscious decision before Phase 5 reuses these parsers.
**Fix:** Make token extraction tolerate the same whitespace as `_PLAIN_PRICE`:
```python
def _price_token(price_cell: str) -> str:
    s = price_cell.strip()
    return re.sub(r"\s*USDT$", "", s).strip()
```

## Info

### IN-01: `--captured-at` and filename-derived dates are never validated

**File:** `indexer/refresh.py:34,124-135`
**Issue:** `_FILENAME_DATE` (`\d{4}-\d{2}-\d{2}`) accepts impossible dates ("census-9999-99-99.csv" → `9999-99-99T00:00:00Z`), and `--captured-at` accepts any string (`--captured-at banana` is stored verbatim into `first_seen`/`last_seen`/`captured_at`). The schema documents these columns as ISO-8601 UTC, and later phases will sort/compare them lexicographically. Local operator input, so low risk.
**Fix:** Validate before use and return 2 on failure, e.g. `re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", captured_at)` (regex keeps the no-`datetime.now` grep gates clean).

### IN-02: `load_census` doesn't guard against empty or duplicate ids — silent merge and overstated summary

**File:** `indexer/census.py:56,79-92` and `indexer/refresh.py:77-82`
**Issue:** An empty `id` cell produces a PK of `""` (satisfies NOT NULL), and two rows sharing an id in one file silently merge via the upsert while `RefreshSummary.agents` reports `len(records)` — so the INDX-01 "N agents" log line could overstate the DB row count on a future census. The committed census has 272 unique numeric ids, so this is purely defensive.
**Fix:** Warn (row number + `%r` id) on empty/duplicate ids during load, or derive `agents` in the summary from `len({r.id for r in records})`.

### IN-03: `connect()` ignores the `journal_mode` pragma result

**File:** `indexer/db.py:102`
**Issue:** `PRAGMA journal_mode=WAL` returns the mode actually in effect; on filesystems where WAL is unavailable (e.g., some network shares) SQLite silently stays in rollback-journal mode while the docstring and locked decision claim WAL. `test_wal_mode` pins the local environment only.
**Fix:**
```python
mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
if mode != "wal":
    logging.getLogger("indexer.db").warning("WAL unavailable, journal_mode=%s", mode)
```

---

_Reviewed: 2026-07-10T22:41:40Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
