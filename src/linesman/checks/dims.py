"""Dimension recall and precision: every required dimension drawn once with the right value, nothing extra."""

import math
import re

from ..schema import CheckResult, Dim, Task, Truth
from ..sheet import Dimension, Sheet

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


def dims(sheet: Sheet, task: Task, truth: Truth) -> list[CheckResult]:
    matched = match(sheet, truth)
    missing = [d.id for d in truth.dims if d.id not in matched]
    drawn = numeric(sheet)
    extra = [f"{kind_of(s)} {s.value:g}" for s in drawn if not any(s is m for m in matched.values())]
    if not truth.dims:
        return []
    recall = len(matched) / len(truth.dims)
    precision = len(matched) / len(drawn) if drawn else 0.0
    return [
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
    ]
