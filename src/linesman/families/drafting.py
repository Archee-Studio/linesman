"""Sheet furniture every family draws the same way: an A3 frame, a title block and dimension styles."""

import math

import ezdxf
from ezdxf.document import Drawing

from ..sheet import MM

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


def place(sizes: dict[str, tuple[float, float]], layout: int) -> dict[str, Box]:
    """First-angle arrangement: `top` below `front`, `left` right of `front`, centred on the front view.

    Layout 0 centres the arrangement in the drawing area; 1 pushes it to the lower left, 2 to the upper right.
    """
    gap = GAPS[layout % 3]
    fw, fh = sizes["front"]
    rel: dict[str, Box] = {"front": (0.0, 0.0, fw, fh)}
    if "top" in sizes:
        w, h = sizes["top"]
        rel["top"] = ((fw - w) / 2, -gap - h, w, h)
    if "left" in sizes:
        w, h = sizes["left"]
        rel["left"] = (fw + gap, (fh - h) / 2, w, h)
    xs0, ys0 = min(b[0] for b in rel.values()), min(b[1] for b in rel.values())
    xs1, ys1 = max(b[0] + b[2] for b in rel.values()), max(b[1] + b[3] for b in rel.values())
    ax0, ay0, ax1, ay1 = drawing_area()
    spare_x, spare_y = (ax1 - ax0 - 2 * PAD) - (xs1 - xs0), (ay1 - ay0 - 2 * PAD) - (ys1 - ys0)
    if spare_x < 0 or spare_y < 0:
        raise ValueError(f"views {sizes} do not fit the drawing area")
    kx, ky = ((0.5, 0.5), (0.0, 0.0), (1.0, 1.0))[layout % 3]
    ox, oy = ax0 + PAD + spare_x * kx - xs0, ay0 + PAD + spare_y * ky - ys0
    return {n: (b[0] + ox, b[1] + oy, b[2], b[3]) for n, b in rel.items()}


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


def hdim(msp, p1, p2, base_y: float, text: str = "<>") -> None:
    _dim(msp, "add_linear_dim", base=(p1[0], base_y), p1=p1, p2=p2, text=text)


def vdim(msp, p1, p2, base_x: float, text: str = "<>") -> None:
    _dim(msp, "add_linear_dim", base=(base_x, p1[1]), p1=p1, p2=p2, angle=90, text=text)


def ddim(msp, c, d: float, angle: float, text: str = "<>", location=None) -> None:
    """A diameter dimension. Its measurement text already carries the diameter sign, so `text` never adds one."""
    _dim(msp, "add_diameter_dim", center=c, radius=d / 2, angle=angle, text=text, location=location)


def rdim(msp, c, r: float, angle: float, text: str = "<>") -> None:
    _dim(msp, "add_radius_dim", center=c, radius=r, angle=angle, text=text)


def polar(c, r: float, angle: float) -> tuple[float, float]:
    return c[0] + r * math.cos(math.radians(angle)), c[1] + r * math.sin(math.radians(angle))
