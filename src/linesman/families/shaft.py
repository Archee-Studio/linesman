"""A stepped shaft: bearing seats with shaft fits, a keyway on the left end, front view and left end view."""

import random

from ezdxf.document import Drawing

from ..schema import Dim, Truth, View
from .drafting import (
    Box,
    circle,
    cross,
    ddim,
    frame,
    hdim,
    line,
    new_sheet,
    notched_circle,
    place,
    rect,
    vdim,
)
from .keys import KEY_LENGTHS, key

NAME = "shaft"
ROLES = {3: ("key", "shoulder", "bearing"), 4: ("key", "bearing", "shoulder", "bearing")}
ROLES[5] = ("key", "bearing", "shoulder", "bearing", "end")
LENGTHS = {"key": (30, 35, 40, 45, 50), "bearing": (20, 25, 30), "shoulder": (10, 12, 15, 20), "end": (20, 25, 30)}


def sample(seed: int) -> dict:
    rng = random.Random(seed)
    d_key = rng.choice([20, 25, 30, 35])
    diameter = {"key": d_key, "bearing": d_key + 5, "shoulder": d_key + 10, "end": d_key}
    fits = {"key": rng.choice(["k6", "m6"]), "bearing": None, "shoulder": None, "end": "js6"}
    steps = []
    for role in ROLES[rng.choice([3, 4, 5])]:
        fit = rng.choice(["k6", "m6", "js6"]) if role == "bearing" else fits[role]
        steps.append(
            {"role": role, "diameter": float(diameter[role]), "length": float(rng.choice(LENGTHS[role])), "fit": fit}
        )
    k = key(d_key)
    length = max(x for x in KEY_LENGTHS if x <= steps[0]["length"] - 8)
    return {
        "part": "Stepped shaft",
        "material": rng.choice(["C45", "42CrMo4", "34CrNiMo6"]),
        "steps": steps,
        "keyway": {"width": k["b"], "t1": k["t1"], "length": float(length), "start": 4.0},
    }


def request(inputs: dict) -> str:
    i, k = inputs, inputs["keyway"]
    lines = []
    for n, s in enumerate(i["steps"], 1):
        fit = f" {s['fit']}" if s["fit"] else ""
        what = {"key": "keyway seat", "bearing": "bearing seat", "shoulder": "shoulder", "end": "plain end"}[s["role"]]
        lines.append(f"step {n} ({what}) diameter {s['diameter']:g}{fit}, length {s['length']:g}")
    total = sum(s["length"] for s in i["steps"])
    return (
        f"Draw an A3 detail sheet of the {i['part'].lower()} at 1:1 in first-angle projection with a front view and "
        f"a left end view. Material {i['material']}, overall length {total:g} mm, steps from the left: "
        + "; ".join(lines)
        + f". The keyway in step 1 is {k['width']:g} mm wide and {k['length']:g} mm long, starting {k['start']:g} mm "
        f"from the left end, shaft depth t1 = {k['t1']:g} mm (DIN 6885): dimension its depth as d - t1 on the end "
        "view. Dimension every step diameter with its fit, every step length and the overall length; fill the title "
        "block with part, material and scale."
    )


def _total(inputs: dict) -> float:
    return sum(s["length"] for s in inputs["steps"])


def _dmax(inputs: dict) -> float:
    return max(s["diameter"] for s in inputs["steps"])


def views(inputs: dict, layout: int = 0) -> dict[str, Box]:
    d = _dmax(inputs)
    return place({"front": (_total(inputs), d), "left": (d, d)}, layout)


def truth(inputs: dict) -> Truth:
    i, k = inputs, inputs["keyway"]
    d_key = i["steps"][0]["diameter"]
    d = _dmax(i)
    dims = []
    for n, s in enumerate(i["steps"], 1):
        dims.append(Dim(id=f"d{n}", kind="diameter", value=s["diameter"], view="front", fit=s["fit"]))
        dims.append(Dim(id=f"l{n}", kind="linear", value=s["length"], view="front"))
    dims += [
        Dim(id="length", kind="linear", value=_total(i), view="front"),
        Dim(id="keyway_length", kind="linear", value=k["length"], view="front"),
        Dim(id="keyway_width", kind="linear", value=k["width"], view="left"),
        Dim(id="keyway_depth", kind="linear", value=round(d_key - k["t1"], 3), view="left"),
    ]
    return Truth(
        views=(View(name="front", width=_total(i), height=d), View(name="left", width=d, height=d)),
        dims=tuple(dims),
        title={"part": i["part"], "material": i["material"], "scale": "1:1"},
    )


def draw(inputs: dict, layout: int = 0) -> Drawing:
    i, k = inputs, inputs["keyway"]
    doc = new_sheet()
    msp = doc.modelspace()
    frame(doc, {"part": i["part"], "material": i["material"], "scale": "1:1"})
    box = views(i, layout)
    steps, big, total = i["steps"], _dmax(i), _total(i)
    fx, fy, _, _ = box["front"]
    cy = fy + big / 2
    xs = [0.0]
    for s in steps:
        xs.append(xs[-1] + s["length"])
    top = [(fx, cy + steps[0]["diameter"] / 2)]
    for n, s in enumerate(steps):
        top.append((fx + xs[n + 1], cy + s["diameter"] / 2))
        if n + 1 < len(steps):
            top.append((fx + xs[n + 1], cy + steps[n + 1]["diameter"] / 2))
    outline = top + [(x, 2 * cy - y) for x, y in reversed(top)]
    msp.add_lwpolyline(outline, close=True, dxfattribs={"layer": "outline"})
    line(msp, (fx, cy), (fx + total, cy), "center")
    d_key = steps[0]["diameter"]
    rect(msp, fx + k["start"], cy + d_key / 2 - k["t1"], k["length"], k["t1"], "hidden")

    up = 1 if layout % 2 == 0 else -1  # lengths on this side, diameters and the keyway length on the other
    edge = cy + up * big / 2
    for n in range(len(steps)):
        d_here = max(steps[n]["diameter"], steps[n + 1]["diameter"] if n + 1 < len(steps) else 0)
        hdim(
            msp,
            (fx + xs[n], cy + up * steps[n]["diameter"] / 2),
            (fx + xs[n + 1], cy + up * d_here / 2),
            edge + up * 15,
        )
    hdim(msp, (fx, cy + up * d_key / 2), (fx + total, cy + up * steps[-1]["diameter"] / 2), edge + up * 30)
    for n, s in enumerate(steps):
        xc = fx + (xs[n] + xs[n + 1]) / 2
        text = "<>" + (s["fit"] or "")
        ddim(msp, (xc, cy), s["diameter"], 90 if up < 0 else 270, text, location=(xc, cy - up * (big / 2 + 10)))
    hdim(
        msp,
        (fx + k["start"], cy - up * d_key / 2),
        (fx + k["start"] + k["length"], cy - up * d_key / 2),
        cy - up * (big / 2 + 30),
    )

    lx, ly, _, _ = box["left"]
    c = (lx + big / 2, ly + big / 2)
    cross(msp, c, big / 2, big / 2)
    seen: set[float] = set()
    reach = 0.0
    for s in steps:
        d = s["diameter"]
        if d in seen:
            continue
        seen.add(d)
        layer = "outline" if d > reach else "hidden"
        reach = max(reach, d)
        if d == d_key:
            notched_circle(msp, c, d, k["width"], d / 2 - k["t1"], layer)
        else:
            circle(msp, c, d, layer)
    hdim(
        msp,
        (c[0] - k["width"] / 2, c[1] + d_key / 2 - k["t1"]),
        (c[0] + k["width"] / 2, c[1] + d_key / 2),
        c[1] + big / 2 + 12,
    )
    side = 1 if layout % 2 == 0 else -1
    vdim(
        msp, (c[0] + k["width"] / 2, c[1] + d_key / 2 - k["t1"]), (c[0], c[1] - d_key / 2), c[0] + side * (big / 2 + 15)
    )
    return doc
