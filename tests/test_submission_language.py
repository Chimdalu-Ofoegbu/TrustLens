"""Language gate over the outward-facing submission text (OPS-03 hardening).

Mirrors the canonical directory-scan in
``tests/test_scoring_golden.py::test_banned_vocabulary_source_layer``: the
banned-vocabulary regex literal lives HERE in ``tests/`` — outside the scanned
tree — so scanning ``submission/*.md`` + ``README.md`` never trips on this file
and never reaches any source directory (``indexer/category.py`` legitimately
carries such words in its keyword table).

This module runs inside the normal suite. It is NOT under ``--cov=scoring``, so
it neither dilutes nor inflates the coverage gate (no ``--no-cov`` needed for the
full run; use ``--no-cov`` only for a submission-only subset run).
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BANNED = re.compile(r"(?i)(fraud|scam|fake|manipulat)")
SUBMISSION = REPO / "submission"
README = REPO / "README.md"

KIT_FILES = ("demo-script.md", "x-post-draft.md", "listing-copy.md")


def _outward_files():
    """submission/*.md plus README.md (if present) — the whole outward surface."""
    files = sorted(SUBMISSION.glob("*.md"))
    if README.is_file():
        files.append(README)
    return files


def test_submission_dir_has_the_three_kit_files():
    for name in KIT_FILES:
        assert (SUBMISSION / name).is_file(), name


def test_banned_vocabulary_absent_from_outward_text():
    files = _outward_files()
    assert files, "no outward-facing text found to scan"
    # README.md must be in scope — the gate covers the whole outward surface,
    # not just submission/.
    assert README in files, "README.md not scanned"
    for path in files:
        assert not BANNED.search(path.read_text(encoding="utf-8")), path.name


def test_listing_tagline_within_80_chars():
    text = (SUBMISSION / "listing-copy.md").read_text(encoding="utf-8")
    # The required, tested contract: the primary tagline is a single line of the
    # exact form ``**Tagline:** <text>``.
    marker = "**Tagline:**"
    lines = [ln for ln in text.splitlines() if ln.startswith(marker)]
    assert len(lines) == 1, f"expected exactly one '{marker}' line, got {len(lines)}"
    tagline = lines[0][len(marker):].strip().strip("`").strip()
    assert tagline, "primary tagline is empty"
    assert len(tagline) <= 80, f"tagline is {len(tagline)} chars (limit 80): {tagline!r}"
    assert not BANNED.search(tagline), tagline
