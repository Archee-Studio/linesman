"""A V-belt pulley: fitted bore, one V-groove around the rim, hub-to-rim web.

The front view is the axial profile drawn as the full section A-A (groove notch cut in the rim, keyway visible);
the left view is the end face. The groove flank angle is dimensioned in the section.
"""

import math
import random

from ezdxf.document import Drawing

from ..schema import Dim, Truth, View
from .drafting import (
    DIMSTYLE,
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

NAME = "pulley"


def sample(seed: int) -> dict:
    rng = random.Random(seed)
    bore = rng.choice([20, 25, 30, 35, 40])
    return {
        "part": "Pulley",
        "material": rng.choice(["EN-GJL-250", "C45", "AlMg3"]),
        "bore": float(bore),
        "bore_fit": rng.choice(["H7", "H8"]),
        "od": float(rng.choice([80, 100, 125, 160, 200, 250])),
        "width": float(rng.choice([20, 25, 30, 40])),
        "groove_angle": float(rng.choice([34, 38])),
        "groove_depth": float(rng.choice([9, 11, 14])),
        "hub": float(bore + 2 * rng.choice([8, 10, 12])),
        "keyway": rng.choice([True, False]),
        "roughness": {"bore": 1.6, "groove_flank": 3.2},
    }


def calc(seed: int) -> dict:
    """Calc-level inputs: the bore takes the mating shaft's size; the groove is stated as belt geometry."""
    i = sample(seed)
    return {
        "part": i["part"],
        "material": i["material"],
        "shaft": i["bore"],
        "bore_fit": i["bore_fit"],
        "od": i["od"],
        "width": i["width"],
        "groove_angle": i["groove_angle"],
        "groove_depth": i["groove_depth"],
        "hub_wall": (i["hub"] - i["bore"]) / 2,
        "keyway": i["keyway"],
        "roughness": i["roughness"],
        "calc": True,
    }


def resolve(inputs: dict) -> dict:
    if not inputs.get("calc"):
        return inputs
    return {
        "part": inputs["part"],
        "material": inputs["material"],
        "bore": inputs["shaft"],
        "bore_fit": inputs["bore_fit"],
        "od": inputs["od"],
        "width": inputs["width"],
        "groove_angle": inputs["groove_angle"],
        "groove_depth": inputs["groove_depth"],
        "hub": inputs["shaft"] + 2 * inputs["hub_wall"],
        "keyway": inputs["keyway"],
        "roughness": inputs["roughness"],
    }


def _sizes(i: dict) -> dict[str, tuple[float, float]]:
    return {"front": (i["width"], i["od"]), "left": (i["od"], i["od"])}


def _scale(inputs: dict) -> tuple[float, str]:
    _, _, f = draft_boxes(_sizes(resolve(inputs)), 0)
    return f, scale_name(f)


def request(inputs: dict) -> str:
    i, scale = inputs, _scale(inputs)[1]
    fit = "with its limit deviations" if i.get("calc") else "designation"
    bore = (
        f"for a shaft of diameter {i['shaft']:g} mm (the bore takes the shaft's size)"
        if i.get("calc")
        else f"bore {i['bore']:g} mm"
    )
    hub = f"hub diameter {i['shaft'] + 2 * i['hub_wall']:g} mm" if i.get("calc") else f"hub diameter {i['hub']:g} mm"
    key = " Include a keyway in the bore." if i["keyway"] else ""
    return (
        f"Draw an A3 detail sheet of the {i['part'].lower()} at {scale} in first-angle projection with a front "
        f"view drawn as the full section A-A and a left view of the end face; label the section A-A. Material "
        f"{i['material']}. Rim diameter {i['od']:g} mm, face width {i['width']:g} mm, {bore} {i['bore_fit']}, "
        f"{hub}. One V-groove centred on the face, flank angle {i['groove_angle']:g} degrees, depth "
        f"{i['groove_depth']:g} mm.{key} Dimension every feature including the groove flank angle and depth; "
        f"show the bore fit {fit}; mark the bore surface Ra {i['roughness']['bore']:g} and one groove flank "
        f"Ra {i['roughness']['groove_flank']:g}; fill the title block with part, material and scale."
    )


def views(inputs: dict, layout: int = 0) -> dict[str, Box]:
    return draft_boxes(_sizes(resolve(inputs)), layout)[1]


def _notch(i: dict) -> tuple[float, float]:
    """Groove half-width at the rim surface and its depth."""
    half = i["groove_depth"] * math.tan(math.radians(i["groove_angle"] / 2))
    return half, i["groove_depth"]


def truth(inputs: dict) -> Truth:
    i, scale = resolve(inputs), _scale(inputs)[1]
    w, d = i["width"], i["od"]
    half, depth = _notch(i)
    cut = w * d - 2 * half * depth - w * i["bore"]  # rim rectangle, less the two V notches and the bore channel
    fit_form = "deviations" if inputs.get("calc") else "any"
    dims = [
        Dim(id="od", kind="diameter", value=d, view="left"),
        Dim(id="bore", kind="diameter", value=i["bore"], view="left", fit=i["bore_fit"], fit_form=fit_form),
        Dim(id="hub", kind="diameter", value=i["hub"], view="left"),
        Dim(id="width", kind="linear", value=w, view="front"),
        Dim(id="groove_angle", kind="angular", value=i["groove_angle"], view="front"),
        Dim(id="groove_depth", kind="linear", value=depth, view="front"),
    ]
    return Truth(
        views=(
            View(name="front", width=w, height=d, hatch_area=cut),
            View(name="left", width=d, height=d),
        ),
        dims=tuple(dims),
        title={"part": i["part"], "material": i["material"], "scale": scale},
        scale=scale,
        finish={"bore": i["roughness"]["bore"], "groove_depth": i["roughness"]["groove_flank"]},
    )


def draw(inputs: dict, layout: int = 0) -> Drawing:
    i = resolve(inputs)
    doc = new_sheet()
    msp = doc.modelspace()
    frame(doc, {"part": i["part"], "material": i["material"], "scale": _scale(i)[1]})
    stage, final, f = draft_boxes(_sizes(i), layout)
    box = stage
    w, d, bore, hub = i["width"], i["od"], i["bore"], i["hub"]
    half, depth = _notch(i)

    fx, fy, _, _ = box["front"]
    cy = fy + d / 2
    gx = fx + w / 2
    top = fy + d
    bot = fy
    # axial section profile: rim rectangle with a V notch out of each rim face, hub solid between them
    outer = [
        (fx, bot),
        (gx - half, bot),
        (gx, bot + depth),
        (gx + half, bot),
        (fx + w, bot),
        (fx + w, top),
        (gx + half, top),
        (gx, top - depth),
        (gx - half, top),
        (fx, top),
    ]
    channel = [(fx, cy - bore / 2), (fx + w, cy - bore / 2), (fx + w, cy + bore / 2), (fx, cy + bore / 2)]
    msp.add_lwpolyline(outer, close=True, dxfattribs={"layer": "outline"})
    msp.add_lwpolyline(channel, close=True, dxfattribs={"layer": "outline"})
    # hub bosses stand proud of the web: lines at the hub diameter inside the section
    for y in (cy - hub / 2, cy + hub / 2):
        msp.add_line((fx, y), (fx + w, y), dxfattribs={"layer": "outline"})
    hatch(msp, outer, channel)
    line(msp, (fx, cy), (fx + w, cy), "center")

    up = 1 if layout % 2 == 0 else -1
    edge = cy + up * d / 2
    hdim(msp, (fx, edge), (fx + w, edge), edge + up * 15 / f)
    vdim(msp, (gx, top - depth), (gx + half, top), fx - 12 / f)  # groove depth
    flank1 = ((gx, top - depth), (gx + half, top))
    flank2 = ((gx, top - depth), (gx - half, top))
    msp.add_angular_dim_2l(
        base=(gx + 22 / f, top + 12 / f),
        line1=flank1,
        line2=flank2,
        text="<>",
        location=(gx + 26 / f, top + 14 / f),
        dimstyle=DIMSTYLE,
        dxfattribs={"layer": "dims"},
    ).render()
    bore_text = f"%%c<>{deviations(i['bore_fit'], bore)}" if inputs.get("calc") else f"%%c<>{i['bore_fit']}"
    vdim(msp, (fx + w * 0.25, cy - bore / 2), (fx + w * 0.25, cy + bore / 2), fx + w + 12 / f, bore_text)

    lx, ly, _, _ = box["left"]
    centre = (lx + d / 2, ly + d / 2)
    for dd in (d, d - 2 * depth, hub, bore):
        circle(msp, centre, dd)
    cross(msp, centre, d / 2, d / 2)
    from .drafting import ddim

    ddim(msp, centre, d, 30 + 90 * layout, "<>", location=(lx + d + 8 / f, centre[1]))
    ddim(msp, centre, hub, 330 + 90 * layout, "<>", location=(centre[0] + d * 0.35, ly - 8 / f))
    if i["keyway"]:
        kw = bore / 4  # simplified keyway proportions for the end view
        msp.add_lwpolyline(
            [
                (centre[0] - kw / 2, centre[1] + math.sqrt((bore / 2) ** 2 - (kw / 2) ** 2)),
                (centre[0] - kw / 2, centre[1] + bore / 2 + kw / 3),
                (centre[0] + kw / 2, centre[1] + bore / 2 + kw / 3),
                (centre[0] + kw / 2, centre[1] + math.sqrt((bore / 2) ** 2 - (kw / 2) ** 2)),
            ],
            dxfattribs={"layer": "outline"},
        )

    if f != 1.0:
        rescale(doc, stage, final)
    section_label(msp, final["front"])
    roughness_marks(doc, truth(inputs))
    return doc
