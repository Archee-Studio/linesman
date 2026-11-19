"""A rectangular plate with a fitted bore and a hole pattern: the reference family the others follow."""

import random

from ezdxf.document import Drawing

from ..schema import Dim, Truth, View
from .drafting import DIMSTYLE, Box, drawing_area, frame, new_sheet

NAME = "plate"
HEADROOM = 155  # mm: drawing-area top 277, less the front view base (105 + thickness) and one dimension tier (17)


def sample(seed: int) -> dict:
    rng = random.Random(seed)
    width = rng.choice(range(80, 201, 10))
    thickness = rng.choice([6, 8, 10, 12, 15])
    height = rng.choice(range(60, min(int(width * 0.8), HEADROOM - thickness) + 1, 10))
    return {
        "part": "Mounting plate",
        "material": rng.choice(["S235", "C45", "AlMg3"]),
        "width": float(width),
        "height": float(height),
        "thickness": float(thickness),
        "bore": float(rng.choice([20, 25, 30, 35, 40])),
        "bore_fit": "H7",
        "hole": float(rng.choice([6.6, 9.0, 11.0])),
        "inset": 10.0,
    }


def request(inputs: dict) -> str:
    i = inputs
    return (
        f"Draw an A3 detail sheet of the {i['part'].lower()} at 1:1 in first-angle projection with a front and a "
        f"top view. Plate {i['width']:g} x {i['height']:g} mm, {i['thickness']:g} mm thick, {i['material']}. "
        f"Central bore {i['bore']:g} {i['bore_fit']}. Four through holes {i['hole']:g} mm, centres "
        f"{i['inset']:g} mm in from each edge. Dimension every feature; show the fit on the bore; fill the "
        "title block with part, material and scale."
    )


def truth(inputs: dict) -> Truth:
    i = inputs
    pitch_x, pitch_y = i["width"] - 2 * i["inset"], i["height"] - 2 * i["inset"]
    return Truth(
        views=(
            View(name="front", width=i["width"], height=i["height"]),
            View(name="top", width=i["width"], height=i["thickness"]),
        ),
        dims=(
            Dim(id="width", kind="linear", value=i["width"], view="front"),
            Dim(id="height", kind="linear", value=i["height"], view="front"),
            Dim(id="thickness", kind="linear", value=i["thickness"], view="top"),
            Dim(id="bore", kind="diameter", value=i["bore"], view="front", fit=i["bore_fit"]),
            Dim(id="hole", kind="diameter", value=i["hole"], view="front"),
            Dim(id="pitch_x", kind="linear", value=pitch_x, view="front", alt=(i["inset"],)),
            Dim(id="pitch_y", kind="linear", value=pitch_y, view="front", alt=(i["inset"],)),
        ),
        title={"part": i["part"], "material": i["material"], "scale": "1:1"},
    )


def views(inputs: dict, layout: int = 0) -> dict[str, Box]:
    """Where each view's outline sits on the sheet: x, y of the lower-left corner, width, height."""
    i = inputs
    x0, y0, _, _ = drawing_area()
    t = i["thickness"]
    fx, fy = x0 + 30 + 15.0 * (layout % 3), y0 + 20 + t + 25
    return {"front": (fx, fy, i["width"], i["height"]), "top": (fx, fy - 25 - t, i["width"], t)}


def draw(inputs: dict, layout: int = 0) -> Drawing:
    """layout 0 is the reference; other layouts move the views and the dimension sides but keep every feature."""
    i = inputs
    doc = new_sheet()
    msp = doc.modelspace()
    frame(doc, {"part": i["part"], "material": i["material"], "scale": "1:1"})
    w, h, t = i["width"], i["height"], i["thickness"]
    box = views(i, layout)
    fx, fy = box["front"][:2]  # front view lower-left corner
    ty = box["top"][1]  # first-angle projection puts the view from above below the front view
    msp.add_lwpolyline(
        [(fx, fy), (fx + w, fy), (fx + w, fy + h), (fx, fy + h)], close=True, dxfattribs={"layer": "outline"}
    )
    cx, cy = fx + w / 2, fy + h / 2
    msp.add_circle((cx, cy), i["bore"] / 2, dxfattribs={"layer": "outline"})
    holes = [
        (fx + i["inset"], fy + i["inset"]),
        (fx + w - i["inset"], fy + i["inset"]),
        (fx + w - i["inset"], fy + h - i["inset"]),
        (fx + i["inset"], fy + h - i["inset"]),
    ]
    for p in holes:
        msp.add_circle(p, i["hole"] / 2, dxfattribs={"layer": "outline"})
    msp.add_lwpolyline(
        [(fx, ty), (fx + w, ty), (fx + w, ty + t), (fx, ty + t)], close=True, dxfattribs={"layer": "outline"}
    )
    for x in (cx - i["bore"] / 2, cx + i["bore"] / 2):
        msp.add_line((x, ty), (x, ty + t), dxfattribs={"layer": "hidden"})

    side = 1 if layout % 2 == 0 else -1
    d = {"layer": "dims"}
    ds = {"dimstyle": DIMSTYLE}
    above = fy + h + 12 if side > 0 else fy - 12
    msp.add_linear_dim(base=(fx, above), p1=(fx, fy + h), p2=(fx + w, fy + h), dxfattribs=d, **ds).render()
    left = fx - 12 if side > 0 else fx + w + 12
    msp.add_linear_dim(base=(left, fy), p1=(fx, fy), p2=(fx, fy + h), angle=90, dxfattribs=d, **ds).render()
    msp.add_linear_dim(
        base=(fx + w + 12, ty), p1=(fx + w, ty), p2=(fx + w, ty + t), angle=90, dxfattribs=d, **ds
    ).render()
    msp.add_diameter_dim(
        center=(cx, cy),
        radius=i["bore"] / 2,
        angle=45.0 + 90 * layout,
        text=f"<>{i['bore_fit']}",
        dxfattribs=d,
        **ds,
    ).render()
    msp.add_diameter_dim(center=holes[2], radius=i["hole"] / 2, angle=45.0, text="4x <>", dxfattribs=d, **ds).render()
    msp.add_linear_dim(base=(fx, fy + i["inset"] - 6), p1=holes[0], p2=holes[1], dxfattribs=d, **ds).render()
    msp.add_linear_dim(base=(fx + i["inset"] - 6, fy), p1=holes[1], p2=holes[2], angle=90, dxfattribs=d, **ds).render()
    return doc
