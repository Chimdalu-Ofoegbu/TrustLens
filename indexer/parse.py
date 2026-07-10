"""Pure field parsers for the OKX.AI census CSV.

Every rule verified against all 272 rows of the real census
(.planning/phases/01-foundation-data-indexer/01-RESEARCH.md).
Parsers never raise on malformed input.
"""
from __future__ import annotations

import re
import unicodedata

_SOLD = re.compile(r"([\d,]+(?:\.\d+)?)\s*([KMkm])?\s*sold")
_SUB = {chr(0x2080 + i): i for i in range(10)}  # U+2080..U+2089 -> 0..9
_PLAIN_PRICE = re.compile(r"(\d+(?:\.\d+)?)\s*USDT")
_SUB_PRICE = re.compile(r"0\.0([₀-₉])(\d+)\s*USDT")
_PCT = re.compile(r"(\d+(?:\.\d+)?)% positive")


def parse_sold(cell: str) -> int | None:
    """'539 sold' -> 539, '1.55K sold' -> 1550, blank -> 0 (locked: missing/blank means zero).

    Returns None only for non-blank unparseable text (real case: id 4137 carries a
    417-char paragraph in this column) - the caller stores 0 and logs a warning.
    """
    s = cell.strip()
    if not s:
        return 0
    m = _SOLD.fullmatch(s)
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    mult = {"K": 1_000, "M": 1_000_000}.get((m.group(2) or "").upper(), 1)
    return int(round(n * mult))


def parse_price(cell: str) -> float | None:
    """'0.01 USDT' -> 0.01; subscript-zero '0.0₄15 USDT' -> 0.000015.

    Subscript digit N = TOTAL zeros between the decimal point and the significant
    digits (the displayed literal 0 after the point is stylistic, NOT an extra zero).
    """
    s = cell.strip()
    if not s:
        return None                      # 28 real rows have a blank price
    if (m := _SUB_PRICE.fullmatch(s)):
        return float(f"0.{'0' * _SUB[m.group(1)]}{m.group(2)}")
    if (m := _PLAIN_PRICE.fullmatch(s)):
        return float(m.group(1))
    return None                          # unseen format -> NULL, caller warns


def _price_token(price_cell: str) -> str:
    s = price_cell.strip()
    return s[: -len(" USDT")].strip() if s.endswith(" USDT") else s


def parse_rating_positive(rating_cell: str, positive_cell: str,
                          price_cell: str) -> tuple[float | None, float | None]:
    """Rating rule A (validated: 90 rated / 182 unrated, zero misclassifications).

    rating is valid iff positive is non-empty AND the rating string is not a
    character-for-character echo of the price number AND 0 <= value <= 5.
    positive_pct is valid iff it fullmatches 'N% positive'.
    """
    rt, pos = rating_cell.strip(), positive_cell.strip()
    pct = float(m.group(1)) if (m := _PCT.fullmatch(pos)) else None
    rating = None
    if pos and rt and rt != _price_token(price_cell):
        try:
            v = float(rt)
            rating = v if 0.0 <= v <= 5.0 else None
        except ValueError:
            rating = None
    return rating, pct


def name_key(name: str) -> str:
    """NFKC-casefolded lookup key. NOT unique: real census has 2 name collisions."""
    return unicodedata.normalize("NFKC", name).casefold().strip()
