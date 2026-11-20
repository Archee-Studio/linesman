"""A rectangular cover: four clearance holes in the corners and two oblong slots on the centre line."""

import random

from ezdxf.document import Drawing

from .. import iso273
from ..schema import Dim, Truth, View
from .drafting import (
    Box,
    cross,
    ddim,
    draft_boxes,
    frame,
    hdim,
    new_sheet,
    rescale,
    roughness_marks,
    scale_name,
    vdim,
)

NAME = "cover"
BOLTS = {"M6": 6.6, "M8": 9.0, "M10": 11.0}


def sample(seed: int) -> dict:
    rng = random.Random(seed)
    bolt = rng.choice(list(BOLTS))
    return {
        "part": "Cover",
        "material": rng.choice(["S235", "AlMg3", "C45"]),
        "width": float(rng.choice(list(range(100, 221, 10)) + [280, 300, 320, 340])),
        "height": float(rng.choice(range(50, 91, 10))),
        "thickness": float(rng.choice([4, 6, 8, 10])),
        "bolt": bolt,
        "slot_bolt": rng.choice(list(BOLTS)),
        "slot_length": float(rng.choice([20, 25, 30, 40])),
        "slot_pitch": float(rng.choice([40, 50, 60, 80, 100])),  # bounded below against the width
        "inset": 10.0,
        "roughness": {"hole": 6.3},
    }


def _bounded(inputs: dict) -> dict:
    """Slots must fit inside the cover: half pitch plus half length stay inside the outline."""
    w = inputs["width"]
    i = dict(inputs)
    i["slot_length"] = min(i["slot_length"], (w - 40) / 2)
    i["slot_pitch"] = min(i["slot_pitch"], w - 2 * i["inset"] - i["slot_length"] - 10)
    return i


def calc(seed: int) -> dict:
    """Cover already states requirements (bolt sizes), so the calc level is the given sheet."""
    return {**sample(seed), "calc": True}


def resolve(inputs: dict) -> dict:
    i = _bounded(inputs)
    return {**i, "hole": iso273.medium(i["bolt"]), "slot_width": iso273.medium(i["slot_bolt"])}


def _sizes(i: dict) -> dict[str, tuple[float, float]]:
    return {"front": (i["width"], i["height"]), "top": (i["width"], i["thickness"])}


def _scale(inputs: dict) -> tuple[float, str]:
    _, _, f = draft_boxes(_sizes(resolve(inputs)), 0)
    return f, scale_name(f)


def request(inputs: dict) -> str:
    i, scale = inputs, _scale(inputs)[1]
    return (
        f"Draw an A3 detail sheet of the {i['part'].lower()} at {scale} in first-angle projection with a front "
        f"and a top view. Cover {i['width']:g} x {i['height']:g} mm, {i['thickness']:g} mm thick, "
        f"{i['material']}. Four through holes for {i['bolt']} bolts, medium clearance per ISO 273, centres "
        f"{i['inset']:g} mm in from each edge. Two oblong slots for {i['slot_bolt']} bolts, medium clearance per "
        f"ISO 273, {i['slot_length']:g} mm long end to end, on the horizontal centre line "
        f"{i['slot_pitch']:g} mm apart. Dimension every feature including the slot length and pitch; fill the "
        "title block with part, material and scale."
    )


def views(inputs: dict, layout: int = 0) -> dict[str, Box]:
    return draft_boxes(_sizes(resolve(inputs)), layout)[1]


def truth(inputs: dict) -> Truth:
    i, scale = resolve(inputs), _scale(inputs)[1]
    px, py = i["width"] - 2 * i["inset"], i["height"] - 2 * i["inset"]
    return Truth(
        views=(
            View(name="front", width=i["width"], height=i["height"]),
            View(name="top", width=i["width"], height=i["thickness"], hidden=True),
        ),
        dims=(
            Dim(id="width", kind="linear", value=i["width"], view="front"),
            Dim(id="height", kind="linear", value=i["height"], view="front"),
            Dim(id="thickness", kind="linear", value=i["thickness"], view="top"),
            Dim(id="hole", kind="diameter", value=i["hole"], view="front"),
            Dim(id="pitch_x", kind="linear", value=px, view="front", alt=(i["inset"],)),
            Dim(id="pitch_y", kind="linear", value=py, view="front", alt=(i["inset"],)),
            Dim(id="slot_width", kind="linear", value=i["slot_width"], view="front"),
            Dim(id="slot_length", kind="linear", value=i["slot_length"], view="front"),
            Dim(id="slot_pitch", kind="linear", value=i["slot_pitch"], view="front"),
        ),
        title={"part": i["part"], "material": i["material"], "scale": scale},
        scale=scale,
        finish=i["roughness"],
    )


def _slot(msp, c, sl: float, sw: float) -> None:
    """An oblong slot centred at c: two straight sides closed by semicircular ends."""
    x0, x1 = c[0] - sl / 2, c[0] + sl / 2
    y = (c[1] - sw / 2, c[1] + sw / 2)
    msp.add_line((x0, y[0]), (x1, y[0]), dxfattribs={"layer": "outline"})
    msp.add_line((x0, y[1]), (x1, y[1]), dxfattribs={"layer": "outline"})
    msp.add_arc((x0, c[1]), sw / 2, 90, 270, dxfattribs={"layer": "outline"})
    msp.add_arc((x1, c[1]), sw / 2, 270, 90, dxfattribs={"layer": "outline"})
    cross(msp, c, sw / 2 + 3, sw / 2 + 3)


def draw(inputs: dict, layout: int = 0) -> Drawing:
    i = resolve(inputs)
    doc = new_sheet()
    msp = doc.modelspace()
    frame(doc, {"part": i["part"], "material": i["material"], "scale": _scale(i)[1]})
    stage, final, f = draft_boxes(_sizes(i), layout)
    box = stage
    w, h = i["width"], i["height"]

    fx, fy, _, _ = box["front"]
    cx, cy = fx + w / 2, fy + h / 2
    msp.add_lwpolyline(
        [(fx, fy), (fx + w, fy), (fx + w, fy + h), (fx, fy + h)], close=True, dxfattribs={"layer": "outline"}
    )
    holes = [
        (fx + i["inset"], fy + i["inset"]),
        (fx + w - i["inset"], fy + i["inset"]),
        (fx + w - i["inset"], fy + h - i["inset"]),
        (fx + i["inset"], fy + h - i["inset"]),
    ]
    for p in holes:
        msp.add_circle(p, i["hole"] / 2, dxfattribs={"layer": "outline"})
        cross(msp, p, i["hole"] / 2 + 3, i["hole"] / 2 + 3)
    s1, s2 = (cx - i["slot_pitch"] / 2, cy), (cx + i["slot_pitch"] / 2, cy)
    _slot(msp, s1, i["slot_length"], i["slot_width"])
    _slot(msp, s2, i["slot_length"], i["slot_width"])

    tx, ty, tw, th = box["top"]
    msp.add_lwpolyline(
        [(tx, ty), (tx + tw, ty), (tx + tw, ty + th), (tx, ty + th)], close=True, dxfattribs={"layer": "outline"}
    )
    for x in (cx - i["slot_pitch"] / 2 - i["slot_length"] / 2, cx + i["slot_pitch"] / 2 + i["slot_length"] / 2):
        msp.add_line((x, ty), (x, ty + th), dxfattribs={"layer": "hidden"})
    for x in (fx + i["inset"], fx + w - i["inset"]):
        msp.add_line((x, ty), (x, ty + th), dxfattribs={"layer": "hidden"})

    side = 1 if layout % 2 == 0 else -1
    above = fy + h + 12 / f if side > 0 else fy - 12 / f
    hdim(msp, (fx, fy + h), (fx + w, fy + h), above)
    left = fx - 12 / f if side > 0 else fx + w + 12 / f
    vdim(msp, (fx, fy), (fx, fy + h), left)
    vdim(msp, (tx + tw, ty), (tx + tw, ty + th), tx + tw + 12 / f)
    ddim(msp, holes[2], i["hole"], 45, "4x <>", location=(fx + w + 18 / f, holes[2][1] + 6 / f))
    hdim(msp, holes[0], holes[1], fy - 10 / f if side > 0 else fy - 26 / f)
    vdim(msp, holes[0], holes[3], fx - 36 / f if side > 0 else fx + w + 24 / f)
    hdim(msp, (s1[0], cy), (s2[0], cy), fy + h + 24 / f)
    hdim(
        msp,
        (s1[0] - i["slot_length"] / 2, cy),
        (s1[0] + i["slot_length"] / 2, cy),
        fy - 26 / f if side > 0 else fy - 10 / f,
    )
    vdim(msp, (s1[0], cy - i["slot_width"] / 2), (s1[0], cy + i["slot_width"] / 2), fx - 24 / f)

    if f != 1.0:
        rescale(doc, stage, final)
    roughness_marks(doc, truth(inputs))
    return doc
