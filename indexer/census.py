"""Census CSV -> AgentRecord loader. Offline only: reads a local file, zero network access.

Wiring rules (locked/verified against all 272 real rows, 01-RESEARCH.md):
- stdlib csv.DictReader over open(newline="", encoding="utf-8-sig") is the ONLY
  correct reader — 29 bare-LF newlines live inside quoted fields, so any
  line-based approach shears rows. Header: id,name,tagline,rating,positive,sold,price.
- Every field is stripped exactly once at ingest (30 taglines carry edge
  whitespace); stripping trims ends only, so internal newlines in multiline
  taglines are preserved.
- Rows are never skipped wholesale and field content never raises: unparseable
  fields degrade per the locked rules below (fail loud, don't crash).
- Warning messages carry ONLY row numbers and ids — never raw cell text.
  The id itself comes from a cell, so it is logged with %r: embedded newlines
  in cells would otherwise allow log injection, and CJK text crashes cp1252
  consoles (research Pitfall 6).
- No count assertions live here: the Phase 5 scrape loader changes counts, so
  the 272-row assertion belongs to the integration tests only.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from indexer.category import derive_category
from indexer.models import AgentRecord
from indexer.parse import name_key, parse_price, parse_rating_positive, parse_sold

log = logging.getLogger("indexer.census")

__all__ = ["load_census"]


def _cell(row: dict, key: str) -> str:
    """One stripped field. Missing/short-row values degrade to '' (never raise)."""
    return (row.get(key) or "").strip()


def load_census(csv_path: str | Path) -> tuple[list[AgentRecord], int]:
    """Parse the census CSV into records. Returns (records, field_warning_count).

    Field degradation rules (all research-verified):
    - sold: blank -> 0 silently (parser rule); non-blank prose -> 0 plus one
      warning (real case: id 4137 carries a 417-char paragraph here).
    - price: blank -> None with NO warning (28 real rows); a non-blank cell
      that fails to parse -> None plus a warning (defensive — 0 real cases).
      price_raw always stores the stripped original cell ("" when blank).
    - rating/positive: the rule-A echo gate in parse_rating_positive decides;
      unrated rows are expected data (182 real rows), never warned about.
    - category: derived from stripped name+tagline; category_source keeps the
      AgentRecord default "derived".
    """
    records: list[AgentRecord] = []
    warnings = 0
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row_num, row in enumerate(csv.DictReader(f), start=2):  # row 1 = header
            row_id = _cell(row, "id")
            name = _cell(row, "name")
            tagline = _cell(row, "tagline")
            rating_cell = _cell(row, "rating")
            positive_cell = _cell(row, "positive")
            sold_cell = _cell(row, "sold")
            price_cell = _cell(row, "price")

            sold = parse_sold(sold_cell)
            if sold is None:
                sold = 0
                warnings += 1
                log.warning("row %d id=%r: sold unparseable, storing 0", row_num, row_id)

            price = parse_price(price_cell)
            if price is None and price_cell:
                warnings += 1
                log.warning("row %d id=%r: price unparseable, storing NULL", row_num, row_id)

            rating, positive_pct = parse_rating_positive(
                rating_cell, positive_cell, price_cell
            )

            records.append(
                AgentRecord(
                    id=row_id,
                    name=name,
                    name_key=name_key(name),
                    category=derive_category(name, tagline),
                    tagline=tagline,
                    price_usdt=price,
                    price_raw=price_cell,
                    sold=sold,
                    rating=rating,
                    positive_pct=positive_pct,
                )
            )
    return records, warnings
