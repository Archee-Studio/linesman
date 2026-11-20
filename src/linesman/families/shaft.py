"""A stepped shaft: bearing seats with shaft fits, a keyway on the left end, front view and left end view.

Calc level: step-1 diameter is the smallest of a stated series not below cbrt(16 T / (pi tau)); the keyway
comes from DIN 6885 by that diameter; the step-1 fit must be shown as limit deviations.
"""

import random

from ezdxf.document import Drawing

from .. import din471
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
    line,
    new_sheet,
    notched_circle,
    rect,
    rescale,
    roughness_marks,
    scale_name,
    vdim,
)
from .keys import KEY_LENGTHS, key

NAME = "shaft"
ROLES = {3: ("key", "shoulder", "bearing"), 4: ("key", "bearing", "shoulder", "bearing")}
ROLES[5] = ("key", "bearing", "shoulder", "bearing", "end")
LENGTHS = {
    "key": (30, 35, 40, 45, 50, 90, 120, 150, 200),
    "bearing": (20, 25, 30, 40, 60, 90),
    "shoulder": (10, 12, 15, 20, 40),
    "end": (20, 25, 30, 50, 80),
}
SERIES = (18, 20, 22, 25, 28, 30, 32, 35, 38, 40)  # stated preferred diameters for the calc rule


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
    inputs = {
        "part": "Stepped shaft",
        "material": rng.choice(["C45", "42CrMo4", "34CrNiMo6"]),
        "steps": steps,
        "keyway": {"width": k["b"], "t1": k["t1"], "length": float(length), "start": 4.0},
    }
    if rng.random() < 0.4:
        inputs["groove"] = din471.groove(diameter["end"]) | {"step": len(steps)}  # DIN 471 ring groove on the last step
    inputs["roughness"] = {f"d{n}": 0.8 for n, s in enumerate(steps, 1) if s["role"] == "bearing"}
    return inputs


def calc(seed: int) -> dict:
    """Calc-level inputs: torque, allowable shear stress and the preferred series in place of the step-1
    diameter; every other step is its delta over step 1."""
    i = sample(seed)
    need = i["steps"][0]["diameter"] - 1.5  # inside (previous series value, chosen]
    tau = 40.0  # MPa
    torque = round(tau * 3.141592653589793 * need**3 / 16 / 1000, 1)  # Nm; cbrt(16 T / pi tau) in mm needs Nmm
    steps = [
        {
            "role": s["role"],
            "delta": s["diameter"] - i["steps"][0]["diameter"],
            "length": s["length"],
            "fit": s["fit"],
        }
        for s in i["steps"]
    ]
    out = {
        "part": i["part"],
        "material": i["material"],
        "torque": torque,
        "tau": tau,
        "series": SERIES,
        "steps": steps,
        "keyway": {"length": i["keyway"]["length"], "start": i["keyway"]["start"]},
        "roughness": i["roughness"],
        "calc": True,
    }
    if "groove" in i:
        out["groove"] = i["groove"]
    return out


def resolve(inputs: dict) -> dict:
    """Requirement inputs (calc) expanded to the full given values."""
    if not inputs.get("calc"):
        return inputs
    need = (16 * inputs["torque"] * 1000 / (3.141592653589793 * inputs["tau"])) ** (1 / 3)
    d_key = min(d for d in inputs["series"] if d >= need - 1e-9)
    steps = [{**s, "diameter": d_key + s["delta"]} for s in inputs["steps"]]
    k = key(d_key)
    out = {
        "part": inputs["part"],
        "material": inputs["material"],
        "steps": steps,
        "keyway": {
            "width": k["b"],
            "t1": k["t1"],
            "length": inputs["keyway"]["length"],
            "start": inputs["keyway"]["start"],
        },
        "roughness": inputs["roughness"],
    }
    if "groove" in inputs:
        out["groove"] = inputs["groove"]
    return out


def _total(i: dict) -> float:
    return sum(s["length"] for s in i["steps"])


def _dmax(i: dict) -> float:
    return max(s["diameter"] for s in i["steps"])


def _sizes(i: dict) -> dict[str, tuple[float, float]]:
    return {"front": (_total(i), _dmax(i)), "left": (_dmax(i), _dmax(i))}


def _scale(inputs: dict) -> tuple[float, str]:
    _, _, f = draft_boxes(_sizes(resolve(inputs)), 0)
    return f, scale_name(f)


def request(inputs: dict) -> str:
    i, scale = inputs, _scale(inputs)[1]
    lines = []
    if i.get("calc"):
        first = (
            f"step 1 (keyway seat) is the smallest diameter of the series {', '.join(str(s) for s in i['series'])} "
            f"that is not below cbrt(16 T / (pi tau)) for T = {i['torque']:g} Nm and tau = {i['tau']:g} MPa, "
            f"fit {i['steps'][0]['fit']} shown with its limit deviations"
        )
        lines.append(first)
        for n, s in list(enumerate(i["steps"], 1))[1:]:
            what = {"key": "keyway seat", "bearing": "bearing seat", "shoulder": "shoulder", "end": "plain end"}[
                s["role"]
            ]
            fit = f" {s['fit']}" if s["fit"] else ""
            lines.append(f"step {n} ({what}) diameter {s['delta']:+g} over step 1{fit}, length {s['length']:g}")
        keyway = (
            f"the keyway in step 1 is a DIN 6885 parallel key for the step diameter, {i['keyway']['length']:g} mm "
            f"long, starting {i['keyway']['start']:g} mm from the left end: dimension its depth as d - t1 on the "
            "end view"
        )
    else:
        for n, s in enumerate(i["steps"], 1):
            fit = f" {s['fit']}" if s["fit"] else ""
            what = {"key": "keyway seat", "bearing": "bearing seat", "shoulder": "shoulder", "end": "plain end"}[
                s["role"]
            ]
            lines.append(f"step {n} ({what}) diameter {s['diameter']:g}{fit}, length {s['length']:g}")
        k = i["keyway"]
        keyway = (
            f"the keyway in step 1 is {k['width']:g} mm wide and {k['length']:g} mm long, starting {k['start']:g} mm "
            f"from the left end, shaft depth t1 = {k['t1']:g} mm (DIN 6885): dimension its depth as d - t1 on the "
            "end view"
        )
    total = _total(resolve(i))
    groove = ""
    if "groove" in i:
        g = i["groove"]
        groove = (
            f" The last step carries a DIN 471 retaining-ring groove, floor {g['d2']:g} mm diameter, "
            f"{g['m']:g} mm wide, 3 mm from the step's right end."
        )
    return (
        f"Draw an A3 detail sheet of the {i['part'].lower()} at {scale} in first-angle projection with a front "
        f"view and a left end view. Material {i['material']}, overall length {total:g} mm, steps from the left: "
        + "; ".join(lines)
        + f". {keyway}.{groove} Dimension every step diameter with its fit, every step length and the overall "
        "length; mark every bearing seat surface Ra 0.8; fill the title block with part, material and scale."
    )


def views(inputs: dict, layout: int = 0) -> dict[str, Box]:
    return draft_boxes(_sizes(resolve(inputs)), layout)[1]


def truth(inputs: dict) -> Truth:
    i = resolve(inputs)
    scale = _scale(inputs)[1]
    k = i["keyway"]
    d_key = i["steps"][0]["diameter"]
    d = _dmax(i)
    dims = []
    for n, s in enumerate(i["steps"], 1):
        fit_form = "deviations" if inputs.get("calc") and n == 1 else "any"
        dims.append(
            Dim(id=f"d{n}", kind="diameter", value=s["diameter"], view="front", fit=s["fit"], fit_form=fit_form)
        )
        dims.append(Dim(id=f"l{n}", kind="linear", value=s["length"], view="front"))
    dims += [
        Dim(id="length", kind="linear", value=_total(i), view="front"),
        Dim(id="keyway_length", kind="linear", value=k["length"], view="front"),
        Dim(id="keyway_width", kind="linear", value=k["width"], view="left"),
        Dim(id="keyway_depth", kind="linear", value=round(d_key - k["t1"], 3), view="left"),
    ]
    if "groove" in i:
        g = i["groove"]
        dims += [
            Dim(id="groove_d", kind="diameter", value=g["d2"], view="front"),
            Dim(id="groove_w", kind="linear", value=g["m"], view="front"),
        ]
    seen, reach, left_hidden = set(), 0.0, False
    for st in i["steps"]:
        d_step = st["diameter"]
        if d_step in seen:
            continue
        seen.add(d_step)
        left_hidden = left_hidden or d_step <= reach  # drawn dashed, like draw() does
        reach = max(reach, d_step)
    return Truth(
        views=(
            View(name="front", width=_total(i), height=d, hidden=True),
            View(name="left", width=d, height=d, hidden=left_hidden),
        ),
        dims=tuple(dims),
        title={"part": i["part"], "material": i["material"], "scale": scale},
        scale=scale,
        finish=i["roughness"],
    )


def draw(inputs: dict, layout: int = 0) -> Drawing:
    i = resolve(inputs)
    k = i["keyway"]
    doc = new_sheet()
    msp = doc.modelspace()
    scale = _scale(inputs)[1]
    frame(doc, {"part": i["part"], "material": i["material"], "scale": scale})
    stage, final, f = draft_boxes(_sizes(i), layout)
    box = stage
    steps, big, total = i["steps"], _dmax(i), _total(i)
    fx, fy, _, _ = box["front"]
    cy = fy + big / 2
    xs = [0.0]
    for s in steps:
        xs.append(xs[-1] + s["length"])
    groove = i.get("groove")
    g_step = groove["step"] if groove else -1
    top = [(fx, cy + steps[0]["diameter"] / 2)]
    for n, s in enumerate(steps):
        y = cy + s["diameter"] / 2
        if n + 1 == g_step:
            gx0 = fx + xs[n + 1] - 3.0 - groove["m"]
            top += [
                (gx0, y),
                (gx0, cy + groove["d2"] / 2),
                (gx0 + groove["m"], cy + groove["d2"] / 2),
                (gx0 + groove["m"], y),
            ]
        top.append((fx + xs[n + 1], y))
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
        text = "<>" + (deviations(s["fit"], s["diameter"]) if inputs.get("calc") and n == 0 else (s["fit"] or ""))
        ddim(
            msp,
            (xc, cy),
            s["diameter"],
            90 if up < 0 else 270,
            text,
            location=(xc, cy - up * (big / 2 + ((32 if inputs.get("calc") else 14) + 16 * (n % 2)) / f)),
        )
    hdim(
        msp,
        (fx + k["start"], cy - up * d_key / 2),
        (fx + k["start"] + k["length"], cy - up * d_key / 2),
        cy - up * (big / 2 + 30 / f),
    )
    if groove:
        gx0 = fx + xs[g_step - 1] + steps[g_step - 1]["length"] - 3.0 - groove["m"]
        y = cy + up * steps[g_step - 1]["diameter"] / 2
        hdim(msp, (gx0, y), (gx0 + groove["m"], y), cy - up * (big / 2 + 64 / f))
        xc = gx0 + groove["m"] / 2
        ddim(msp, (xc, cy), groove["d2"], 90 if up < 0 else 270, "<>", location=(xc, cy - up * (big / 2 + 78 / f)))

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
        (c[0] + k["width"] / 2, c[1] + d_key / 2 - k["t1"]),
        c[1] + big / 2 + 12,
    )
    side = 1 if layout % 2 == 0 else -1
    vdim(
        msp, (c[0] + k["width"] / 2, c[1] + d_key / 2 - k["t1"]), (c[0], c[1] - d_key / 2), c[0] + side * (big / 2 + 15)
    )
    if f != 1.0:
        rescale(doc, stage, final)
    roughness_marks(doc, truth(inputs))
    return doc
