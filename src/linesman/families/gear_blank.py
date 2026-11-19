"""A spur gear blank: tip diameter from module and teeth, face width, hub, fitted bore with keyway."""

import random

from ezdxf.document import Drawing

from ..schema import Dim, Truth, View
from .drafting import Box, circle, cross, ddim, frame, hdim, line, mirror, new_sheet, notched_circle, place, polar, vdim
from .keys import key

NAME = "gear-blank"
MAX_TIP = 150.0


def tip_diameter(module: float, teeth: int) -> float:
    """d_a = m (z + 2)"""
    return round(module * (teeth + 2), 3)


def sample(seed: int) -> dict:
    rng = random.Random(seed)
    module = rng.choice([2.0, 2.5, 3.0, 4.0])
    teeth = rng.choice([z for z in range(20, 61) if tip_diameter(module, z) <= MAX_TIP])
    root = module * (teeth - 2.5)
    hub_of = {b: -(-b * 18 // 50) * 5.0 for b in (12, 16, 20, 25, 30, 35, 40)}  # about 1.8 d, up to a multiple of 5
    bore = rng.choice([b for b, hub in hub_of.items() if hub <= root - 4 * module])
    return {
        "part": "Spur gear blank",
        "material": rng.choice(["C45", "16MnCr5", "42CrMo4"]),
        "module": module,
        "teeth": teeth,
        "face_width": float(round(module * rng.choice([8, 10, 12]))),
        "bore": float(bore),
        "bore_fit": "H7",
        "hub": hub_of[bore],
        "hub_extension": float(rng.choice([8, 10, 12])),
    }


def _key(inputs: dict) -> dict[str, float]:
    return key(inputs["bore"])


def request(inputs: dict) -> str:
    i, k = inputs, _key(inputs)
    return (
        f"Draw an A3 detail sheet of the {i['part'].lower()} at 1:1 in first-angle projection with a front view and "
        f"a left view. Material {i['material']}. Module {i['module']:g}, {i['teeth']} teeth: the blank is turned to "
        f"the tip diameter d_a = m (z + 2). Face width {i['face_width']:g} mm; the hub stands "
        f"{i['hub_extension']:g} mm proud of the rim on the viewer's side, hub diameter {i['hub']:g} mm. Bore "
        f"{i['bore']:g} {i['bore_fit']} with a through keyway {k['b']:g} mm wide, hub depth t2 = {k['t2']:g} mm "
        f"(DIN 6885): dimension its depth as d + t2. Dimension every feature; show the fit on the bore; fill the "
        "title block with part, material and scale."
    )


def _length(inputs: dict) -> float:
    return inputs["face_width"] + inputs["hub_extension"]


def views(inputs: dict, layout: int = 0) -> dict[str, Box]:
    tip = tip_diameter(inputs["module"], inputs["teeth"])
    return place({"front": (tip, tip), "left": (_length(inputs), tip)}, layout)


def truth(inputs: dict) -> Truth:
    i, k = inputs, _key(inputs)
    tip = tip_diameter(i["module"], i["teeth"])
    return Truth(
        views=(View(name="front", width=tip, height=tip), View(name="left", width=_length(i), height=tip)),
        dims=(
            Dim(id="tip", kind="diameter", value=tip, view="front"),
            Dim(id="hub", kind="diameter", value=i["hub"], view="front"),
            Dim(id="bore", kind="diameter", value=i["bore"], view="front", fit=i["bore_fit"]),
            Dim(id="keyway_width", kind="linear", value=k["b"], view="front"),
            Dim(id="keyway_depth", kind="linear", value=round(i["bore"] + k["t2"], 3), view="front"),
            Dim(id="face_width", kind="linear", value=i["face_width"], view="left"),
            Dim(id="length", kind="linear", value=_length(i), view="left"),
        ),
        title={"part": i["part"], "material": i["material"], "scale": "1:1"},
    )


def draw(inputs: dict, layout: int = 0) -> Drawing:
    i, k = inputs, _key(inputs)
    doc = new_sheet()
    msp = doc.modelspace()
    frame(doc, {"part": i["part"], "material": i["material"], "scale": "1:1"})
    box = views(i, layout)
    tip, hub, bore = tip_diameter(i["module"], i["teeth"]), i["hub"], i["bore"]
    fx, fy, _, _ = box["front"]
    c = (fx + tip / 2, fy + tip / 2)
    circle(msp, c, tip)
    circle(msp, c, hub)
    notched_circle(msp, c, bore, k["b"], bore / 2 + k["t2"])
    cross(msp, c, tip / 2, tip / 2)
    side = 1 if layout % 2 == 0 else -1
    out = tip / 2 + 12
    for d, angle, text in ((tip, 35, "<>"), (hub, 70, "<>"), (bore, 145, "<>" + i["bore_fit"])):
        ddim(msp, c, d, mirror(angle, layout), text, location=polar(c, out, mirror(angle, layout)))
    top = c[1] + tip / 2
    hdim(msp, (c[0] - k["b"] / 2, c[1] + bore / 2 + k["t2"]), (c[0] + k["b"] / 2, c[1] + bore / 2 + k["t2"]), top + 12)
    vdim(msp, (c[0] + k["b"] / 2, c[1] + bore / 2 + k["t2"]), (c[0], c[1] - bore / 2), c[0] + side * (tip / 2 + 15))

    lx, ly, _, _ = box["left"]
    cy, b, ext = ly + tip / 2, i["face_width"], i["hub_extension"]
    pts = [(0, -tip / 2), (b, -tip / 2), (b, -hub / 2), (b + ext, -hub / 2), (b + ext, hub / 2), (b, hub / 2)]
    pts += [(b, tip / 2), (0, tip / 2)]
    msp.add_lwpolyline([(lx + x, cy + y) for x, y in pts], close=True, dxfattribs={"layer": "outline"})
    for y in (bore / 2, -bore / 2, bore / 2 + k["t2"]):
        line(msp, (lx, cy + y), (lx + b + ext, cy + y), "hidden")
    line(msp, (lx, cy), (lx + b + ext, cy), "center")
    up = 1 if layout % 2 == 0 else -1
    hdim(msp, (lx, cy + up * tip / 2), (lx + b, cy + up * tip / 2), cy + up * (tip / 2 + 12))
    hdim(msp, (lx, cy - up * tip / 2), (lx + b + ext, cy - up * hub / 2), cy - up * (tip / 2 + 12))
    return doc
