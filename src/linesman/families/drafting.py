"""Sheet furniture every family draws the same way: an A3 frame, a title block and dimension styles."""

import math
from contextlib import suppress

import ezdxf
from ezdxf import bbox as ezbbox
from ezdxf.document import Drawing
from ezdxf.math import Matrix44, Vec3

from ..sheet import _POINTS, MM

A3 = (420.0, 297.0)
TITLE_W, TITLE_H = 180.0, 40.0


def new_sheet() -> Drawing:
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = MM
    doc.header["$MEASUREMENT"] = 1
    for name, linetype, color in (
        ("outline", "CONTINUOUS", 7),
        ("hidden", "DASHED", 3),
        ("center", "CENTER", 1),
        ("dims", "CONTINUOUS", 4),
        ("hatch", "CONTINUOUS", 8),
        ("frame", "CONTINUOUS", 7),
    ):
        doc.layers.add(name, color=color, linetype=linetype)
    style = doc.dimstyles.new(DIMSTYLE)
    for key, value in {
        "dimlfac": 1.0,
        "dimtxt": 3.5,
        "dimasz": 3.0,
        "dimexe": 2.0,
        "dimexo": 1.0,
        "dimgap": 1.0,
        "dimdec": 2,
        "dimzin": 8,
        "dimtad": 1,
        "dimtih": 0,
        "dimtoh": 0,
        "dimblk": "",
    }.items():
        style.dxf.set(key, value)
    return doc


DIMSTYLE = "ISO-35"  # ISO 129 style: 3.5 mm text above the line, closed filled arrows, millimetres


def frame(doc: Drawing, title: dict[str, str]) -> None:
    """A3 landscape border with a 10 mm margin (20 mm binding edge) and the title block bottom right."""
    msp = doc.modelspace()
    w, h = A3
    msp.add_lwpolyline(
        [(20, 10), (w - 10, 10), (w - 10, h - 10), (20, h - 10)], close=True, dxfattribs={"layer": "frame"}
    )
    x0, y0 = w - 10 - TITLE_W, 10.0
    msp.add_lwpolyline(
        [(x0, y0), (x0 + TITLE_W, y0), (x0 + TITLE_W, y0 + TITLE_H), (x0, y0 + TITLE_H)],
        close=True,
        dxfattribs={"layer": "frame"},
    )
    row = TITLE_H / max(len(title), 1)
    for i, (label, value) in enumerate(title.items()):
        y = y0 + TITLE_H - (i + 1) * row
        msp.add_line((x0, y), (x0 + TITLE_W, y), dxfattribs={"layer": "frame"})
        msp.add_text(label.upper(), height=2.5, dxfattribs={"layer": "frame"}).set_placement((x0 + 3, y + 2))
        msp.add_text(value, height=3.5, dxfattribs={"layer": "frame"}).set_placement((x0 + 60, y + 2))


def drawing_area() -> tuple[float, float, float, float]:
    """The free area left of and above the title block: x0, y0, x1, y1."""
    w, h = A3
    return 30.0, 10.0 + TITLE_H + 10.0, w - 20.0, h - 20.0


Box = tuple[float, float, float, float]  # x, y, width, height of a view outline; x, y is the lower-left corner
GAPS = (40.0, 45.0, 50.0)  # between views, per layout; room for one tier of dimensions
PAD = 30.0  # kept free around the arrangement for outer dimension tiers


def place(sizes: dict[str, tuple[float, float]], layout: int, area: tuple | None = None) -> dict[str, Box]:
    """First-angle arrangement: `top` below the front (or section) view, `left` right of it, centred on it.

    Layout 0 centres the arrangement in `area` (the drawing area by default); 1 pushes it to the lower left,
    2 to the upper right.
    """
    gap = GAPS[layout % 3]
    anchor = "front" if "front" in sizes else "section"
    fw, fh = sizes[anchor]
    rel: dict[str, Box] = {anchor: (0.0, 0.0, fw, fh)}
    if "top" in sizes:
        w, h = sizes["top"]
        rel["top"] = ((fw - w) / 2, -gap - h, w, h)
    if "left" in sizes:
        w, h = sizes["left"]
        rel["left"] = (fw + gap, (fh - h) / 2, w, h)
    xs0, ys0 = min(b[0] for b in rel.values()), min(b[1] for b in rel.values())
    xs1, ys1 = max(b[0] + b[2] for b in rel.values()), max(b[1] + b[3] for b in rel.values())
    ax0, ay0, ax1, ay1 = area or drawing_area()
    spare_x, spare_y = (ax1 - ax0 - 2 * PAD) - (xs1 - xs0), (ay1 - ay0 - 2 * PAD) - (ys1 - ys0)
    if spare_x < 0 or spare_y < 0:
        raise ValueError(f"views {sizes} do not fit the drawing area")
    kx, ky = ((0.5, 0.5), (0.0, 0.0), (1.0, 1.0))[layout % 3]
    ox, oy = ax0 + PAD + spare_x * kx - xs0, ay0 + PAD + spare_y * ky - ys0
    return {n: (b[0] + ox, b[1] + oy, b[2], b[3]) for n, b in rel.items()}


def deviations(fit: str, nominal: float) -> str:
    """A fitted dimension's limit deviations text, `+0.021/0` style (ISO 286 values via iso286)."""
    from .. import iso286

    upper, lower = iso286.limits(fit, nominal)
    return f"+{upper:g}/{lower:+g}" if lower else f"+{upper:g}/0"


def mirror(angle: float, layout: int) -> float:
    """A dimension angle for a layout: as is, flipped top to bottom, or flipped left to right."""
    return (angle, -angle, 180.0 - angle)[layout % 3]


def line(msp, a, b, layer: str = "outline") -> None:
    msp.add_line(a, b, dxfattribs={"layer": layer})


def rect(msp, x: float, y: float, w: float, h: float, layer: str = "outline") -> None:
    msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True, dxfattribs={"layer": layer})


def circle(msp, c, d: float, layer: str = "outline") -> None:
    msp.add_circle(c, d / 2, dxfattribs={"layer": layer})


def cross(msp, c, half_w: float, half_h: float) -> None:
    """Centre lines through c, kept inside the view outline."""
    line(msp, (c[0] - half_w, c[1]), (c[0] + half_w, c[1]), "center")
    line(msp, (c[0], c[1] - half_h), (c[0], c[1] + half_h), "center")


def notched_circle(msp, c, d: float, width: float, y_notch: float, layer: str = "outline") -> None:
    """A circle of diameter d with a keyway notch of `width` at the top, cut to height `y_notch` above the centre."""
    r, half = d / 2, width / 2
    theta = math.degrees(math.asin(half / r))
    y_c = math.sqrt(r * r - half * half)
    msp.add_arc(c, r, 90 + theta, 90 - theta + 360, dxfattribs={"layer": layer})
    left, right = (c[0] - half, c[1] + y_c), (c[0] + half, c[1] + y_c)
    pts = [left, (c[0] - half, c[1] + y_notch), (c[0] + half, c[1] + y_notch), right]
    msp.add_lwpolyline(pts, dxfattribs={"layer": layer})


def _dim(msp, kind: str, **kw):
    getattr(msp, kind)(dimstyle=DIMSTYLE, dxfattribs={"layer": "dims"}, **kw).render()


def hdim(msp, p1, p2, base_y: float, text: str = "<>", location=None) -> None:
    _dim(msp, "add_linear_dim", base=(p1[0], base_y), p1=p1, p2=p2, text=text, location=location)


def vdim(msp, p1, p2, base_x: float, text: str = "<>") -> None:
    _dim(msp, "add_linear_dim", base=(base_x, p1[1]), p1=p1, p2=p2, angle=90, text=text)


def ddim(msp, c, d: float, angle: float, text: str = "<>", location=None) -> None:
    """A diameter dimension. Its measurement text already carries the diameter sign, so `text` never adds one."""
    _dim(msp, "add_diameter_dim", center=c, radius=d / 2, angle=angle, text=text, location=location)


def rdim(msp, c, r: float, angle: float, text: str = "<>", location=None) -> None:
    _dim(msp, "add_radius_dim", center=c, radius=r, angle=angle, text=text, location=location)


def polar(c, r: float, angle: float) -> tuple[float, float]:
    return c[0] + r * math.cos(math.radians(angle)), c[1] + r * math.sin(math.radians(angle))


def hatch(msp, *paths: list[tuple[float, float]]) -> None:
    """ANSI31 hatching inside `paths`, each a closed polyline; extra paths are islands (even-odd)."""
    h = msp.add_hatch(color=8, dxfattribs={"layer": "hatch"})
    for pts in paths:
        h.paths.add_polyline_path(pts, is_closed=True)


def section_label(msp, box: Box) -> None:
    """The `A-A` tag of a sectioned view, centred under its outline; drops a tier when the band is occupied."""
    x, y, w, _ = box
    others = []
    for e in msp:
        if e.dxftype() in {"TEXT", "MTEXT", "INSERT", "DIMENSION"}:
            try:
                b = ezbbox.extents([e])
            except Exception:
                continue
            if b.has_data:
                others.append((b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y))
    for dy in range(-7, -70, -7):
        cand = (x + w / 2 - 4.5, y + dy - 5.0, x + w / 2 + 4.5, y + dy)
        if not any(cand[0] < o[2] and o[0] < cand[2] and cand[1] < o[3] and o[1] < cand[3] for o in others):
            break
    msp.add_text("A-A", height=5.0, dxfattribs={"layer": "dims"}).set_placement((x + w / 2 - 4.5, y + dy - 5.0))


STAGE = (1000.0, 1000.0, 3000.0, 3000.0)  # scratch area far off the sheet: drafted at true size, then moved


def scale_of(sizes: dict[str, tuple[float, float]]) -> float:
    """The drawing scale factor: 2 when the largest view is under 40 mm, 0.5 when the 1:1 arrangement does not
    fit the drawing area, else 1."""
    if max(max(w, h) for w, h in sizes.values()) < 40.0:
        return 2.0
    try:
        place(sizes, 0)
    except ValueError:
        return 0.5
    return 1.0


def scale_name(factor: float) -> str:
    return {2.0: "2:1", 0.5: "1:2"}.get(factor, "1:1")


def placed(sizes: dict[str, tuple[float, float]], layout: int) -> tuple[dict[str, Box], float]:
    """The view boxes on the sheet and the scale factor chosen for them (true sizes in, sheet sizes out)."""
    factor = scale_of(sizes)
    return place({n: (w * factor, h * factor) for n, (w, h) in sizes.items()}, layout), factor


def draft_boxes(sizes: dict[str, tuple[float, float]], layout: int) -> tuple[dict[str, Box], dict[str, Box], float]:
    """(stage, final, factor): draw into `stage` boxes, then `rescale` moves everything to `final`."""
    final, factor = placed(sizes, layout)
    if factor == 1.0:
        return final, final, factor
    return place(sizes, layout, area=STAGE), final, factor


def area(points: list[tuple[float, float]]) -> float:
    """Signed shoelace area of a polygon in mm2; clockwise polygons return negative values."""
    pairs = zip(points, [*points[1:], points[0]], strict=False)
    return sum(ax * by - bx * ay for (ax, ay), (bx, by) in pairs) / 2


def _transform(x0: float, y0: float, x1: float, y1: float, factor: float) -> Matrix44:
    # ezdxf composes A @ B as "A applied first": scale, then translate to the placed corner
    return Matrix44.scale(factor, factor, 1.0) @ Matrix44.translate(x1 - x0 * factor, y1 - y0 * factor, 0.0)


def rescale(doc: Drawing, stage: dict[str, Box], final: dict[str, Box]) -> None:
    """Move each staged view's entities into its placed box: geometry and text are scaled, dimension definition
    points and text position move with the view but the text stays its drafted size (DIMLFAC = 1/factor)."""
    msp = doc.modelspace()
    anchor = "front" if "front" in stage else "section"
    factor = final[anchor][2] / stage[anchor][2]
    doc.dimstyles.get(DIMSTYLE).dxf.dimlfac = 1.0 / factor
    boxes = {n: (b[0] - 1, b[1] - 1, b[0] + b[2] + 1, b[1] + b[3] + 1) for n, b in stage.items()}
    transforms = {n: _transform(*stage[n][:2], *final[n][:2], factor) for n in stage}
    _POINT_ATTRS = ("defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5", "text_midpoint")

    def owner(p) -> str | None:
        return next((n for n, (x0, y0, x1, y1) in boxes.items() if x0 <= p[0] <= x1 and y0 <= p[1] <= y1), None)

    for e in msp:
        kind = e.dxftype()
        if kind == "DIMENSION":
            feature = _POINTS.get(e.dimtype & 0x0F, ("defpoint2", "defpoint3"))
            points = [e.dxf.get(n) for n in feature if e.dxf.get(n) is not None]
            owners = {owner(p) for p in points} - {None}
            if len(owners) != 1:  # floating dims and dims spanning views are not moved
                continue
            which = next(iter(owners))
            move = transforms[which]
            final_box = final[which]
            for n in _POINT_ATTRS:
                q = e.dxf.get(n)
                if q is None:
                    continue
                moved = move.transform(q)
                if n not in feature:
                    moved = Vec3(*annotation_point(final_box, moved))
                e.dxf.set(n, moved)
            blk = e.get_geometry_block()  # transform the rendered block: texts keep their size and placement
            if blk is not None:
                for be in blk:
                    keep = {
                        a: be.dxf.get(a) for a in ("height", "char_height", "xscale", "yscale") if be.dxf.hasattr(a)
                    }
                    with suppress(Exception):
                        be.transform(move)
                    for a, v in keep.items():
                        if v is not None:
                            be.dxf.set(a, v)
        elif kind in ("TEXT", "MTEXT", "ATTRIB"):
            n = owner(e.dxf.insert)
            if n is None:
                continue
            attr = "char_height" if kind == "MTEXT" else "height"
            height = e.dxf.get(attr, None)
            e.dxf.insert = transforms[n].transform(e.dxf.insert)
            if height is not None:
                e.dxf.set(attr, height)
        elif kind == "HATCH":
            b = ezbbox.extents([e])
            n = owner(((b.extmin.x + b.extmax.x) / 2, (b.extmin.y + b.extmax.y) / 2)) if b.has_data else None
            if n is not None:
                e.transform(transforms[n])
        elif e.is_virtual or kind == "INSERT":
            continue
        else:
            try:
                b = ezbbox.extents([e])
            except Exception:
                continue
            if not b.has_data:
                continue
            n = owner(((b.extmin.x + b.extmax.x) / 2, (b.extmin.y + b.extmax.y) / 2))
            if n is not None:
                e.transform(transforms[n])


def map_point(before: Box, after: Box, p) -> tuple[float, float]:
    """Where a point inside (or relative to) the `before` view box lands in `after`."""
    factor = after[2] / before[2]
    return (after[0] + (p[0] - before[0]) * factor, after[1] + (p[1] - before[1]) * factor)


ANNOTATION_GAP = 7.0  # mm: scaled dim lines and texts never sit closer than this to their view


def annotation_point(after: Box, p, margin: float = ANNOTATION_GAP) -> tuple[float, float]:
    """A dimension's line or text point after scaling: kept as transformed, unless it lands in the `margin`
    band along the view's edge — then it is moved to the nearest grown side so the annotation never ends up
    tangled in the outline. Interior dimension lines stay interior."""
    x0, y0, w, h = after
    x, y = p.x, p.y
    if x0 <= x <= x0 + w and y0 <= y <= y0 + h:
        sides = [(x - x0, "l"), (x0 + w - x, "r"), (y - y0, "b"), (y0 + h - y, "t")]
        depth, side = min(sides)
        if depth >= margin:
            return x, y
        return {"l": (x0 - margin, y), "r": (x0 + w + margin, y), "b": (x, y0 - margin), "t": (x, y0 + h + margin)}[
            side
        ]
    grown = x0 - margin <= x <= x0 + w + margin and y0 - margin <= y <= y0 + h + margin
    if not grown:
        return x, y
    if x < x0:
        return x0 - margin, y
    if x > x0 + w:
        return x0 + w + margin, y
    if y < y0:
        return x, y0 - margin
    return x, y0 + h + margin


def push_outside(box: Box, p, margin: float = ANNOTATION_GAP) -> tuple[float, float]:
    """`p` pushed out of `box` grown by `margin`, along the ray from the box centre (no move when already out)."""
    x0, y0, w, h = box
    cx, cy = x0 + w / 2, y0 + h / 2
    x, y = p.x, p.y
    if not (x0 - margin <= x <= x0 + w + margin and y0 - margin <= y <= y0 + h + margin):
        return x, y
    dx, dy = x - cx, y - cy
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        dx = 1.0
    tx = max((x0 - margin - cx) / dx, (x0 + w + margin - cx) / dx) if abs(dx) > 1e-9 else math.inf
    ty = max((y0 - margin - cy) / dy, (y0 + h + margin - cy) / dy) if abs(dy) > 1e-9 else math.inf
    t = max(1.0, min(tx, ty))  # the nearer boundary along the ray is the exit side
    return cx + dx * t, cy + dy * t


def roughness_marks(doc: Drawing, truth) -> None:
    """ISO 1302 style `Ra <v>` texts beside the sheet dimensions `truth.finish` names. Called after any rescale
    so the mark lands next to the dimension's final text position."""
    from ..checks.dims import match
    from ..checks.drafting import _dim_text_boxes
    from ..sheet import parse

    if not truth.finish:
        return
    sheet = parse(doc)
    matched = match(sheet, truth)
    msp = doc.modelspace()
    taken = [b for t in sheet.texts if t.box for b in (t.box,)]
    taken += [b for d in sheet.dims for b in _dim_text_boxes(sheet, d.handle)]
    for dim_id, ra in truth.finish.items():
        found = matched.get(dim_id)
        if found is None:
            continue
        label = f"Ra {ra:g}"
        wide = 3.5 * len(label)  # the pinned measurement font's width at 3.5 mm height
        spots = [
            (dx, dy)
            for dy in (-9.0, -14.0, -19.0, -24.0, -29.0, 8.0, 12.0, 16.0, 21.0, 25.0, 29.0)
            for dx in (5.0, -wide - 6.0, wide + 6.0, -wide - 15.0, wide + 15.0, -wide - 24.0, wide + 24.0, -29.0, 20.0)
        ]
        for dx, dy in spots:
            box = (found.x + dx - 1.5, found.y + dy - 6.0, found.x + dx + wide + 1.5, found.y + dy + 5.0)
            inside = box[0] > 10.0 and box[2] < 410.0 and box[1] > 10.0 and box[3] < 287.0
            near = abs(dx) <= 29.0 and abs(dy) <= 29.0  # the check measures each axis within 30 mm
            if (
                inside
                and near
                and not any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1] for b in taken)
            ):
                break
        taken.append(box)
        msp.add_text(label, height=3.5, dxfattribs={"layer": "dims"}).set_placement((found.x + dx, found.y + dy))
