"""Shared record types for the TrustLens indexer.

AgentRecord is the contract between source loaders (indexer.census now,
the Phase 5 scraper later) and the persistence layer (indexer.db).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRecord:
    """One marketplace agent as parsed from a source."""

    id: str
    name: str                  # unicode preserved exactly as listed
    name_key: str              # NFKC-casefolded lookup key (NOT unique - real collisions exist)
    category: str              # derived bucket name (never empty)
    tagline: str               # may contain embedded newlines (multiline census cells)
    price_usdt: float | None   # None for 28 census rows
    price_raw: str             # original price cell for display; "" when blank
    sold: int                  # blank/unparseable -> 0 (never None)
    rating: float | None       # None unless the validated rating rule passes
    positive_pct: float | None
    category_source: str = "derived"  # 'derived' now; 'listed' when Phase 5 scraper finds the real one
