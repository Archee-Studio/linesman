"""Shared geometry primitives for the checks: point-to-entity distance and linetype classification.

Distance to an ARC or CIRCLE counts its centre too: a radius dimension's definition point sits at the centre of the
curve it measures, which is part of the geometry even when nothing is drawn there.
"""

import math

from ezdxf import bbox as ezbbox

Point = tuple[float, float]
INF = math.inf


def text_box(e):
    """The rendered extents of a TEXT, MTEXT or ATTRIB; ezdxf overestimates MTEXT height (line capacity), so the
    box is capped at 1.5 line heights per line, anchored at its top."""
    try:
        b = ezbbox.extents([e])
        if not b.has_data or not all(map(math.isfinite, (*b.extmin, *b.extmax))):
            return None
        box = (b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y)
    except Exception:
        return None
    if e.dxftype() == "MTEXT":
        height = e.dxf.get("char_height", 2.5)
        lines = max(1, e.plain_text().count("\\P") + 1)
        cap = 1.5 * height * lines
        if box[3] - box[1] > cap:
            box = (box[0], box[3] - cap, box[2], box[3])
    return box


def _seg(px: float, py: float, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / length2))
    return math.hypot(px - a[0] - t * dx, py - a[1] - t * dy)


def _arc_dist(p: Point, centre: Point, radius: float, a1: float, a2: float, ends: tuple[Point, Point]) -> float:
    """Distance to a circular arc or its centre. `a1`->`a2` is CCW; `ends` are the arc's start and end points."""
    d = math.hypot(p[0] - centre[0], p[1] - centre[1])
    near = min(math.hypot(p[0] - ends[0][0], p[1] - ends[0][1]), math.hypot(p[0] - ends[1][0], p[1] - ends[1][1]))
    if d < 1e-9:
        return 0.0  # the centre counts
    angle = math.degrees(math.atan2(p[1] - centre[1], p[0] - centre[0])) % 360.0
    span = (a2 - a1) % 360.0
    on = (angle - a1) % 360.0 <= span + 1e-7
    return min(abs(d - radius), d) if on else min(near, d)


def _bulge_arc(p: Point, a: Point, b: Point, bulge: float) -> float:
    """Distance to a polyline bulge segment (or its arc centre). `bulge` is tan(angle/4), positive curves left."""
    chord = math.hypot(b[0] - a[0], b[1] - a[1])
    if chord < 1e-9 or abs(bulge) < 1e-9:
        return _seg(p[0], p[1], a, b)
    radius = chord * (1 + bulge * bulge) / (4 * abs(bulge))
    offset = chord * (1 - bulge * bulge) / (4 * bulge)
    ux, uy = (b[0] - a[0]) / chord, (b[1] - a[1]) / chord
    centre = ((a[0] + b[0]) / 2 - uy * offset, (a[1] + b[1]) / 2 + ux * offset)
    a1 = math.degrees(math.atan2(a[1] - centre[1], a[0] - centre[0])) % 360.0
    a2 = math.degrees(math.atan2(b[1] - centre[1], b[0] - centre[0])) % 360.0
    if bulge < 0:
        a1, a2 = a2, a1
    return _arc_dist(p, centre, radius, a1, a2, (a, b))


def _poly_points(e):
    if e.dxftype() == "LWPOLYLINE":
        pts = [(x, y, b) for x, y, b in e.get_points("xyb")]
        return pts, bool(e.closed)
    pts = [(v.dxf.location.x, v.dxf.location.y, v.dxf.get("bulge", 0.0)) for v in e.vertices]
    return pts, bool(e.is_closed)


def point_distance(e, p: Point) -> float:
    """Distance from `p` to the nearest point of the entity (inf when it cannot be measured)."""
    try:
        kind = e.dxftype()
        if kind == "LINE":
            s, t = e.dxf.start, e.dxf.end
            return _seg(p[0], p[1], (s.x, s.y), (t.x, t.y))
        if kind == "CIRCLE":
            c = e.dxf.center
            d = math.hypot(p[0] - c.x, p[1] - c.y)
            return min(abs(d - e.dxf.radius), d)
        if kind == "ARC":
            c, r, a1, a2 = e.dxf.center, e.dxf.radius, e.dxf.start_angle % 360, e.dxf.end_angle % 360
            ends = (
                (c.x + r * math.cos(math.radians(a1)), c.y + r * math.sin(math.radians(a1))),
                (c.x + r * math.cos(math.radians(a2)), c.y + r * math.sin(math.radians(a2))),
            )
            return _arc_dist(p, (c.x, c.y), r, a1, a2, ends)
        if kind in ("LWPOLYLINE", "POLYLINE"):
            pts, closed = _poly_points(e)
            segs = list(zip(pts, pts[1:], strict=False))
            if closed and len(pts) > 2:
                segs.append((pts[-1], pts[0]))
            if not segs:
                return INF
            return min(_bulge_arc(p, a[:2], b[:2], a[2]) if a[2] else _seg(p[0], p[1], a[:2], b[:2]) for a, b in segs)
        if kind in ("SPLINE", "ELLIPSE"):
            approx = e.flattening(0.1) if kind == "SPLINE" else e.flattening(0.01)
            pts = [(v.x, v.y) for v in approx]
            return min((_seg(p[0], p[1], a, b) for a, b in zip(pts, pts[1:], strict=False)), default=INF)
    except Exception:
        return INF
    return INF


_CENTRE_NAMES = ("CENTER", "CENTRE", "DASHDOT", "PHANTOM", "AXIS", "ISO04", "ISO10")
_DASHED_NAMES = ("HIDDEN", "DASHED", "ISO02", "ISO05", "ISO08")


def linetype_name(doc, e) -> str:
    """The entity's effective linetype name: BYLAYER resolved through its layer (BYBLOCK left unresolved)."""
    name = (e.dxf.get("linetype", "BYLAYER") or "BYLAYER").upper()
    if name == "BYLAYER":
        try:
            name = (doc.layers.get(e.dxf.get("layer", "0")).dxf.linetype or "CONTINUOUS").upper()
        except Exception:
            return "CONTINUOUS"
    return name


def linetype_class(doc, e) -> str:
    """`center` (dash-dot), `dashed` or `solid`. Known linetype names win: the pattern is consulted only for an
    unknown name, since real files carry malformed patterns under good names (a `CENTER` with tags -2,2,-2)."""
    name = linetype_name(doc, e)
    if any(word in name for word in _CENTRE_NAMES):
        return "center"
    if any(word in name for word in _DASHED_NAMES):
        return "dashed"
    try:
        tags = [t.value for t in doc.linetypes.get(name).pattern_tags.tags if t.code == 49]
        dashes = [v for v in tags if v > 0.01]
        if len(tags) >= 3 and dashes and min(dashes) <= 0.4 * max(dashes):
            return "center"  # a long dash alternating with a much shorter one is dash-dot
        if len(tags) >= 2:
            return "dashed"
    except Exception:
        pass
    return "solid"


def _clip_hits_box(a: Point, b: Point, box) -> bool:
    """Liang-Barsky clip: does segment a-b cross or touch the closed box (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p_, q_ in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if abs(p_) < 1e-12:
            if q_ < 0:
                return False
        else:
            t = q_ / p_
            if p_ < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def _sample(e):
    """The entity's path as a polyline of (x, y) points; curves are sampled. Empty when not measurable."""
    kind = e.dxftype()
    if kind == "LINE":
        s, t = e.dxf.start, e.dxf.end
        return [(s.x, s.y), (t.x, t.y)]
    if kind in ("ARC", "CIRCLE"):
        c, r = e.dxf.center, e.dxf.radius
        a1 = e.dxf.start_angle if kind == "ARC" else 0.0
        a2 = e.dxf.end_angle if kind == "ARC" else 360.0
        span = (a2 - a1) % 360.0 or 360.0
        n = max(8, int(span / 10) + 1)
        return [
            (c.x + r * math.cos(math.radians(a1 + span * i / n)), c.y + r * math.sin(math.radians(a1 + span * i / n)))
            for i in range(n + 1)
        ]
    if kind in ("LWPOLYLINE", "POLYLINE"):
        pts, closed = _poly_points(e)
        out = []
        segs = list(zip(pts, pts[1:], strict=False)) + ([(pts[-1], pts[0])] if closed and len(pts) > 2 else [])
        for a, b in segs:
            out.append(a[:2])
            if a[2]:  # bulge: sample the arc
                chord = math.hypot(b[0] - a[0], b[1] - a[1])
                if chord > 1e-9:
                    radius = chord * (1 + a[2] ** 2) / (4 * abs(a[2]))
                    offset = chord * (1 - a[2] ** 2) / (4 * a[2])
                    ux, uy = (b[0] - a[0]) / chord, (b[1] - a[1]) / chord
                    cc = ((a[0] + b[0]) / 2 - uy * offset, (a[1] + b[1]) / 2 + ux * offset)
                    aa = math.degrees(math.atan2(a[1] - cc[1], a[0] - cc[0]))
                    sweep = 4 * math.degrees(math.atan(abs(a[2])))
                    n = max(2, int(sweep / 10) + 1)
                    sign = 1 if a[2] > 0 else -1
                    out += [
                        (
                            cc[0] + radius * math.cos(math.radians(aa + sign * sweep * i / n)),
                            cc[1] + radius * math.sin(math.radians(aa + sign * sweep * i / n)),
                        )
                        for i in range(1, n)
                    ]
            out.append(b[:2])
        return out
    if kind in ("SPLINE", "ELLIPSE"):
        return [(v.x, v.y) for v in e.flattening(0.1 if kind == "SPLINE" else 0.01)]
    return []


def entity_hits_box(e, box) -> bool:
    """True when the entity's path passes through or inside the closed box."""
    try:
        pts = _sample(e)
    except Exception:
        return False
    return any(x0 <= x <= x1 and y0 <= y <= y1 for (x, y) in pts for x0, y0, x1, y1 in [box]) or any(
        _clip_hits_box(a, b, box) for a, b in zip(pts, pts[1:], strict=False)
    )
