"""A press-fit sleeve: fitted outside and inside diameters, length and 45 degree chamfers.

The front view is the axial profile drawn as the full section A-A; the left view is the end face.
"""

import random

from ezdxf.document import Drawing

from ..schema import Dim, Truth, View
from .drafting import (
    Box,
    circle,
    cross,
    deviations,
    draft_boxes,
    frame,
    hatch,
    hdim,
    line,
    new_sheet,
    rescale,
    roughness_marks,
    scale_name,
    section_label,
    vdim,
)

NAME = "bushing"
WALLS = (5, 6, 8, 10)


def sample(seed: int) -> dict:
    rng = random.Random(seed)
    bore = rng.choice([20, 25, 30, 35, 40, 50])
    return {
        "part": "Bushing",
        "material": rng.choice(["CuSn8", "C45", "16MnCr5"]),
        "bore": float(bore),
        "bore_fit": rng.choice(["H7", "F7"]),
        "od": float(bore + 2 * rng.choice(WALLS)),
        "od_fit": rng.choice(["p6", "s6"]),
        "length": float(rng.choice([25, 30, 40, 50, 60, 70])),
        "chamfer": rng.choice([0.5, 1.0, 1.5]),
        "roughness": {"bore": 1.6, "od": 3.2},
    }


def calc(seed: int) -> dict:
    """Calc-level inputs: requirements instead of finished values — the sleeve is for a stated shaft and wall."""
    i = sample(seed)
    return {
        "part": i["part"],
        "material": i["material"],
        "shaft": i["bore"],
        "bore_fit": i["bore_fit"],
        "wall": (i["od"] - i["bore"]) / 2,
        "od_fit": i["od_fit"],
        "length": i["length"],
        "chamfer": i["chamfer"],
        "roughness": i["roughness"],
        "calc": True,
    }


def resolve(inputs: dict) -> dict:
    """Requirement inputs (calc) expanded to the full given values: the bore takes the shaft's size."""
    if not inputs.get("calc"):
        return inputs
    return {
        "part": inputs["part"],
        "material": inputs["material"],
        "bore": inputs["shaft"],
        "bore_fit": inputs["bore_fit"],
        "od": inputs["shaft"] + 2 * inputs["wall"],
        "od_fit": inputs["od_fit"],
        "length": inputs["length"],
        "chamfer": inputs["chamfer"],
        "roughness": inputs["roughness"],
    }


def _sizes(i: dict) -> dict[str, tuple[float, float]]:
    return {"front": (i["length"], i["od"]), "left": (i["od"], i["od"])}


def _scale(inputs: dict) -> tuple[float, str]:
    _, _, f = draft_boxes(_sizes(resolve(inputs)), 0)
    return f, scale_name(f)


def request(inputs: dict) -> str:
    i, scale = inputs, _scale(inputs)[1]
    fit = "with its limit deviations" if i.get("calc") else "designation"
    if i.get("calc"):
        what = (
            f"for a shaft of diameter {i['shaft']:g} mm (the bore takes the shaft's size), wall {i['wall']:g} mm, "
            f"outside {i['od_fit']} (press fit)"
        )
    else:
        what = f"outside diameter {i['od']:g} {i['od_fit']} (press fit), bore {i['bore']:g} {i['bore_fit']}"
    return (
        f"Draw an A3 detail sheet of the {i['part'].lower()} at {scale} in first-angle projection with a front view "
        f"drawn as the full section A-A and a left view of the end face; label the section A-A. Material "
        f"{i['material']}. {what}, length {i['length']:g} mm, chamfer {i['chamfer']:g} x 45 degrees on all four "
        f"edges. Dimension every feature; show both fits, the bore fit {fit}; mark the bore surface Ra 1.6 and "
        "the outside surface Ra 3.2; fill the title block with part, material and scale."
    )


def views(inputs: dict, layout: int = 0) -> dict[str, Box]:
    return draft_boxes(_sizes(resolve(inputs)), layout)[1]


def truth(inputs: dict) -> Truth:
    i, scale = resolve(inputs), _scale(inputs)[1]
    c, length = i["chamfer"], i["length"]
    # cut material in the section = chamfered outer profile minus the chamfered bore channel
    hatch_area = length * i["od"] - 2 * c * c - (length * i["bore"] + 2 * c * c)
    fit_form = "deviations" if inputs.get("calc") else "any"
    return Truth(
        views=(
            View(name="front", width=length, height=i["od"], hatch_area=hatch_area),
            View(name="left", width=i["od"], height=i["od"]),
        ),
        dims=(
            Dim(id="od", kind="diameter", value=i["od"], view="left", fit=i["od_fit"]),
            Dim(id="bore", kind="diameter", value=i["bore"], view="left", fit=i["bore_fit"], fit_form=fit_form),
            Dim(id="length", kind="linear", value=length, view="front"),
            Dim(id="chamfer", kind="linear", value=c, view="front"),
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
    od, bore, length, c = i["od"], i["bore"], i["length"], i["chamfer"]

    fx, fy, _, _ = box["front"]  # the axial profile, sectioned
    cy, r = fy + od / 2, od / 2
    outer = [
        (fx + c, fy),
        (fx + length - c, fy),
        (fx + length, fy + c),
        (fx + length, fy + od - c),
        (fx + length - c, fy + od),
        (fx + c, fy + od),
        (fx, fy + od - c),
        (fx, fy + c),
    ]
    msp.add_lwpolyline(outer, close=True, dxfattribs={"layer": "outline"})
    h = bore / 2
    channel = [
        (fx, cy - h - c),
        (fx + c, cy - h),
        (fx + length - c, cy - h),
        (fx + length, cy - h - c),
        (fx + length, cy + h + c),
        (fx + length - c, cy + h),
        (fx + c, cy + h),
        (fx, cy + h + c),
    ]
    msp.add_lwpolyline(channel, close=True, dxfattribs={"layer": "outline"})
    hatch(msp, outer, channel)
    line(msp, (fx, cy), (fx + length, cy), "center")
    up = 1 if layout % 2 == 0 else -1
    edge = cy + up * r
    hdim(msp, (fx, edge - up * c), (fx + length, edge - up * c), edge + up * 15)
    vdim(msp, (fx, edge - up * c), (fx + c, edge), fx - 10)  # the chamfer leg, vertex to vertex
    x_mid = fx + length / 2
    bore_text = f"%%c<>{deviations(i['bore_fit'], bore)}" if inputs.get("calc") else f"%%c<>{i['bore_fit']}"
    vdim(msp, (x_mid, cy - h), (x_mid, cy + h), fx - 15 / f, bore_text)
    vdim(msp, (x_mid, fy), (x_mid, fy + od), fx + length + 15 / f, "%%c<>" + i["od_fit"])

    lx, ly, _, _ = box["left"]  # the end face
    centre = (lx + od / 2, ly + od / 2)
    for d in (od, od - 2 * c, bore, bore + 2 * c):
        circle(msp, centre, d)
    cross(msp, centre, od / 2, od / 2)

    if f != 1.0:
        rescale(doc, stage, final)
    section_label(msp, final["front"])
    roughness_marks(doc, truth(inputs))
    return doc
