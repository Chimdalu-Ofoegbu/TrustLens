"""TrustLens badge SVG generator (UI-SPEC Badge SVG Contract).

Pure module: no I/O, no wall clock, no randomness, no imports. The SVG is
a fixed 110x20 shields-style two-segment badge rendered from a deterministic
f-string template; the same (grade, score) input always yields identical
bytes. Output stays under the 1KB UI-SPEC performance budget.

Wording is neutral by contract: an unknown agent renders "N/A" with the
label "TrustLens: agent not found" — never an error tone.
"""
from __future__ import annotations

# UI-SPEC Badge SVG Contract — dark tones, all >=4.5:1 contrast with white text.
GRADE_BADGE_COLORS = {
    "A": "#166534",
    "B": "#115E59",
    "C": "#854D0E",
    "D": "#9A3412",
    "F": "#9F1239",
    "NR": "#475569",
}

_UNKNOWN_COLOR = "#475569"
_LEFT_COLOR = "#334155"  # slate-700 left segment


def badge_svg(grade: str | None, score: int | None) -> str:
    """Render the TrustLens badge for one agent as a self-contained SVG string.

    Known grade with a score -> right text "{grade} {score}" (e.g. "B 82");
    grade "NR" (score is None) -> right text "NR"; unknown grade (None or not
    in GRADE_BADGE_COLORS) -> right text "N/A" on the neutral gray segment.
    """
    if grade is None or grade not in GRADE_BADGE_COLORS:
        label = "TrustLens: agent not found"
        color = _UNKNOWN_COLOR
        right = "N/A"
    else:
        label = f"TrustLens grade {grade}"
        color = GRADE_BADGE_COLORS[grade]
        # NR never carries a score; a scoreless known grade renders bare too.
        right = grade if grade == "NR" or score is None else f"{grade} {score}"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 110 20" '
        f'width="110" height="20" role="img" aria-label="{label}">'
        f"<title>{label}</title>"
        '<clipPath id="r"><rect width="110" height="20" rx="3"/></clipPath>'
        '<g clip-path="url(#r)">'
        f'<rect width="64" height="20" fill="{_LEFT_COLOR}"/>'
        f'<rect x="64" width="46" height="20" fill="{color}"/>'
        "</g>"
        '<g fill="#FFFFFF" font-family="Verdana,\'DejaVu Sans\',Geneva,sans-serif" '
        'font-size="11" text-anchor="middle">'
        '<text x="32" y="14">TrustLens</text>'
        f'<text x="87" y="14">{right}</text>'
        "</g>"
        "</svg>"
    )
