"""Views: the required views exist at the right size, line up as a projection, and sit in first-angle places."""

import re
from itertools import product

from ..regions import TOL, Region, regions
from ..schema import CheckResult, Task, Truth, View
from ..sheet import Sheet

CANDIDATES = 4  # regions of the right size tried per view; identical views beyond this are ignored

# View -> the view it is placed against. Only these names have a projection place in first-angle layout.
ALIGN_X = ("top", "bottom")  # share the front's x-extents
ALIGN_Y = ("left", "right")  # share the front's y-extents


def views(sheet: Sheet, task: Task, truth: Truth) -> list[CheckResult]:
    found = regions(sheet)
    factor = _factor(truth.scale)
    match = _assign(truth.views, found, factor)
    aligned, placed = _relations(match)
    required = len(truth.views)
    if not required:
        return []
    missing = [v.name for v in truth.views if v.name not in match]
    return [
        CheckResult(
            id="views.present",
            part="views",
            critical=True,
            score=len(match) / required,
            detail=tuple(f"no region of the size of the {n} view" for n in missing),
        ),
    ] + [
        r
        for r in (
            _ratio("views.aligned", aligned, len(match), required),
            _ratio("views.first_angle", placed, len(match), required),
        )
        if r
    ]


def _ratio(check: str, results: list[tuple[str, bool]], matched: int, required: int) -> CheckResult | None:
    """Share of the judged relations that hold; None when one view is required (nothing to relate)."""
    if required < 2:
        return None
    score = sum(ok for _, ok in results) / len(results) if results else float(matched > 0)
    return CheckResult(
        id=check, part="views", critical=True, score=score, detail=tuple(n for n, ok in results if not ok)
    )


def _factor(scale: str) -> float:
    found = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*", scale)
    if not found or float(found.group(2)) == 0 or float(found.group(1)) == 0:
        return 1.0
    return float(found.group(1)) / float(found.group(2))


def _fits(view: View, region: Region, factor: float) -> bool:
    return abs(region.width - view.width * factor) <= TOL and abs(region.height - view.height * factor) <= TOL


def _assign(wanted: tuple[View, ...], found: list[Region], factor: float) -> dict[str, Region]:
    """One region per view, each used once: most views matched first, then most projection relations holding."""
    options = [[r for r in found if _fits(v, r, factor)][:CANDIDATES] + [None] for v in wanted]
    best: tuple[int, int] = (-1, -1)
    chosen: dict[str, Region] = {}
    for combo in product(*options):
        used = [id(r) for r in combo if r is not None]
        if len(used) != len(set(used)):
            continue
        match = {v.name: r for v, r in zip(wanted, combo, strict=True) if r is not None}
        a, p = _relations(match)
        score = (len(match), sum(ok for _, ok in a + p))
        if score > best:
            best, chosen = score, match
    return chosen


def _relations(match: dict[str, Region]) -> tuple[list[tuple[str, bool]], list[tuple[str, bool]]]:
    """(alignment, placement) results of every view matched against the front view."""
    front = match.get("front")
    if front is None:
        return [], []
    aligned: list[tuple[str, bool]] = []
    placed: list[tuple[str, bool]] = []
    for name, r in match.items():
        if name in ALIGN_X:
            aligned.append(
                (f"{name} view does not share the front's x-extents", _same(r.x0, front.x0) and _same(r.x1, front.x1))
            )
        if name in ALIGN_Y:
            aligned.append(
                (f"{name} view does not share the front's y-extents", _same(r.y0, front.y0) and _same(r.y1, front.y1))
            )
        place = {
            "top": r.y1 <= front.y0 + TOL,
            "bottom": r.y0 >= front.y1 - TOL,
            "left": r.x0 >= front.x1 - TOL,
            "right": r.x1 <= front.x0 + TOL,
        }.get(name)
        if place is not None:
            expected = {"top": "below", "bottom": "above", "left": "right of", "right": "left of"}[name]
            placed.append((f"{name} view is not {expected} the front view (first-angle projection)", place))
    return aligned, placed


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= TOL
