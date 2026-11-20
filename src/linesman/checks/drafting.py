"""Drafting hygiene: views and dimensions on the sheet, legible text, clearance and linetype conventions."""

import math

from ezdxf import bbox as ezbbox

from ..geo import entity_hits_box, linetype_class, point_distance, text_box
from ..regions import TOL, Region, _centre_line, frame, regions, title_block
from ..schema import CheckResult, Task, Truth
from ..sheet import Sheet
from .views import _assign, _factor

MIN_TEXT = 2.5  # mm: smallest legible height, ISO 3098 / TCVN
MIN_CIRCLE = 3.0  # mm: circles this small are not expected to carry centre marks
CENTRE_GAP = 0.5  # mm: a centre line may pass this far off a circle's centre
SHRINK = 0.9  # text boxes are shrunk this much: ezdxf boxes are font approximations

Box = tuple[float, float, float, float]


def _entity(sheet: Sheet, handle: str):
    return sheet.doc.entitydb.get(handle)


def _shrink(b: Box) -> Box:
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    hw, hh = (b[2] - b[0]) * SHRINK / 2, (b[3] - b[1]) * SHRINK / 2
    return (cx - hw, cy - hh, cx + hw, cy + hh)


def _inside(b: Box, outer: Box, tol: float = TOL) -> bool:
    return b[0] >= outer[0] - tol and b[1] >= outer[1] - tol and b[2] <= outer[2] + tol and b[3] <= outer[3] + tol


def _cross(a: Box, b: Box, tol: float = 0.01) -> bool:
    return a[0] < b[2] - tol and a[2] > b[0] + tol and a[1] < b[3] - tol and a[3] > b[1] + tol


def _dim_box(sheet: Sheet, handle: str) -> Box | None:
    e = _entity(sheet, handle)
    if e is None:
        return None
    try:
        b = ezbbox.extents([e])
        if b.has_data and all(map(math.isfinite, (*b.extmin, *b.extmax))):
            return (b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y)
    except Exception:
        pass
    return None


def _on_sheet(sheet: Sheet, found: list[Region]) -> CheckResult:
    fbox = frame(sheet)
    if fbox is None:
        return CheckResult(
            id="drafting.on_sheet",
            part="drafting",
            critical=True,
            score=0.0,
            detail=("no frame: a closed rectangle spanning the sheet",),
        )
    tbox = title_block(sheet)
    detail = []
    for r in found:
        box = (r.x0, r.y0, r.x1, r.y1)
        if not _inside(box, fbox):
            detail.append("a view lies outside the frame")
        elif tbox and _cross(box, tbox):
            detail.append("a view overlaps the title block")
    for d in sheet.dims:
        box = _dim_box(sheet, d.handle)
        if box is None:
            continue
        if not _inside(box, fbox):
            detail.append(f"dimension {d.value:g} lies outside the frame")
        elif tbox and _cross(box, tbox):
            detail.append(f"dimension {d.value:g} overlaps the title block")
    total = len(found) + len(sheet.dims)
    return CheckResult(
        id="drafting.on_sheet",
        part="drafting",
        critical=True,
        score=1.0 - len(detail) / total if total else 1.0,
        detail=tuple(detail),
    )


def _dim_text_boxes(sheet: Sheet, handle: str) -> list[Box]:
    """WCS boxes of the text inside a dimension's rendered block."""
    e = _entity(sheet, handle)
    boxes = []
    if e is not None:
        try:
            for v in e.virtual_entities():
                if v.dxftype() in ("TEXT", "MTEXT") and (b := text_box(v)) is not None:
                    boxes.append(b)
        except Exception:
            pass
    return boxes


def _text_heights(sheet: Sheet) -> tuple[list[str], list[float]]:
    """(labels, heights) of every sheet text and every text inside the dimension blocks."""
    labels = [f'"{t.text}"' for t in sheet.texts]
    heights = [t.height for t in sheet.texts]
    for d in sheet.dims:
        e = _entity(sheet, d.handle)
        if e is None:
            continue
        try:
            hs = [
                v.dxf.get("char_height", 0.0) if v.dxftype() == "MTEXT" else v.dxf.get("height", 0.0)
                for v in e.virtual_entities()
                if v.dxftype() in ("TEXT", "MTEXT")
            ]
        except Exception:
            hs = []
        labels += [f"dimension {d.value:g}"] * len(hs)
        heights += hs
    return labels, heights


def _text(sheet: Sheet) -> CheckResult:
    labels, heights = _text_heights(sheet)
    small = [n for n, h in zip(labels, heights, strict=True) if h < MIN_TEXT - 1e-9]
    return CheckResult(
        id="drafting.text",
        part="drafting",
        critical=True,
        score=1.0 - len(small) / len(heights) if heights else 1.0,
        detail=tuple(f"{n} is under {MIN_TEXT:g} mm tall" for n in small),
    )


def _clear(sheet: Sheet, found: list[Region]) -> CheckResult:
    """No two texts overlap; no dimension text crosses view geometry (centre lines excepted)."""
    boxes = [(t.text, t.box) for t in sheet.texts if t.box is not None]
    dim_boxes = {d.handle: _dim_text_boxes(sheet, d.handle) for d in sheet.dims}
    all_text = boxes + [(f"dimension {d.value:g}", b) for d in sheet.dims for b in dim_boxes[d.handle]]
    detail = []
    for i, (name, b) in enumerate(all_text):
        if any(_cross(_shrink(b), _shrink(o)) for _, o in all_text[i + 1 :]):
            detail.append(f'text "{name}" overlaps another text')
    geometry = [e for r in found for e in r.entities if not _centre_line(sheet, e)]
    for d in sheet.dims:
        for b in dim_boxes[d.handle]:
            if any(entity_hits_box(e, _shrink(b)) for e in geometry):
                detail.append(f"dimension {d.value:g} text crosses view geometry")
                break
    total = len(all_text) + sum(len(v) for v in dim_boxes.values())
    return CheckResult(
        id="drafting.clear",
        part="drafting",
        critical=True,
        score=1.0 - len(detail) / total if total else 1.0,
        detail=tuple(detail),
    )


def _linetypes(sheet: Sheet, truth: Truth, found: list[Region], match: dict[str, Region]) -> CheckResult:
    """Circles carry centre lines; views required to show hidden features hold dashed geometry."""
    detail = []
    total = 0
    for r in found:
        for e in r.entities:
            if e.dxftype() == "CIRCLE" and 2 * e.dxf.radius >= MIN_CIRCLE:
                total += 1
                c = (e.dxf.center.x, e.dxf.center.y)
                if not any(
                    linetype_class(sheet.doc, o) == "center" and point_distance(o, c) <= CENTRE_GAP
                    for o in r.entities
                    if o is not e
                ):
                    detail.append(f"circle at {c[0]:g},{c[1]:g} has no centre line")
    for v in truth.views:
        if not v.hidden:
            continue
        total += 1
        region = match.get(v.name)
        if region is None or not any(linetype_class(sheet.doc, e) == "dashed" for e in region.entities):
            detail.append(f"the {v.name} view shows hidden features with no dashed lines")
    return CheckResult(
        id="drafting.linetypes",
        part="drafting",
        critical=False,
        score=1.0 - len(detail) / total if total else 1.0,
        detail=tuple(detail),
    )


def drafting(sheet: Sheet, task: Task, truth: Truth) -> list[CheckResult]:
    found = regions(sheet)
    match = _assign(truth.views, found, _factor(truth.scale), sheet)
    return [
        _on_sheet(sheet, found),
        _text(sheet),
        _clear(sheet, found),
        _linetypes(sheet, truth, found, match),
    ]
