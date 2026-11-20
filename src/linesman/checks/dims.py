"""Dimension recall and precision: every required dimension drawn once with the right value, nothing extra."""

import math
import re

from ..geo import point_distance
from ..regions import regions
from ..schema import CheckResult, Dim, Task, Truth
from ..sheet import Dimension, Sheet
from .views import _assign, _factor

LINEAR_TOLERANCE = 0.01  # mm
ANGULAR_TOLERANCE = 0.1  # degrees
_DIAMETER_MARK = re.compile(r"%%[cC]|[Øø⌀]")


def kind_of(dimension: Dimension) -> str:
    """A linear dimension with a diameter prefix is a diameter."""
    if dimension.kind == "linear" and _DIAMETER_MARK.search(dimension.text):
        return "diameter"
    return dimension.kind


def numeric(sheet: Sheet) -> list[Dimension]:
    return [d for d in sheet.dims if math.isfinite(d.value)]


def agrees(dim: Dim, shown: Dimension) -> bool:
    tolerance = ANGULAR_TOLERANCE if dim.kind == "angular" else LINEAR_TOLERANCE
    return kind_of(shown) == dim.kind and any(abs(shown.value - v) <= tolerance + 1e-9 for v in (dim.value, *dim.alt))


def match(sheet: Sheet, truth: Truth, prefer=None) -> dict[str, Dimension]:
    """One-to-one assignment of required dimensions to sheet dimensions of the same kind and value.

    `prefer(dim, shown)` ranks candidates first when true; fitted dimensions are assigned before the rest so that the
    sheet dimension showing the fit is the one that gets credited (fits.py reads the same assignment).
    """
    shown = numeric(sheet)
    owner: dict[int, str] = {}  # sheet dimension index -> truth dim id
    wanted = {d.id: d for d in truth.dims}

    def candidates(dim: Dim, only: bool) -> list[int]:
        found = [i for i, s in enumerate(shown) if agrees(dim, s)]
        if prefer:
            found = (
                [i for i in found if prefer(dim, shown[i])]
                if only
                else sorted(found, key=lambda i: not prefer(dim, shown[i]))
            )
        return found

    def assign(dim: Dim, only: bool, seen: set[int]) -> bool:
        for i in candidates(dim, only):
            if i in seen:
                continue
            seen.add(i)
            if i not in owner or (i not in frozen and assign(wanted[owner[i]], only, seen)):
                owner[i] = dim.id
                return True
        return False

    frozen: set[int] = set()
    if prefer:
        for dim in (d for d in truth.dims if d.fit):
            assign(dim, True, set())
        frozen = set(owner)
    for dim in truth.dims:
        if dim.id not in owner.values():
            assign(dim, False, set())
    return {dim_id: shown[i] for i, dim_id in owner.items()}


def _in_region(shown: Dimension, region) -> bool:
    return all(
        region.x0 - REGION_SLACK <= px <= region.x1 + REGION_SLACK
        and region.y0 - REGION_SLACK <= py <= region.y1 + REGION_SLACK
        for px, py in shown.points
    )


def dims(sheet: Sheet, task: Task, truth: Truth) -> list[CheckResult]:
    placed = _assign(truth.views, regions(sheet), _factor(truth.scale), sheet)
    # a dimension of a view's feature sits on that view's geometry: prefer candidates inside its region
    matched = match(sheet, truth, prefer=lambda dim, shown: dim.view in placed and _in_region(shown, placed[dim.view]))
    missing = [d.id for d in truth.dims if d.id not in matched]
    drawn = numeric(sheet)
    extra = [f"{kind_of(s)} {s.value:g}" for s in drawn if not any(s is m for m in matched.values())]
    if not truth.dims:
        return []
    recall = len(matched) / len(truth.dims)
    precision = len(matched) / len(drawn) if drawn else 0.0
    results = [
        CheckResult(
            id="dims.recall",
            part="dims",
            critical=True,
            score=recall,
            detail=tuple(f"missing {m}" for m in missing),
        ),
        CheckResult(
            id="dims.precision",
            part="dims",
            critical=False,
            score=min(precision, 1.0),
            detail=tuple(f"unmatched {e}" for e in extra),
        ),
        _true(sheet, truth),
        _attached(sheet, truth, placed, matched),
    ]
    return results


ATTACH_TOLERANCE = 0.2  # mm: a definition point must sit on drawn geometry
REGION_SLACK = 0.5  # mm: a definition point may sit just outside the view's outline


def _honest(shown: Dimension, factor: float) -> bool:
    """The displayed value reads the geometry: it equals measurement * DIMLFAC, or measurement / scale factor."""
    if not math.isfinite(shown.measured):
        return False  # an unknown measurement cannot be verified
    tolerance = ANGULAR_TOLERANCE if shown.kind == "angular" else LINEAR_TOLERANCE
    if abs(shown.value - shown.measured) <= tolerance + 1e-9:
        return True
    return math.isfinite(shown.raw) and abs(shown.value - shown.raw / factor) <= tolerance + 1e-9


def _true(sheet: Sheet, truth: Truth) -> CheckResult:
    """Share of numeric dimensions whose text tells the truth (an override can lie)."""
    shown = numeric(sheet)
    lying = [
        f"{kind_of(d)} {d.value:g} (measured {d.measured:g})" for d in shown if not _honest(d, _factor(truth.scale))
    ]
    return CheckResult(
        id="dims.true",
        part="dims",
        critical=True,
        score=1.0 - len(lying) / len(shown) if shown else 0.0,
        detail=tuple(f"{t} does not match the geometry" for t in lying),
    )


def _attached(sheet: Sheet, truth: Truth, placed: dict, matched: dict[str, Dimension]) -> CheckResult:
    """Share of matched dimensions whose definition points sit on geometry inside one matched view's region.

    ISO lets the drafter pick the view a feature is dimensioned in, so any region matched to a required view
    counts; `Dim.view` only steers credit in `match`, it does not constrain attachment.
    """
    detail = []
    seen = set()
    views = [r for r in placed.values() if not (id(r) in seen or seen.add(id(r)))]
    for want in truth.dims:
        shown = matched.get(want.id)
        if shown is None:
            continue
        attached = bool(shown.points) and any(
            all(
                r.x0 - REGION_SLACK <= px <= r.x1 + REGION_SLACK and r.y0 - REGION_SLACK <= py <= r.y1 + REGION_SLACK
                for px, py in shown.points
            )
            and all(min(point_distance(e, p) for e in r.entities) <= ATTACH_TOLERANCE for p in shown.points)
            for r in views
        )
        if not attached:
            sample = f"{shown.points[0][0]:g},{shown.points[0][1]:g}" if shown.points else "none"
            detail.append(f"{want.id}: definition points ({sample}, ...) not on geometry in any one view")
    return CheckResult(
        id="dims.attached",
        part="dims",
        critical=True,
        score=1.0 - len(detail) / len(matched) if matched else 0.0,
        detail=tuple(detail),
    )
