"""An L-bracket bent from plate: legs, bend radius, a hole pair in the base and a hole in the upright leg."""

import random

from ezdxf.document import Drawing

from .. import iso273
from ..schema import Dim, Truth, View
from .drafting import (
    Box,
    circle,
    cross,
    ddim,
    deviations,
    draft_boxes,
    frame,
    hdim,
    line,
    mirror,
    new_sheet,
    polar,
    rdim,
    rect,
    rescale,
    roughness_marks,
    scale_name,
    vdim,
)

NAME = "bracket"
BEND = 0.41421356237309503  # bulge of a quarter circle: tan(90 / 4)


def sample(seed: int) -> dict:
    rng = random.Random(seed)
    thickness = float(rng.choice([4, 5, 6, 8]))
    height = float(rng.choice([45, 50]))
    return {
        "part": "L-bracket",
        "material": rng.choice(["S235JR", "DC01", "AlMg3"]),
        "length": float(rng.choice(list(range(70, 111, 10)) + [160, 200, 240, 280, 320])),
        "width": float(rng.choice([40, 45, 50])),
        "height": height,
        "thickness": thickness,
        "radius": float(rng.choice([4, 6, 8])),
        "hole": rng.choice([6.6, 9.0, 11.0]),
        "hole_edge": float(rng.choice([12, 15])),
        "leg_hole": rng.choice([6.6, 9.0]),
        "leg_hole_height": height - 15.0,
        "roughness": {"leg_hole": 3.2},
    }


def calc(seed: int) -> dict:
    """Calc-level inputs: the holes are given as bolt sizes (ISO 273 medium clearance) and the leg hole takes a
    locating pin, fit H9 shown as limit deviations."""
    i = sample(seed)
    bolts = {6.6: "M6", 9.0: "M8", 11.0: "M10"}
    i = {**i, "bolt": bolts[i["hole"]], "pin_bolt": bolts[i["leg_hole"]], "leg_fit": "H9", "calc": True}
    del i["hole"], i["leg_hole"]
    return i


def resolve(inputs: dict) -> dict:
    """Requirement inputs (calc) expanded to the full given values."""
    if not inputs.get("calc"):
        return inputs
    i = {k: v for k, v in inputs.items() if k not in ("bolt", "pin_bolt", "leg_fit", "calc")}
    i["hole"] = iso273.medium(inputs["bolt"])
    i["leg_hole"] = iso273.medium(inputs["pin_bolt"])
    return i


def _pitch(inputs: dict) -> float:
    return resolve(inputs)["width"] - 20.0


def _sizes(i: dict) -> dict[str, tuple[float, float]]:
    return {"front": (i["length"], i["height"]), "top": (i["length"], i["width"]), "left": (i["width"], i["height"])}


def _scale(inputs: dict) -> tuple[float, str]:
    _, _, f = draft_boxes(_sizes(resolve(inputs)), 0)
    return f, scale_name(f)


def request(inputs: dict) -> str:
    i, scale = inputs, _scale(inputs)[1]
    if i.get("calc"):
        holes = f"two through holes for {i['bolt']} bolts, medium clearance per ISO 273"
        leg = (
            f"a hole for a locating pin, {i['pin_bolt']} medium clearance per ISO 273, "
            f"fit {i['leg_fit']} as limit deviations"
        )
    else:
        holes = f"two {i['hole']:g} mm holes"
        leg = f"one {i['leg_hole']:g} mm hole"
    j = resolve(i)
    return (
        f"Draw an A3 detail sheet of the {i['part']} at {scale} in first-angle projection with a front, a top "
        f"and a left view; the upright leg is at the left end of the front view. Bent from {i['thickness']:g} mm "
        f"{i['material']} plate: base {i['length']:g} mm long, upright leg {i['height']:g} mm high (both outside "
        f"measures), {i['width']:g} mm wide, inside bend radius {i['radius']:g} mm. {holes.capitalize()} in "
        f"the base, {i['hole_edge']:g} mm from the free end and {_pitch(i):g} mm apart, centred on the width. "
        f"{leg.capitalize()}, centred on the width, {i['leg_hole_height']:g} mm above the underside of the base. "
        f"Dimension every feature; mark the leg hole surface Ra {j['roughness']['leg_hole']:g}; fill the title "
        "block with part, material and scale."
    )


def views(inputs: dict, layout: int = 0) -> dict[str, Box]:
    return draft_boxes(_sizes(resolve(inputs)), layout)[1]


def truth(inputs: dict) -> Truth:
    i, scale = resolve(inputs), _scale(inputs)[1]
    leg_fit = inputs.get("leg_fit")
    return Truth(
        views=(
            View(name="front", width=i["length"], height=i["height"], hidden=True),
            View(name="top", width=i["length"], height=i["width"]),
            View(name="left", width=i["width"], height=i["height"]),
        ),
        dims=(
            Dim(id="length", kind="linear", value=i["length"], view="front"),
            Dim(id="height", kind="linear", value=i["height"], view="front"),
            Dim(id="thickness", kind="linear", value=i["thickness"], view="front"),
            Dim(id="bend_radius", kind="radius", value=i["radius"], view="front"),
            Dim(id="hole", kind="diameter", value=i["hole"], view="top"),
            Dim(id="hole_edge", kind="linear", value=i["hole_edge"], view="top"),
            Dim(id="hole_pitch", kind="linear", value=_pitch(i), view="top"),
            Dim(id="width", kind="linear", value=i["width"], view="left"),
            Dim(
                id="leg_hole",
                kind="diameter",
                value=i["leg_hole"],
                view="left",
                fit=leg_fit,
                fit_form="deviations" if leg_fit else "any",
            ),
            Dim(id="leg_hole_height", kind="linear", value=i["leg_hole_height"], view="left"),
        ),
        title={"part": i["part"], "material": i["material"], "scale": scale},
        scale=scale,
        finish=i["roughness"],
    )


def draw(inputs: dict, layout: int = 0) -> Drawing:
    i = resolve(inputs)
    doc = new_sheet()
    msp = doc.modelspace()
    scale = _scale(i)[1]
    frame(doc, {"part": i["part"], "material": i["material"], "scale": scale})
    stage, final, f = draft_boxes(_sizes(i), layout)
    box = stage
    a, w, h, t, r = i["length"], i["width"], i["height"], i["thickness"], i["radius"]
    ro = r + t
    above = layout == 1  # the hole-edge dimension of the top view sits above the view, else below it

    fx, fy, _, _ = box["front"]
    pts = [(0, h, 0), (0, ro, BEND), (ro, 0, 0), (a, 0, 0), (a, t, 0), (t + r, t, -BEND), (t, t + r, 0), (t, h, 0)]
    msp.add_lwpolyline(
        [(fx + x, fy + y, b) for x, y, b in pts], format="xyb", close=True, dxfattribs={"layer": "outline"}
    )
    hx = fx + a - i["hole_edge"]
    for dx in (-i["hole"] / 2, i["hole"] / 2):
        line(msp, (hx + dx, fy), (hx + dx, fy + t), "hidden")
    for dy in (-i["leg_hole"] / 2, i["leg_hole"] / 2):
        line(msp, (fx, fy + i["leg_hole_height"] + dy), (fx + t, fy + i["leg_hole_height"] + dy), "hidden")
    hdim(msp, (fx, fy + h), (fx + a, fy + t), fy + h + 12 / f)
    vdim(msp, (fx + a, fy), (fx, fy + h), fx - 14 / f)
    vdim(msp, (fx + a, fy), (fx + a, fy + t), fx + a + 12 / f)
    rdim(
        msp,
        (fx + t + r, fy + t + r),
        r,
        (210.0, 225.0, 240.0)[layout % 3],
        location=polar((fx + t + r, fy + t + r), r + 24 / f, (210.0, 225.0, 240.0)[layout % 3]),
    )

    tx, ty, _, _ = box["top"]
    rect(msp, tx, ty, a, w)
    for x in (t, t + r):
        line(msp, (tx + x, ty), (tx + x, ty + w))
    centres = [(tx + a - i["hole_edge"], ty + w / 2 + s * _pitch(i) / 2) for s in (-1, 1)]
    for p in centres:
        circle(msp, p, i["hole"])
    cross(msp, (tx + a - i["hole_edge"], ty + w / 2), 0.0, w / 2)
    near, far = (ty + w + 10 / f, ty - 12 / f) if not above else (ty - 12 / f, ty + w + 10 / f)
    ddim(
        msp,
        centres[1] if not above else centres[0],
        i["hole"],
        mirror(30, layout),
        "2x <>",
        location=(centres[1][0] + 20 / f, near),
    )
    hdim(msp, centres[1] if above else centres[0], (tx + a, centres[1][1] if above else centres[0][1]), far)
    vdim(msp, centres[0], centres[1], tx + a + 14 / f)

    lx, ly, _, _ = box["left"]
    rect(msp, lx, ly, w, h)
    line(msp, (lx, ly + ro), (lx + w, ly + ro))
    p = (lx + w / 2, ly + i["leg_hole_height"])
    circle(msp, p, i["leg_hole"])
    cross(msp, p, w / 2, i["leg_hole"] / 2 + 3)
    hdim(msp, (lx, ly + h), (lx + w, ly + h), ly + h + 12 / f)
    vdim(msp, (lx + w, ly), p, lx + w + 15 / f)
    leg_text = "<>" + (deviations(inputs["leg_fit"], i["leg_hole"]) if inputs.get("calc") else "")
    ddim(msp, p, i["leg_hole"], mirror(45, layout), leg_text, location=(lx + w + 14 / f, ly + h + 2 / f))
    if f != 1.0:
        rescale(doc, stage, final)
    roughness_marks(doc, truth(inputs))
    return doc
