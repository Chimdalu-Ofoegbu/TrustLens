"""Badge SVG contract tests (UI-SPEC Badge SVG Contract).

Pins the fixed 110x20 two-segment geometry, the grade color table, the
accessibility contract (title-first + role + aria-label), the neutral
unknown-agent wording, the 1KB weight budget, byte determinism, and the
banned-vocabulary source scan extended over web/badge.py.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from web.badge import GRADE_BADGE_COLORS, badge_svg

REPO_ROOT = Path(__file__).resolve().parents[1]
BADGE_SOURCE = REPO_ROOT / "web" / "badge.py"
# Mirror of the tests/test_scoring_golden.py source-scan pattern; the regex
# literal lives here in tests/, outside the scanned tree.
BANNED = re.compile(r"(?i)(fraud|scam|fake|manipulat)")

SVG_NS = "{http://www.w3.org/2000/svg}"


def _right_text(svg: str) -> str:
    """Text content of the right-segment <text> element (centered at x=87)."""
    root = ET.fromstring(svg)
    for el in root.iter(f"{SVG_NS}text"):
        if el.get("x") == "87":
            return el.text or ""
    raise AssertionError("no right-segment <text> element at x=87")


def test_grade_a_badge_is_valid_xml_with_contract_geometry():
    svg = badge_svg("A", 94)
    root = ET.fromstring(svg)  # must parse as valid XML
    assert 'viewBox="0 0 110 20"' in svg
    assert 'role="img"' in svg
    first_child = list(root)[0]  # <title> must be the FIRST child of <svg>
    assert first_child.tag == f"{SVG_NS}title"
    assert first_child.text == "TrustLens grade A"
    assert _right_text(svg) == "A 94"
    assert 'fill="#166534"' in svg


@pytest.mark.parametrize(
    ("grade", "score", "color"),
    [
        ("B", 82, "#115E59"),
        ("C", 60, "#854D0E"),
        ("D", 45, "#9A3412"),
        ("F", 20, "#9F1239"),
        ("NR", None, "#475569"),
    ],
)
def test_grade_color_per_band(grade, score, color):
    assert f'fill="{color}"' in badge_svg(grade, score)


def test_nr_right_text_is_exactly_nr_without_score():
    assert _right_text(badge_svg("NR", None)) == "NR"


def test_unknown_agent_renders_neutral_na_badge():
    svg = badge_svg(None, None)
    assert _right_text(svg) == "N/A"
    assert 'fill="#475569"' in svg
    assert 'aria-label="TrustLens: agent not found"' in svg


def test_unrecognized_grade_string_also_falls_back_to_unknown():
    svg = badge_svg("Z", 99)
    assert _right_text(svg) == "N/A"
    assert 'aria-label="TrustLens: agent not found"' in svg


def test_badge_stays_under_1kb_budget():
    assert len(badge_svg("A", 100).encode("utf-8")) <= 1024


def test_badge_is_deterministic():
    assert badge_svg("B", 82) == badge_svg("B", 82)


def test_every_grade_in_color_table_produces_valid_svg():
    for grade in GRADE_BADGE_COLORS:
        score = None if grade == "NR" else 70
        ET.fromstring(badge_svg(grade, score))


def test_banned_vocabulary_absent_from_badge_source():
    assert not BANNED.search(BADGE_SOURCE.read_text(encoding="utf-8"))
