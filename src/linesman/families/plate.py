"""A rectangular plate with a fitted bore and a hole pattern: the reference family the others follow."""

import random

from ezdxf.document import Drawing

from .. import iso273
from ..schema import Dim, Truth, View
from .drafting import (
    DIMSTYLE,
    Box,
    cross,
    deviations,
    drawing_area,
    frame,
    new_sheet,
    rescale,
    roughness_marks,
    scale_name,
    scale_of,
)

NAME = "plate"
HEADROOM = 155  # mm: drawing-area top 277, less the front view base (105 + thickness) and one dimension tier (17)


def sample(seed: int) -> dict:
    rng = random.Random(seed)
    width = rng.choice(list(range(80, 201, 10)) + [300, 320, 340, 360])  # 300+ forces a 1:2 sheet
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
        "roughness": {"bore": 1.6},
    }


def calc(seed: int) -> dict:
    """Calc-level inputs: the bore stays fitted, the holes are given as a bolt size (ISO 273 medium)."""
    i = sample(seed)
    bolt = {6.6: "M6", 9.0: "M8", 11.0: "M10"}[i["hole"]]
    i = {**i, "bolt": bolt, "calc": True}
    i.pop("hole")
    return i


def resolve(inputs: dict) -> dict:
    """Requirement inputs (calc) expanded to the full given values."""
    if not inputs.get("calc"):
        return inputs
    return {**inputs, "hole": iso273.medium(inputs["bolt"])}


def _sizes(i: dict) -> dict[str, tuple[float, float]]:
    return {"front": (i["width"], i["height"]), "top": (i["width"], i["thickness"])}


def _scale(inputs: dict) -> tuple[float, str]:
    f = scale_of(_sizes(resolve(inputs)))
    return f, scale_name(f)


def request(inputs: dict) -> str:
    i, scale = inputs, _scale(inputs)[1]
    holes = (
        f"four through holes for {i['bolt']} bolts, medium clearance per ISO 273"
        if i.get("calc")
        else f"four through holes {i['hole']:g} mm"
    )
    fit = "as limit deviations" if i.get("calc") else i["bore_fit"]
    return (
        f"Draw an A3 detail sheet of the {i['part'].lower()} at {scale} in first-angle projection with a front and a "
        f"top view. Plate {i['width']:g} x {i['height']:g} mm, {i['thickness']:g} mm thick, {i['material']}. "
        f"Central bore {i['bore']:g} {fit}. {holes.capitalize()}, centres "
        f"{i['inset']:g} mm in from each edge. Dimension every feature; show the fit on the bore "
        f"{'with its limit deviations' if i.get('calc') else 'designation'}; mark the bore surface Ra 1.6; fill "
        "the title block with part, material and scale."
    )


def views(inputs: dict, layout: int = 0) -> dict[str, Box]:
    """Where each view's outline sits on the sheet: x, y of the lower-left corner, width, height."""
    i = resolve(inputs)
    f = _scale(i)[0]
    x0, y0, _, _ = drawing_area()
    t = i["thickness"]
    fx, fy = x0 + 30 + 15.0 * (layout % 3), y0 + 20 + t * f + 25
    return {"front": (fx, fy, i["width"] * f, i["height"] * f), "top": (fx, fy - 25 - t * f, i["width"] * f, t * f)}


def truth(inputs: dict) -> Truth:
    i, scale = resolve(inputs), _scale(inputs)[1]
    pitch_x, pitch_y = i["width"] - 2 * i["inset"], i["height"] - 2 * i["inset"]
    fit_form = "deviations" if inputs.get("calc") else "any"
    return Truth(
        views=(
            View(name="front", width=i["width"], height=i["height"]),
            View(name="top", width=i["width"], height=i["thickness"], hidden=True),
        ),
        dims=(
            Dim(id="width", kind="linear", value=i["width"], view="front"),
            Dim(id="height", kind="linear", value=i["height"], view="front"),
            Dim(id="thickness", kind="linear", value=i["thickness"], view="top"),
            Dim(id="bore", kind="diameter", value=i["bore"], view="front", fit=i["bore_fit"], fit_form=fit_form),
            Dim(id="hole", kind="diameter", value=i["hole"], view="front"),
            Dim(id="pitch_x", kind="linear", value=pitch_x, view="front", alt=(i["inset"],)),
            Dim(id="pitch_y", kind="linear", value=pitch_y, view="front", alt=(i["inset"],)),
        ),
        title={"part": i["part"], "material": i["material"], "scale": scale},
        scale=scale,
        finish=i["roughness"],
    )


def draw(inputs: dict, layout: int = 0) -> Drawing:
    """layout 0 is the reference; other layouts move the views and the dimension sides but keep every feature."""
    i = resolve(inputs)
    doc = new_sheet()
    msp = doc.modelspace()
    scale = _scale(i)[1]
    frame(doc, {"part": i["part"], "material": i["material"], "scale": scale})
    w, h, t = i["width"], i["height"], i["thickness"]
    final, f = views(i, layout), _scale(i)[0]
    if f == 1.0:
        stage = final
    else:
        x0, y0 = 100.0, 1500.0  # plate places its own views, so its stage is a fixed scratch corner
        ty_s = y0 + 20 + t + 25
        stage = {"front": (x0 + 30, ty_s, w, h), "top": (x0 + 30, ty_s - 25 - t, w, t)}
    box = stage
    fx, fy = box["front"][:2]  # front view lower-left corner
    ty = box["top"][1]  # first-angle projection puts the view from above below the front view
    msp.add_lwpolyline(
        [(fx, fy), (fx + w, fy), (fx + w, fy + h), (fx, fy + h)], close=True, dxfattribs={"layer": "outline"}
    )
    cx, cy = fx + w / 2, fy + h / 2
    msp.add_circle((cx, cy), i["bore"] / 2, dxfattribs={"layer": "outline"})
    cross(msp, (cx, cy), i["bore"] / 2 + 3, i["bore"] / 2 + 3)
    holes = [
        (fx + i["inset"], fy + i["inset"]),
        (fx + w - i["inset"], fy + i["inset"]),
        (fx + w - i["inset"], fy + h - i["inset"]),
        (fx + i["inset"], fy + h - i["inset"]),
    ]
    for p in holes:
        msp.add_circle(p, i["hole"] / 2, dxfattribs={"layer": "outline"})
        cross(msp, p, i["hole"] / 2 + 3, i["hole"] / 2 + 3)
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
    bore_text = f"<>{deviations(i['bore_fit'], i['bore'])}" if inputs.get("calc") else f"<>{i['bore_fit']}"
    far = w / 2 + (48.0 if inputs.get("calc") else 20.0)  # deviations text is wider
    if f == 1.0:  # clamps keep the text inside the frame; at other scales map_point does that job
        bore_loc = (min(cx + 0.7071 * far, 395.0), min(max(cy + 0.7071 * far, fy + h + 8.0), 280.0))
    else:
        bore_loc = (cx + 0.7071 * far, cy + 0.7071 * far)
    msp.add_diameter_dim(
        center=(cx, cy),
        radius=i["bore"] / 2,
        angle=45.0 + 90 * layout,
        text=bore_text,
        location=bore_loc,
        dxfattribs=d,
        **ds,
    ).render()
    msp.add_diameter_dim(
        center=holes[2],
        radius=i["hole"] / 2,
        angle=45.0,
        text="4x <>",
        location=(min(fx + w + 17.0, 395.0) if f == 1.0 else fx + w + 17.0, holes[2][1]),
        dxfattribs=d,
        **ds,
    ).render()
    msp.add_linear_dim(
        base=(fx, fy - 8 if side > 0 else fy - 24), p1=holes[0], p2=holes[1], dxfattribs=d, **ds
    ).render()
    msp.add_linear_dim(base=(fx + i["inset"] + 6, fy), p1=holes[0], p2=holes[3], angle=90, dxfattribs=d, **ds).render()
    if f != 1.0:
        rescale(doc, stage, final)
    roughness_marks(doc, truth(inputs))
    return doc
