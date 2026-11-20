"""A lever: two bosses at a centre distance joined by a web, each boss bored for its shaft.

The front view shows the two boss outlines and their tangent web; the top view shows the arm's thickness.
"""

import math
import random

from ezdxf.document import Drawing

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
    new_sheet,
    rdim,
    rescale,
    roughness_marks,
    scale_name,
    vdim,
)

NAME = "lever"
FIT_SHAFTS = (12, 16, 20, 25, 30)


def sample(seed: int) -> dict:
    rng = random.Random(seed)
    d1 = rng.choice(FIT_SHAFTS)
    d2 = rng.choice([d for d in FIT_SHAFTS if d <= d1])
    w1, w2 = rng.choice([4, 5, 6, 8]), rng.choice([4, 5, 6, 8])
    return {
        "part": "Lever",
        "material": rng.choice(["C45", "S235", "42CrMo4"]),
        "bore_big": float(d1),
        "bore_big_fit": rng.choice(["H7", "H8"]),
        "bore_small": float(d2),
        "bore_small_fit": rng.choice(["H7", "H8"]),
        "wall_big": float(w1),
        "wall_small": float(w2),
        "distance": float(rng.choice([60, 80, 100, 125, 160, 200, 250, 280, 320])),
        "thickness": float(rng.choice([8, 10, 12, 16])),
        "roughness": {"bore_big": 1.6, "bore_small": 3.2},
    }


def calc(seed: int) -> dict:
    """Calc-level inputs: the bores take their shaft sizes; boss outer radii come from the stated walls."""
    i = sample(seed)
    return {
        "part": i["part"],
        "material": i["material"],
        "shaft_big": i["bore_big"],
        "bore_big_fit": i["bore_big_fit"],
        "shaft_small": i["bore_small"],
        "bore_small_fit": i["bore_small_fit"],
        "wall_big": i["wall_big"],
        "wall_small": i["wall_small"],
        "distance": i["distance"],
        "thickness": i["thickness"],
        "roughness": i["roughness"],
        "calc": True,
    }


def resolve(inputs: dict) -> dict:
    if not inputs.get("calc"):
        return inputs
    return {
        "part": inputs["part"],
        "material": inputs["material"],
        "bore_big": inputs["shaft_big"],
        "bore_big_fit": inputs["bore_big_fit"],
        "bore_small": inputs["shaft_small"],
        "bore_small_fit": inputs["bore_small_fit"],
        "wall_big": inputs["wall_big"],
        "wall_small": inputs["wall_small"],
        "distance": inputs["distance"],
        "thickness": inputs["thickness"],
        "roughness": inputs["roughness"],
    }


def _r(i: dict) -> tuple[float, float]:
    return i["bore_big"] / 2 + i["wall_big"], i["bore_small"] / 2 + i["wall_small"]


def _sizes(i: dict) -> dict[str, tuple[float, float]]:
    r1, r2 = _r(i)
    w = i["distance"] + r1 + r2
    return {"front": (w, 2 * max(r1, r2)), "top": (w, i["thickness"])}


def _scale(inputs: dict) -> tuple[float, str]:
    _, _, f = draft_boxes(_sizes(resolve(inputs)), 0)
    return f, scale_name(f)


def request(inputs: dict) -> str:
    i, scale = inputs, _scale(inputs)[1]
    fit = "with their limit deviations" if i.get("calc") else "designations"
    if i.get("calc"):
        bores = (
            f"bosses bored for shafts of {i['shaft_big']:g} mm and {i['shaft_small']:g} mm (each bore takes its "
            f"shaft's size) with wall thicknesses {i['wall_big']:g} mm and {i['wall_small']:g} mm"
        )
    else:
        r1, r2 = _r(i)
        bores = (
            f"bores {i['bore_big']:g} {i['bore_big_fit']} and {i['bore_small']:g} {i['bore_small_fit']}, "
            f"boss radii {r1:g} mm and {r2:g} mm"
        )
    return (
        f"Draw an A3 detail sheet of the {i['part'].lower()} at {scale} in first-angle projection with a front "
        f"view of the two bosses joined by a tangent web and a top view showing the arm's thickness. Material "
        f"{i['material']}. Centre distance {i['distance']:g} mm, {bores}, uniform thickness "
        f"{i['thickness']:g} mm. Dimension every feature including the centre distance, both boss radii and the "
        f"thickness; show both bore fits {fit}; mark the big bore Ra {i['roughness']['bore_big']:g} and the "
        f"small bore Ra {i['roughness']['bore_small']:g}; fill the title block with part, material and scale."
    )


def views(inputs: dict, layout: int = 0) -> dict[str, Box]:
    return draft_boxes(_sizes(resolve(inputs)), layout)[1]


def truth(inputs: dict) -> Truth:
    i, scale = resolve(inputs), _scale(inputs)[1]
    r1, r2 = _r(i)
    w, h = i["distance"] + r1 + r2, 2 * max(r1, r2)
    fit_form = "deviations" if inputs.get("calc") else "any"
    return Truth(
        views=(View(name="front", width=w, height=h), View(name="top", width=w, height=i["thickness"])),
        dims=(
            Dim(
                id="bore_big",
                kind="diameter",
                value=i["bore_big"],
                view="front",
                fit=i["bore_big_fit"],
                fit_form=fit_form,
            ),
            Dim(
                id="bore_small",
                kind="diameter",
                value=i["bore_small"],
                view="front",
                fit=i["bore_small_fit"],
                fit_form=fit_form,
            ),
            Dim(id="radius_big", kind="radius", value=r1, view="front"),
            Dim(id="radius_small", kind="radius", value=r2, view="front"),
            Dim(id="distance", kind="linear", value=i["distance"], view="front"),
            Dim(id="thickness", kind="linear", value=i["thickness"], view="top"),
        ),
        title={"part": i["part"], "material": i["material"], "scale": scale},
        scale=scale,
        finish={"bore_big": i["roughness"]["bore_big"], "bore_small": i["roughness"]["bore_small"]},
    )


def draw(inputs: dict, layout: int = 0) -> Drawing:
    i = resolve(inputs)
    doc = new_sheet()
    msp = doc.modelspace()
    frame(doc, {"part": i["part"], "material": i["material"], "scale": _scale(i)[1]})
    stage, final, f = draft_boxes(_sizes(i), layout)
    box = stage
    r1, r2 = _r(i)
    dist = i["distance"]

    fx, fy, w, h = box["front"]
    cy = fy + max(r1, r2)
    c1 = (fx + r1, cy)
    c2 = (fx + w - r2, cy)
    for c, r, b in ((c1, r1, i["bore_big"]), (c2, r2, i["bore_small"])):
        circle(msp, c, 2 * r)
        circle(msp, c, b)
        cross(msp, c, r, r)
    # outer tangents between the two boss circles
    if dist > abs(r1 - r2):
        a = math.asin((r1 - r2) / dist)
        for sgn in (1, -1):
            th = sgn * (math.pi / 2 + a)
            p1 = (c1[0] + r1 * math.cos(th), c1[1] + r1 * math.sin(th))
            p2 = (c2[0] + r2 * math.cos(th), c2[1] + r2 * math.sin(th))
            msp.add_line(p1, p2, dxfattribs={"layer": "outline"})

    up = 1 if layout % 2 == 0 else -1
    hdim(msp, c1, c2, fy + h + 10 / f if up > 0 else fy - 10 / f)
    ddim(
        msp,
        c1,
        i["bore_big"],
        90 if up < 0 else 270,
        "<>" + (deviations(i["bore_big_fit"], i["bore_big"]) if inputs.get("calc") else i["bore_big_fit"]),
        location=(c1[0], c1[1] - up * (r1 + 26 / f)),
    )
    ddim(
        msp,
        c2,
        i["bore_small"],
        90 if up < 0 else 270,
        "<>" + (deviations(i["bore_small_fit"], i["bore_small"]) if inputs.get("calc") else i["bore_small_fit"]),
        location=(c2[0], c2[1] - up * (r2 + 40 / f)),
    )
    rdim(msp, c1, r1, 150, "<>", location=(c1[0] - r1 - 14 / f, fy + h + 24 / f))
    rdim(msp, c2, r2, 30, "<>", location=(c2[0] + r2, fy + h + 24 / f))

    tx, ty, tw, th = box["top"]
    msp.add_lwpolyline(
        [(tx, ty), (tx + tw, ty), (tx + tw, ty + th), (tx, ty + th)], close=True, dxfattribs={"layer": "outline"}
    )
    msp.add_line((tx, ty + th / 2), (tx + tw, ty + th / 2), dxfattribs={"layer": "center"})
    vdim(msp, (tx, ty), (tx, ty + th), tx - 12 / f)

    if f != 1.0:
        rescale(doc, stage, final)
    roughness_marks(doc, truth(inputs))
    return doc
