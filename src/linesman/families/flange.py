"""A round flange with a spigot, a fitted bore and bolt holes on a pitch circle: front and left views."""

import math
import random

from ezdxf.document import Drawing

from ..schema import Dim, Truth, View
from .drafting import Box, circle, cross, ddim, frame, hdim, line, mirror, new_sheet, place, polar, rect

NAME = "flange"
# outside diameter, pitch circle diameter, holes, hole diameter (PN 10 style flanges, small sizes)
SIZES = (
    (90, 65, 4, 9.0),
    (100, 75, 4, 9.0),
    (110, 80, 4, 11.0),
    (120, 90, 6, 11.0),
    (130, 100, 6, 11.0),
    (140, 105, 6, 14.0),
    (150, 110, 8, 14.0),
)


def sample(seed: int) -> dict:
    rng = random.Random(seed)
    od, pcd, holes, hole = rng.choice(SIZES)
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
    }


def request(inputs: dict) -> str:
    i = inputs
    return (
        f"Draw an A3 detail sheet of the {i['part'].lower()} at 1:1 in first-angle projection with a front view of the "
        f"circular face (spigot towards the viewer) and a left view. Material {i['material']}. Outside diameter "
        f"{i['od']:g} mm, flange thickness {i['thickness']:g} mm. Spigot diameter {i['spigot']:g} mm, "
        f"{i['spigot_length']:g} mm long. Central bore {i['bore']:g} {i['bore_fit']}. {i['holes']} through holes "
        f"{i['hole']:g} mm on a {i['pcd']:g} mm pitch circle, equally spaced. Dimension every feature; show the fit "
        "on the bore; fill the title block with part, material and scale."
    )


def views(inputs: dict, layout: int = 0) -> dict[str, Box]:
    i = inputs
    return place({"front": (i["od"], i["od"]), "left": (i["thickness"] + i["spigot_length"], i["od"])}, layout)


def truth(inputs: dict) -> Truth:
    i = inputs
    return Truth(
        views=(
            View(name="front", width=i["od"], height=i["od"]),
            View(name="left", width=i["thickness"] + i["spigot_length"], height=i["od"]),
        ),
        dims=(
            Dim(id="od", kind="diameter", value=i["od"], view="front"),
            Dim(id="pcd", kind="diameter", value=i["pcd"], view="front"),
            Dim(id="hole", kind="diameter", value=i["hole"], view="front"),
            Dim(id="bore", kind="diameter", value=i["bore"], view="front", fit=i["bore_fit"]),
            Dim(id="spigot", kind="diameter", value=i["spigot"], view="front"),
            Dim(id="thickness", kind="linear", value=i["thickness"], view="left"),
            Dim(id="spigot_length", kind="linear", value=i["spigot_length"], view="left"),
        ),
        title={"part": i["part"], "material": i["material"], "scale": "1:1"},
    )


def draw(inputs: dict, layout: int = 0) -> Drawing:
    i = inputs
    doc = new_sheet()
    msp = doc.modelspace()
    frame(doc, {"part": i["part"], "material": i["material"], "scale": "1:1"})
    box = views(i, layout)
    od, pcd, n = i["od"], i["pcd"], i["holes"]
    fx, fy, _, _ = box["front"]
    c = (fx + od / 2, fy + od / 2)
    for d in (od, i["spigot"], i["bore"]):
        circle(msp, c, d)
    circle(msp, c, pcd, "center")
    cross(msp, c, od / 2, od / 2)
    start = 45.0 if n == 4 else 90.0
    angles = [start + 360.0 * k / n for k in range(n)]
    for a in angles:
        circle(msp, polar(c, pcd / 2, a), i["hole"])
    out = od / 2 + 12
    ddim(msp, c, od, mirror(30, layout), location=polar(c, out, mirror(30, layout)))
    ddim(msp, c, pcd, mirror(75, layout), location=polar(c, out, mirror(75, layout)), text="<>")
    ddim(msp, c, i["spigot"], mirror(120, layout), location=polar(c, out, mirror(120, layout)))
    ddim(
        msp,
        c,
        i["bore"],
        mirror(150, layout),
        location=polar(c, out, mirror(150, layout)),
        text="<>" + i["bore_fit"],
    )
    hole_at = polar(c, pcd / 2, angles[0])
    ddim(msp, hole_at, i["hole"], angles[0], f"{n}x <>", location=polar(hole_at, 24, angles[0] + 45))

    lx, ly, w, h = box["left"]
    cy, t, ls = ly + od / 2, i["thickness"], i["spigot_length"]
    rect(msp, lx, ly, t, od)
    rect(msp, lx + t, cy - i["spigot"] / 2, ls, i["spigot"])
    for y in (i["bore"] / 2, -i["bore"] / 2):
        line(msp, (lx, cy + y), (lx + w, cy + y), "hidden")
    for y in sorted({round(pcd / 2 * math.sin(math.radians(a)), 6) for a in angles}):
        for dy in (-i["hole"] / 2, i["hole"] / 2):
            line(msp, (lx, cy + y + dy), (lx + t, cy + y + dy), "hidden")
    line(msp, (lx, cy), (lx + w, cy), "center")
    up = 1 if layout % 2 == 0 else -1
    edge = cy + up * od / 2
    hdim(msp, (lx, edge), (lx + t, edge), edge + up * 12)
    hdim(msp, (lx + t, cy + up * i["spigot"] / 2), (lx + w, cy + up * i["spigot"] / 2), edge + up * 12)
    return doc
