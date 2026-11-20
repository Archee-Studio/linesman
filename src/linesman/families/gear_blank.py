"""A spur gear blank: tip diameter from module and teeth, face width, hub, fitted bore with keyway.

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
    new_sheet,
    notched_circle,
    rescale,
    roughness_marks,
    scale_name,
    section_label,
    vdim,
)
from .keys import key

NAME = "gear-blank"
MAX_TIP = 300.0


def tip_diameter(module: float, teeth: int) -> float:
    """d_a = m (z + 2)"""
    return round(module * (teeth + 2), 3)


def sample(seed: int) -> dict:
    rng = random.Random(seed)
    module = rng.choice([2.0, 2.5, 3.0, 4.0])
    teeth = rng.choice([z for z in range(20, 79) if tip_diameter(module, z) <= MAX_TIP])
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
        "roughness": {"bore": 1.6},
    }


def calc(seed: int) -> dict:
    """Calc-level inputs: the keyway comes from DIN 6885 by bore diameter and the bore fit must be shown as
    limit deviations."""
    i = sample(seed)
    return {**i, "calc": True}


def resolve(inputs: dict) -> dict:
    return inputs


def _key(inputs: dict) -> dict[str, float]:
    return key(inputs["bore"])


def _length(i: dict) -> float:
    return i["face_width"] + i["hub_extension"]


def _sizes(i: dict) -> dict[str, tuple[float, float]]:
    tip = tip_diameter(i["module"], i["teeth"])
    return {"front": (_length(i), tip), "left": (tip, tip)}


def _scale(inputs: dict) -> tuple[float, str]:
    _, _, f = draft_boxes(_sizes(resolve(inputs)), 0)
    return f, scale_name(f)


def request(inputs: dict) -> str:
    i, k, scale = inputs, _key(inputs), _scale(inputs)[1]
    keyway = (
        "a DIN 6885 keyway for its bore diameter"
        if i.get("calc")
        else f"a keyway {k['b']:g} mm wide, hub depth t2 = {k['t2']:g} mm (DIN 6885)"
    )
    fit = "with its limit deviations" if i.get("calc") else "designation"
    return (
        f"Draw an A3 detail sheet of the {i['part'].lower()} at {scale} in first-angle projection with a front view "
        f"drawn as the full section A-A and a left view of the end face; label the section A-A (cut along the axis, "
        f"clear of the keyway); material "
        f"{i['material']}. Module {i['module']:g}, {i['teeth']} teeth: the blank is turned to the tip diameter "
        f"d_a = m (z + 2). Face width {i['face_width']:g} mm; the hub stands {i['hub_extension']:g} mm proud of "
        f"the rim on the viewer's side, hub diameter {i['hub']:g} mm. Bore {i['bore']:g} {i['bore_fit']} with "
        f"{keyway}: dimension its depth as d + t2 on the end view. Dimension every feature; show the fit on the "
        f"bore {fit}; mark the bore surface Ra 1.6; fill the title block with part, material and scale."
    )


def views(inputs: dict, layout: int = 0) -> dict[str, Box]:
    return draft_boxes(_sizes(resolve(inputs)), layout)[1]


def truth(inputs: dict) -> Truth:
    i, k, scale = resolve(inputs), _key(inputs), _scale(inputs)[1]
    tip = tip_diameter(i["module"], i["teeth"])
    b, ext = i["face_width"], i["hub_extension"]
    hatch_area = b * tip + ext * i["hub"] - (b + ext) * i["bore"]
    fit_form = "deviations" if inputs.get("calc") else "any"
    return Truth(
        views=(
            View(name="front", width=_length(i), height=tip, hatch_area=hatch_area),
            View(name="left", width=tip, height=tip),
        ),
        dims=(
            Dim(id="tip", kind="diameter", value=tip, view="front"),
            Dim(id="hub", kind="diameter", value=i["hub"], view="front"),
            Dim(id="bore", kind="diameter", value=i["bore"], view="front", fit=i["bore_fit"], fit_form=fit_form),
            Dim(id="keyway_width", kind="linear", value=k["b"], view="left"),
            Dim(id="keyway_depth", kind="linear", value=round(i["bore"] + k["t2"], 3), view="left"),
            Dim(id="face_width", kind="linear", value=b, view="front"),
            Dim(id="length", kind="linear", value=_length(i), view="front"),
        ),
        title={"part": i["part"], "material": i["material"], "scale": scale},
        scale=scale,
        finish=i["roughness"],
    )


def draw(inputs: dict, layout: int = 0) -> Drawing:
    i, k = resolve(inputs), _key(inputs)
    doc = new_sheet()
    msp = doc.modelspace()
    scale = _scale(i)[1]
    frame(doc, {"part": i["part"], "material": i["material"], "scale": scale})
    stage, final, f = draft_boxes(_sizes(i), layout)
    box = stage
    tip, hub, bore = tip_diameter(i["module"], i["teeth"]), i["hub"], i["bore"]

    lx, ly, w, h = box["front"]  # the axial profile, sectioned
    cy, b, ext = ly + tip / 2, i["face_width"], i["hub_extension"]
    outer = [
        (lx, ly),
        (lx + b, ly),
        (lx + b, cy - hub / 2),
        (lx + w, cy - hub / 2),
        (lx + w, cy + hub / 2),
        (lx + b, cy + hub / 2),
        (lx + b, ly + h),
        (lx, ly + h),
    ]
    msp.add_lwpolyline(outer, close=True, dxfattribs={"layer": "outline"})
    channel = [(lx, cy - bore / 2), (lx + w, cy - bore / 2), (lx + w, cy + bore / 2), (lx, cy + bore / 2)]
    msp.add_lwpolyline(channel, close=True, dxfattribs={"layer": "outline"})
    hatch(msp, outer, channel)
    msp.add_line((lx, cy), (lx + w, cy), dxfattribs={"layer": "center"})

    up = 1 if layout % 2 == 0 else -1
    edge = cy + up * tip / 2
    hdim(msp, (lx, edge), (lx + b, edge), edge + up * 15)
    hdim(msp, (lx, cy - up * tip / 2), (lx + w, cy - up * hub / 2), cy - up * (tip / 2 + 15))
    bore_text = f"%%c<>{deviations(i['bore_fit'], bore)}" if inputs.get("calc") else f"%%c<>{i['bore_fit']}"
    vdim(msp, (lx + b / 2, ly), (lx + b / 2, ly + h), lx - 12, "%%c<>")
    vdim(msp, (lx + w / 2, cy - bore / 2), (lx + w / 2, cy + bore / 2), lx - 24, bore_text)
    vdim(
        msp,
        (lx + b + ext / 2, cy - hub / 2),
        (lx + b + ext / 2, cy + hub / 2),
        lx + w + 12,
        "%%c<>",
    )

    gx, gy, _, _ = box["left"]  # the end face
    c = (gx + tip / 2, gy + tip / 2)
    circle(msp, c, tip)
    circle(msp, c, hub)
    notched_circle(msp, c, bore, k["b"], bore / 2 + k["t2"])
    cross(msp, c, tip / 2, tip / 2)
    side = 1 if layout % 2 == 0 else -1
    top = c[1] + tip / 2
    hdim(msp, (c[0] - k["b"] / 2, c[1] + bore / 2 + k["t2"]), (c[0] + k["b"] / 2, c[1] + bore / 2 + k["t2"]), top + 12)
    vdim(msp, (c[0] + k["b"] / 2, c[1] + bore / 2 + k["t2"]), (c[0], c[1] - bore / 2), c[0] + side * (tip / 2 + 15))

    if f != 1.0:
        rescale(doc, stage, final)
    section_label(msp, final["front"])
    roughness_marks(doc, truth(inputs))
    return doc
