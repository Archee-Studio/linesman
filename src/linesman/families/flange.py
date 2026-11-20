"""A round flange with a spigot, a fitted bore and bolt holes on a pitch circle.

The front view is the axial profile drawn as the full section A-A; the left view is the circular face.
"""

import random

from ezdxf.document import Drawing

from .. import iso273
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
    polar,
    rescale,
    roughness_marks,
    scale_name,
    section_label,
    vdim,
)

NAME = "flange"
# outside diameter, pitch circle diameter, holes, bolt size (ISO 273 medium gives the hole)
SIZES = (
    (90, 65, 4, "M8"),
    (100, 75, 4, "M8"),
    (110, 80, 4, "M10"),
    (120, 90, 6, "M10"),
    (130, 100, 6, "M10"),
    (140, 105, 6, "M12"),
    (150, 110, 8, "M12"),
    (180, 140, 8, "M16"),
    (200, 160, 8, "M16"),
    (250, 210, 8, "M20"),
    (300, 250, 8, "M20"),
)


def sample(seed: int) -> dict:
    rng = random.Random(seed)
    od, pcd, holes, bolt = rng.choice(SIZES)
    hole = iso273.medium(bolt)
    bore = rng.choice([b for b in (16, 20, 25, 30, 35, 40) if b + 16 <= pcd - hole - 8])
    return {
        "part": "Flange",
        "material": rng.choice(["S235JR", "C45", "EN-GJL-250"]),
        "od": float(od),
        "pcd": float(pcd),
        "holes": holes,
        "hole": hole,
        "bore": float(bore),
        "bore_fit": "H7",
        "spigot": float(bore + 16),
        "thickness": float(rng.choice([10, 12, 14, 16])),
        "spigot_length": float(rng.choice([8, 10, 12, 15])),
        "roughness": {"bore": 1.6},
    }


def calc(seed: int) -> dict:
    """Calc-level inputs: the holes are given as a bolt size (ISO 273 medium clearance), the bore fit as
    limit deviations."""
    i = sample(seed)
    i = {**i, "bolt": _bolt_of(i["hole"]), "calc": True}
    i.pop("hole")
    return i


def _bolt_of(hole: float) -> str:
    return {iso273.medium(s[3]): s[3] for s in SIZES}[hole]


def resolve(inputs: dict) -> dict:
    """Requirement inputs (calc) expanded to the full given values."""
    if not inputs.get("calc"):
        return inputs
    return {**inputs, "hole": iso273.medium(inputs["bolt"])}


def _sizes(i: dict) -> dict[str, tuple[float, float]]:
    return {"front": (i["thickness"] + i["spigot_length"], i["od"]), "left": (i["od"], i["od"])}


def _scale(inputs: dict) -> tuple[float, str]:
    _, _, f = draft_boxes(_sizes(resolve(inputs)), 0)
    return f, scale_name(f)


def request(inputs: dict) -> str:
    i, scale = inputs, _scale(inputs)[1]
    holes = (
        f"{i['holes']} through holes for {i['bolt']} bolts, medium clearance per ISO 273"
        if i.get("calc")
        else f"{i['holes']} through holes {i['hole']:g} mm"
    )
    fit = "with its limit deviations" if i.get("calc") else "designation"
    return (
        f"Draw an A3 detail sheet of the {i['part'].lower()} at {scale} in first-angle projection with a front view "
        f"drawn as the full section A-A (the section plane passes through two bolt-hole axes) and a left view of "
        f"the circular face, spigot towards the viewer; label the section A-A. Material {i['material']}. Outside "
        f"diameter {i['od']:g} mm, flange thickness {i['thickness']:g} mm. Spigot diameter {i['spigot']:g} mm, "
        f"{i['spigot_length']:g} mm long. Central bore {i['bore']:g} {i['bore_fit']}. {holes.capitalize()} on a "
        f"{i['pcd']:g} mm pitch circle, equally spaced. Dimension every feature; show the fit on the bore {fit}; "
        "mark the bore surface Ra 1.6; fill the title block with part, material and scale."
    )


def views(inputs: dict, layout: int = 0) -> dict[str, Box]:
    return draft_boxes(_sizes(resolve(inputs)), layout)[1]


def truth(inputs: dict) -> Truth:
    i, scale = resolve(inputs), _scale(inputs)[1]
    t, ls = i["thickness"], i["spigot_length"]
    hatch_area = t * i["od"] + ls * i["spigot"] - (t + ls) * i["bore"] - 2 * t * i["hole"]
    fit_form = "deviations" if inputs.get("calc") else "any"
    return Truth(
        views=(
            View(name="front", width=t + ls, height=i["od"], hatch_area=hatch_area),
            View(name="left", width=i["od"], height=i["od"]),
        ),
        dims=(
            Dim(id="od", kind="diameter", value=i["od"], view="front"),
            Dim(id="pcd", kind="diameter", value=i["pcd"], view="front"),
            Dim(id="hole", kind="diameter", value=i["hole"], view="front"),
            Dim(id="bore", kind="diameter", value=i["bore"], view="front", fit=i["bore_fit"], fit_form=fit_form),
            Dim(id="spigot", kind="diameter", value=i["spigot"], view="front"),
            Dim(id="thickness", kind="linear", value=t, view="front"),
            Dim(id="spigot_length", kind="linear", value=ls, view="front"),
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
    od, pcd, n = i["od"], i["pcd"], i["holes"]
    t, ls = i["thickness"], i["spigot_length"]

    lx, ly, w, h = box["front"]  # the axial profile, sectioned
    cy = ly + od / 2
    outer = [
        (lx, ly),
        (lx + t, ly),
        (lx + t, cy - i["spigot"] / 2),
        (lx + w, cy - i["spigot"] / 2),
        (lx + w, cy + i["spigot"] / 2),
        (lx + t, cy + i["spigot"] / 2),
        (lx + t, ly + h),
        (lx, ly + h),
    ]
    msp.add_lwpolyline(outer, close=True, dxfattribs={"layer": "outline"})
    channel = [
        (lx, cy - i["bore"] / 2),
        (lx + w, cy - i["bore"] / 2),
        (lx + w, cy + i["bore"] / 2),
        (lx, cy + i["bore"] / 2),
    ]
    msp.add_lwpolyline(channel, close=True, dxfattribs={"layer": "outline"})
    slots = []
    for sgn in (-1, 1):
        slot = [
            (lx, cy + sgn * (pcd / 2 - i["hole"] / 2)),
            (lx + t, cy + sgn * (pcd / 2 - i["hole"] / 2)),
            (lx + t, cy + sgn * (pcd / 2 + i["hole"] / 2)),
            (lx, cy + sgn * (pcd / 2 + i["hole"] / 2)),
        ]
        slots.append(slot)
        msp.add_lwpolyline(slot, close=True, dxfattribs={"layer": "outline"})
        line(msp, (lx, cy + sgn * pcd / 2), (lx + t, cy + sgn * pcd / 2), "center")
    hatch(msp, outer, channel, *slots)
    line(msp, (lx, cy), (lx + w, cy), "center")

    up = 1 if layout % 2 == 0 else -1
    edge = cy + up * od / 2
    hdim(msp, (lx, edge), (lx + t, edge), edge + up * 15)
    hdim(
        msp,
        (lx + t, cy - up * i["spigot"] / 2),
        (lx + w, cy - up * i["spigot"] / 2),
        cy - up * (i["spigot"] / 2 + 10),
        location=(lx + w + 8, cy - up * (i["spigot"] / 2 + 10)),
    )
    x_mid = lx + t / 2
    bore_text = f"%%c<>{deviations(i['bore_fit'], i['bore'])}" if inputs.get("calc") else f"%%c<>{i['bore_fit']}"
    vdim(msp, (x_mid, ly), (x_mid, ly + h), lx - 24, "%%c<>")
    vdim(msp, (lx + w / 2, cy - i["bore"] / 2), (lx + w / 2, cy + i["bore"] / 2), lx - 12, bore_text)
    vdim(
        msp,
        (lx + t + ls / 2, cy - i["spigot"] / 2),
        (lx + t + ls / 2, cy + i["spigot"] / 2),
        lx + w + 12,
        "%%c<>",
    )
    vdim(
        msp,
        (x_mid, cy + pcd / 2 + i["hole"] / 2),
        (x_mid, cy - pcd / 2 + i["hole"] / 2),
        lx + w + 24,
        "%%c<>",
    )
    vdim(
        msp,
        (x_mid, cy + pcd / 2 - i["hole"] / 2),
        (x_mid, cy + pcd / 2 + i["hole"] / 2),
        lx + w + 36,
        f"{n}x %%c<>",
    )

    gx, gy, _, _ = box["left"]  # the circular face
    c = (gx + od / 2, gy + od / 2)
    for d in (od, i["spigot"], i["bore"]):
        circle(msp, c, d)
    circle(msp, c, pcd, "center")
    cross(msp, c, od / 2, od / 2)
    start = 45.0 if n == 4 else 90.0
    angles = [start + 360.0 * k / n for k in range(n)]
    for a in angles:
        circle(msp, polar(c, pcd / 2, a), i["hole"])

    if f != 1.0:
        rescale(doc, stage, final)
    section_label(msp, final["front"])
    roughness_marks(doc, truth(inputs))
    return doc
