"""Find the views on a sheet from geometry alone: drop the frame and the title block, cluster what is left."""

import math
from dataclasses import dataclass

from ezdxf import bbox as ezbbox

from .sheet import Sheet

GAP = 3.0  # mm: entities whose boxes are closer than this belong to one view
TOL = 0.5  # mm: slack for "the same extent" and "inside"
CORNER = 5.0  # mm: how far from the frame's lower-right corner a title block may start
CENTRE = ("CENTER", "CENTRE", "DASHDOT", "PHANTOM", "AXIS")  # linetypes or layer names of centre lines
MAX_LINES = 5000  # line-built rectangles are searched only on sheets with fewer lines than this

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Region:
    """One view: the box of its outline (centre lines excluded), its entities and their handles."""

    x0: float
    y0: float
    x1: float
    y1: float
    entities: tuple
    handles: tuple[str, ...]

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


def regions(sheet: Sheet) -> list[Region]:
    """Views of the sheet, top to bottom then left to right. Frame, inner border and title block are never views."""
    geo = sheet.geometry
    boxes = [_box(e) for e in geo]
    keep = [i for i, b in enumerate(boxes) if b is not None]
    drop, _, _ = _furniture(geo, boxes, keep)
    live = [i for i in keep if i not in drop]
    live = [i for i in live if i not in _leaders(sheet, geo, live)]
    groups = _merge_inner(sheet, geo, boxes, _clusters(boxes, live))
    found = [_region(sheet, geo, boxes, group) for group in groups]
    return sorted(found, key=lambda r: (-round(r.y1, 1), r.x0))


def title_block(sheet: Sheet) -> Box | None:
    """The title block: a closed rectangle at the frame's lower-right corner, or None when the sheet has none."""
    boxes = [_box(e) for e in sheet.geometry]
    return _furniture(sheet.geometry, boxes, [i for i, b in enumerate(boxes) if b is not None])[2]


def frame(sheet: Sheet) -> Box | None:
    """The sheet frame: the outermost closed rectangle spanning the geometry, or None when there is none."""
    boxes = [_box(e) for e in sheet.geometry]
    return _furniture(sheet.geometry, boxes, [i for i, b in enumerate(boxes) if b is not None])[1]


LEADER_SLACK = 8.0  # mm: a leader ends this close to the text it points at
LEADER_MAX_SEGMENTS = 4
ANNOTATION = ("DIM", "ANNOT", "LEADER", "TEXT", "NOTE")


def _leaders(sheet: Sheet, geo, live: list[int]) -> set[int]:
    """LINE chains from a text's edge to the view are annotation, not outline: a note's leader never sizes a view."""
    if not sheet.texts:
        return set()
    lines = {
        i
        for i in live
        if geo[i].dxftype() == "LINE" and any(w in geo[i].dxf.get("layer", "").upper() for w in ANNOTATION)
    }
    ends = {i: ((geo[i].dxf.start.x, geo[i].dxf.start.y), (geo[i].dxf.end.x, geo[i].dxf.end.y)) for i in lines}
    at_text = {i for i, (a, b) in ends.items() if any(_near_text(a, t) or _near_text(b, t) for t in sheet.texts)}
    dropped: set[int] = set()
    for start in at_text:
        chain = {start}
        frontier = [start]
        while frontier and len(chain) <= LEADER_MAX_SEGMENTS:
            nxt = []
            for i in frontier:
                for j in lines - chain:
                    if any(abs(p[0] - q[0]) <= TOL and abs(p[1] - q[1]) <= TOL for p in ends[i] for q in ends[j]):
                        chain.add(j)
                        nxt.append(j)
            frontier = nxt
        if len(chain) <= LEADER_MAX_SEGMENTS:
            dropped |= chain
    return dropped


def _near_text(p, t, slack: float = LEADER_SLACK) -> bool:
    box = t.box or (t.x, t.y, t.x, t.y)
    return box[0] - slack <= p[0] <= box[2] + slack and box[1] - slack <= p[1] <= box[3] + slack


def _box(e) -> Box | None:
    try:
        b = ezbbox.extents([e])
        if not b.has_data:
            return None
        box = (b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y)
    except Exception:  # hostile or malformed entity: it simply has no box
        return None
    return box if all(math.isfinite(v) for v in box) else None


def _union(boxes: list[Box]) -> Box:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _inside(inner: Box, outer: Box, tol: float = TOL) -> bool:
    return (
        inner[0] >= outer[0] - tol
        and inner[1] >= outer[1] - tol
        and inner[2] <= outer[2] + tol
        and inner[3] <= outer[3] + tol
    )


def _area(b: Box) -> float:
    return (b[2] - b[0]) * (b[3] - b[1])


def _furniture(geo, boxes: list[Box | None], keep: list[int]) -> tuple[set[int], Box | None, Box | None]:
    """Indices of the frame, an inner border, the title block and what it holds; frame box; title block box."""
    rects = _rectangles(geo, boxes, keep)  # (box, entity indices), largest first
    if not rects:
        return set(), None, None
    total = _union([boxes[i] for i in keep])
    frame_box, frame_own = rects[0]
    if frame_box[2] - frame_box[0] < 0.95 * (total[2] - total[0]) or frame_box[3] - frame_box[1] < 0.95 * (
        total[3] - total[1]
    ):
        return set(), None, None  # the largest rectangle does not span the geometry: there is no sheet frame
    rest = [i for i in keep if i not in frame_own]
    if rest and sum(_inside(boxes[i], frame_box) for i in rest) < 0.8 * len(rest):
        return set(), None, None
    drop = set(frame_own)
    title: tuple[Box, set[int]] | None = None
    for box, own in rects[1:]:
        if _area(box) >= 0.8 * _area(frame_box) and _inside(box, frame_box):
            drop |= own  # inner border
        elif _corner(box, frame_box) and _area(box) <= 0.4 * _area(frame_box) and title is None:
            title = (box, own)
    if title:
        drop |= {i for i in rest if _inside(boxes[i], title[0])} | title[1]
    return drop, frame_box, title[0] if title else None


def _corner(box: Box, frame: Box) -> bool:
    return box[2] >= frame[2] - CORNER and box[1] <= frame[1] + CORNER and _inside(box, frame)


def _rectangles(geo, boxes, keep) -> list[tuple[Box, set[int]]]:
    """Axis-aligned closed rectangles, from one polyline or from four lines, largest first."""
    found: list[tuple[Box, set[int]]] = []
    lines = []
    for i in keep:
        e = geo[i]
        kind = e.dxftype()
        if kind in ("LWPOLYLINE", "POLYLINE") and _polyline_rect(e):
            found.append((boxes[i], {i}))
        elif kind == "LINE":
            lines.append(i)
    if len(lines) <= MAX_LINES:
        found += _line_rects(geo, lines)
    return sorted(found, key=lambda r: -_area(r[0]))


def _polyline_rect(e) -> bool:
    try:
        if e.dxftype() == "LWPOLYLINE":
            pts = [(x, y, b) for x, y, b in e.get_points("xyb")]
            closed = e.closed
        else:
            pts = [(p.x, p.y, 0.0) for p in e.points()]
            closed = e.is_closed
    except Exception:
        return False
    if len(pts) >= 5 and pts[0][:2] == pts[-1][:2]:
        pts, closed = pts[:-1], True
    if not closed or len(pts) != 4 or any(p[2] for p in pts):
        return False
    for a, b in zip(pts, pts[1:] + pts[:1], strict=True):
        if abs(a[0] - b[0]) > 0.01 and abs(a[1] - b[1]) > 0.01:
            return False
    return True


def _line_rects(geo, lines: list[int]) -> list[tuple[Box, set[int]]]:
    horizontal: dict[tuple[float, float], list[tuple[float, int]]] = {}
    vertical: dict[tuple[float, float], list[tuple[float, int]]] = {}
    for i in lines:
        s, t = geo[i].dxf.start, geo[i].dxf.end
        if abs(s.y - t.y) <= 0.01 and abs(s.x - t.x) > 0.01:
            horizontal.setdefault((round(min(s.x, t.x), 1), round(max(s.x, t.x), 1)), []).append((round(s.y, 1), i))
        elif abs(s.x - t.x) <= 0.01 and abs(s.y - t.y) > 0.01:
            vertical.setdefault((round(min(s.y, t.y), 1), round(max(s.y, t.y), 1)), []).append((round(s.x, 1), i))
    out = []
    for (x0, x1), hs in horizontal.items():
        for a in hs:
            for b in hs:
                if a[0] < b[0] and (vs := vertical.get((a[0], b[0]))):
                    left = [v for v in vs if v[0] == x0]
                    right = [v for v in vs if v[0] == x1]
                    if left and right:
                        out.append(((x0, a[0], x1, b[0]), {a[1], b[1], left[0][1], right[0][1]}))
    return out


def _clusters(boxes: list[Box | None], live: list[int]) -> list[list[int]]:
    """Groups of entities whose boxes lie within GAP of each other, found by a sweep along x."""
    parent = {i: i for i in live}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    active: list[int] = []
    for i in sorted(live, key=lambda k: boxes[k][0]):
        b = boxes[i]
        active = [j for j in active if boxes[j][2] + GAP >= b[0]]
        for j in active:
            c = boxes[j]
            if c[1] <= b[3] + GAP and b[1] <= c[3] + GAP:
                parent[find(i)] = find(j)
        active.append(i)
    groups: dict[int, list[int]] = {}
    for i in live:
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _merge_inner(sheet: Sheet, geo, boxes, groups: list[list[int]]) -> list[list[int]]:
    """Clusters fully inside another cluster's outline belong to it: an exploded polyline is four lines whose boxes
    no longer span the view, so geometry inside it would otherwise split off as a second "view"."""
    body = [
        _union([boxes[i] for i in group if not _centre_line(sheet, geo[i])] or [boxes[i] for i in group])
        for group in groups
    ]
    merged = list(range(len(groups)))
    for a in range(len(groups)):
        for b in range(len(groups)):
            if a != b and _inside(body[a], body[b], tol=-0.1) and _area(body[b]) > _area(body[a]):
                merged[a] = b
                break
    out: dict[int, list[int]] = {}
    for i, group in enumerate(groups):
        out.setdefault(merged[i], []).extend(group)
    return list(out.values())


def _centre_line(sheet: Sheet, e) -> bool:
    try:
        layer = e.dxf.get("layer", "0")
        name = (e.dxf.get("linetype", "BYLAYER") or "BYLAYER").upper()
        if name == "BYLAYER":
            name = sheet.doc.layers.get(layer).dxf.linetype.upper()
        name = f"{name} {layer.upper()}"  # a centre line on a CENTER layer drawn continuous is still a centre line
    except Exception:
        return False
    return any(word in name for word in CENTRE)


def _region(sheet: Sheet, geo, boxes, group: list[int]) -> Region:
    group = sorted(group)
    body = [boxes[i] for i in group if not _centre_line(sheet, geo[i])] or [boxes[i] for i in group]
    x0, y0, x1, y1 = _union(body)
    return Region(x0, y0, x1, y1, tuple(geo[i] for i in group), tuple(str(geo[i].dxf.get("handle", "")) for i in group))
