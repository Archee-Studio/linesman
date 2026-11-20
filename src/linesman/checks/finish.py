"""Surface finish: every required Ra mark sits near the dimension it finishes (ISO 1302)."""

import re

from ..schema import CheckResult, Task, Truth
from ..sheet import Dimension, Sheet
from .dims import agrees, numeric

NEAR = 30.0  # mm: a roughness mark must sit this close to the dimension of the surface it marks
_RA = re.compile(r"Ra\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)


def finish(sheet: Sheet, task: Task, truth: Truth) -> list[CheckResult]:
    if not truth.finish:
        return []  # no finish required: the check does not apply
    shown = numeric(sheet)
    marks = [(t, _RA.search(t.text)) for t in sheet.texts]
    detail = []
    owner: dict[int, str] = {}  # a sheet dimension anchors one required mark: identical twins are interchangeable
    for dim_id, ra in truth.finish.items():
        dim = next(d for d in truth.dims if d.id == dim_id)
        spots = [i for i, s in enumerate(shown) if agrees(dim, s) and _near(s, ra, marks)]
        if not spots or not _claim(dim_id, spots, owner, truth, shown, marks):
            detail.append(f"no Ra {ra:g} mark within {NEAR:g} mm of the {dim_id} dimension")
    return [
        CheckResult(
            id="finish.roughness",
            part="finish",
            critical=True,
            score=1.0 - len(detail) / len(truth.finish),
            detail=tuple(detail),
        )
    ]


def _near(s: Dimension, ra: float, marks: list) -> bool:
    return any(
        m and abs(float(m.group(1).replace(",", ".")) - ra) < 0.01 and abs(t.x - s.x) <= NEAR and abs(t.y - s.y) <= NEAR
        for t, m in marks
    )


def _claim(dim_id: str, spots: list[int], owner: dict[int, str], truth: Truth, shown: list, marks: list) -> bool:
    """Take a free spot, or ask the spot's owner to move to another spot it can use."""
    wanted = {d.id: d for d in truth.dims}
    for i in spots:
        if i not in owner:
            owner[i] = dim_id
            return True
        other = wanted[owner[i]]
        alt = [
            j
            for j, s in enumerate(shown)
            if agrees(other, s) and _near(s, truth.finish[other.id], marks) and j != i and j not in owner
        ]
        if alt:
            owner[alt[0]] = other.id
            owner[i] = dim_id
            return True
    return False
