"""A press-fit sleeve: fitted outside and inside diameters, length and 45 degree chamfers; front and left views."""

import random

from ezdxf.document import Drawing

from ..schema import Dim, Truth, View
from .drafting import Box, circle, cross, ddim, frame, hdim, line, mirror, new_sheet, place, polar

NAME = "bushing"


def sample(seed: int) -> dict:
    rng = random.Random(seed)
    bore = rng.choice([20, 25, 30, 35, 40, 50])
    return {
        "part": "Bushing",
        "material": rng.choice(["CuSn8", "C45", "16MnCr5"]),
        "bore": float(bore),
        "bore_fit": rng.choice(["H7", "F7"]),
        "od": float(bore + 2 * rng.choice([5, 6, 8, 10])),
        "od_fit": rng.choice(["p6", "s6"]),
        "length": float(rng.choice([25, 30, 40, 50, 60, 70])),
        "chamfer": rng.choice([0.5, 1.0, 1.5]),
    }


def request(inputs: dict) -> str:
    i = inputs
    return (
        f"Draw an A3 detail sheet of the {i['part'].lower()} at 1:1 in first-angle projection with a front view of "
        f"the end face and a left view. Material {i['material']}. Outside diameter {i['od']:g} {i['od_fit']} "
        f"(press fit), bore {i['bore']:g} {i['bore_fit']}, length {i['length']:g} mm. Chamfer "
        f"{i['chamfer']:g} x 45 degrees on all four edges. Dimension every feature; show both fits; fill the title "
        "block with part, material and scale."
    )


def views(inputs: dict, layout: int = 0) -> dict[str, Box]:
    i = inputs
    return place({"front": (i["od"], i["od"]), "left": (i["length"], i["od"])}, layout)


def truth(inputs: dict) -> Truth:
    i = inputs
    return Truth(
        views=(
            View(name="front", width=i["od"], height=i["od"]),
            View(name="left", width=i["length"], height=i["od"]),
        ),
        dims=(
            Dim(id="od", kind="diameter", value=i["od"], view="front", fit=i["od_fit"]),
            Dim(id="bore", kind="diameter", value=i["bore"], view="front", fit=i["bore_fit"]),
            Dim(id="length", kind="linear", value=i["length"], view="left"),
            Dim(id="chamfer", kind="linear", value=i["chamfer"], view="left"),
        ),
        title={"part": i["part"], "material": i["material"], "scale": "1:1"},
    )


def draw(inputs: dict, layout: int = 0) -> Drawing:
    i = inputs
    doc = new_sheet()
    msp = doc.modelspace()
    frame(doc, {"part": i["part"], "material": i["material"], "scale": "1:1"})
    box = views(i, layout)
    od, bore, length, c = i["od"], i["bore"], i["length"], i["chamfer"]
    fx, fy, _, _ = box["front"]
    centre = (fx + od / 2, fy + od / 2)
    for d in (od, od - 2 * c, bore, bore + 2 * c):
        circle(msp, centre, d)
    cross(msp, centre, od / 2, od / 2)
    out = od / 2 + 12
    ddim(msp, centre, od, mirror(40, layout), "<>" + i["od_fit"], location=polar(centre, out, mirror(40, layout)))
    ddim(msp, centre, bore, mirror(140, layout), "<>" + i["bore_fit"], location=polar(centre, out, mirror(140, layout)))

    lx, ly, _, _ = box["left"]
    cy, r = ly + od / 2, od / 2
    msp.add_lwpolyline(
        [
            (lx + c, cy - r),
            (lx + length - c, cy - r),
            (lx + length, cy - r + c),
            (lx + length, cy + r - c),
            (lx + length - c, cy + r),
            (lx + c, cy + r),
            (lx, cy + r - c),
            (lx, cy - r + c),
        ],
        close=True,
        dxfattribs={"layer": "outline"},
    )
    for x in (lx + c, lx + length - c):
        line(msp, (x, cy - r + c), (x, cy + r - c))
    for s in (1, -1):
        h = bore / 2
        msp.add_lwpolyline(
            [
                (lx, cy + s * (h + c)),
                (lx + c, cy + s * h),
                (lx + length - c, cy + s * h),
                (lx + length, cy + s * (h + c)),
            ],
            dxfattribs={"layer": "hidden"},
        )
    line(msp, (lx, cy), (lx + length, cy), "center")
    up = 1 if layout % 2 == 0 else -1
    edge = cy + up * r
    hdim(msp, (lx, edge - up * c), (lx + length, edge - up * c), edge + up * 15)
    hdim(msp, (lx, edge - up * c), (lx + c, edge - up * c), edge + up * 6)
    return doc
