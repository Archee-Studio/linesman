"""Views: the required views exist at the right size, line up as a projection, and sit in first-angle places."""

import math
import re
from contextlib import suppress
from itertools import product

from ezdxf import bbox as ezbbox

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
    match = _assign(truth.views, found, factor, sheet)
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
        *_section(sheet, truth, match, factor),
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


def _split_candidates(view: View, found: list[Region], factor: float, hatches: list) -> list[Region]:
    """A section drawn as two hatched walls (no far-edge lines) reads as two regions sharing one axis's extents;
    their union is the section view. Only offered for views that must hold hatching."""
    unions = []
    for a, b in product(found, found):
        if a is b:
            continue
        same_x = abs(a.x0 - b.x0) <= TOL and abs(a.x1 - b.x1) <= TOL
        same_y = abs(a.y0 - b.y0) <= TOL and abs(a.y1 - b.y1) <= TOL
        if not (same_x or same_y):
            continue
        box = (min(a.x0, b.x0), min(a.y0, b.y0), max(a.x1, b.x1), max(a.y1, b.y1))
        union = Region(*box, entities=a.entities + b.entities, handles=a.handles + b.handles)
        if not _fits(view, union, factor):
            continue

        def hatched(r: Region) -> bool:
            return any(
                hb[0] < r.x1 - TOL and hb[2] > r.x0 + TOL and hb[1] < r.y1 - TOL and hb[3] > r.y0 + TOL
                for hb in hatches
            )

        if hatched(a) and hatched(b):
            unions.append(union)
    return unions[:CANDIDATES]


def _assign(
    wanted: tuple[View, ...], found: list[Region], factor: float, sheet: Sheet | None = None
) -> dict[str, Region]:
    """One region per view, each used once: most views matched first, then most projection relations holding."""
    hatches = []
    if sheet is not None:
        for e in sheet.doc.modelspace().query("HATCH"):
            with suppress(Exception):
                hb = ezbbox.extents([e])
                if hb.has_data:
                    hatches.append((hb.extmin.x, hb.extmin.y, hb.extmax.x, hb.extmax.y))
    options = []
    for v in wanted:
        cands = [r for r in found if _fits(v, r, factor)][:CANDIDATES]
        if v.hatch_area is not None and hatches:
            cands += _split_candidates(v, found, factor, hatches)
        options.append(cands + [None])
    best: tuple[int, int] = (-1, -1)
    chosen: dict[str, Region] = {}
    for combo in product(*options):
        used = [h for r in combo if r is not None for h in r.handles]
        if len(used) != len(set(used)):
            continue
        match = {v.name: r for v, r in zip(wanted, combo, strict=True) if r is not None}
        a, p = _relations(match)
        score = (len(match), sum(ok for _, ok in a + p))
        if score > best:
            best, chosen = score, match
    return chosen


def _relations(match: dict[str, Region]) -> tuple[list[tuple[str, bool]], list[tuple[str, bool]]]:
    """(alignment, placement) results of every view matched against the front (or section) view."""
    front = match.get("front") or match.get("section")
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


_SECTION_LABEL = re.compile(r"A\s*[-\u2013]\s*A")
HATCH_TOLERANCE = 0.02  # the cut area may differ from the truth by this share


def _hatch_area(e) -> float:
    """Filled area of one HATCH by even-odd rule: outer paths add, paths inside them subtract."""

    def shoelace(pts):
        return abs(sum(ax * by - bx * ay for (ax, ay), (bx, by) in zip(pts, [*pts[1:], pts[0]], strict=False)) / 2)

    def inside(p, poly):
        x, y = p
        hits = sum(
            1
            for (ax, ay), (bx, by) in zip(poly, [*poly[1:], poly[0]], strict=False)
            if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax
        )
        return hits % 2 == 1

    polys = []
    try:
        for path in e.paths:
            vertices = path.flattening(0.05) if hasattr(path, "flattening") else path.vertices
            pts = [(v[0], v[1]) for v in vertices]
            if len(pts) > 2:
                polys.append((pts, shoelace(pts)))
    except Exception:
        return math.nan

    depth = [sum(1 for other, _ in polys if other is not pts and inside(pts[0], other)) for pts, _ in polys]
    return abs(sum(a if d % 2 == 0 else -a for (pts, a), d in zip(polys, depth, strict=True)))


def _section(sheet: Sheet, truth: Truth, match: dict[str, Region], factor: float) -> list[CheckResult]:
    """A required section view holds hatching of the true cut area and an A-A label."""
    wanted = [v for v in truth.views if v.hatch_area is not None]
    if not wanted:
        return []
    detail = []
    hatches = [e for e in sheet.doc.modelspace().query("HATCH")]
    for v in wanted:
        region = match.get(v.name)
        if region is None:
            detail.append(f"no region of the size of the {v.name} view")
            continue
        inside = [
            e
            for e in hatches
            if (b := ezbbox.extents([e])).has_data
            and b.extmin.x >= region.x0 - TOL
            and b.extmin.y >= region.y0 - TOL
            and b.extmax.x <= region.x1 + TOL
            and b.extmax.y <= region.y1 + TOL
        ]
        if not inside:
            detail.append(f"the {v.name} view holds no hatching")
            continue
        shown = sum(a for e in inside if math.isfinite(a := _hatch_area(e))) / (factor * factor)
        if abs(shown - v.hatch_area) > HATCH_TOLERANCE * v.hatch_area:
            detail.append(f"the {v.name} view hatches {shown:g} mm2, not {v.hatch_area:g}")
    if not any(_SECTION_LABEL.search(t.text) for t in sheet.texts):
        detail.append("no A-A section label on the sheet")
    return [
        CheckResult(
            id="views.section",
            part="views",
            critical=True,
            score=1.0 - len(detail) / (2 * len(wanted)) if wanted else 1.0,
            detail=tuple(detail),
        )
    ]
