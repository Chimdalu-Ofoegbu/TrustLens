"""Shared fixtures for server tests. Phase 1/2 test files do not request these."""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = REPO_ROOT / "data" / "okx-marketplace-census-2026-07-10.csv"
DB_PATH = REPO_ROOT / "data" / "trustlens.db"
SEED_TS = "2026-07-10T00:00:00Z"


@pytest.fixture(scope="session")
def real_db() -> Path:
    """data/trustlens.db seeded from the committed census (offline) when absent."""
    if not DB_PATH.exists():
        from indexer.refresh import refresh

        refresh(CSV_PATH, DB_PATH, SEED_TS)
    return DB_PATH
