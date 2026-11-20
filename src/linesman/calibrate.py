"""Calibration: the benchmark proves its own checks before it scores anyone (AGENTS.md, docs/spec.md).

For every family and seed: the reference and its variants score 1 on every check; each mutant fails every check it
targets; the empty, title-block-only and copied-input sheets fail the task and average at most 0.2 over the content
parts (the gate is a precondition, not content). The review track is calibrated the same way: the seeded errors
as findings score 1, no findings score 0.
"""

import json
import random
import statistics
import tempfile
from collections import defaultdict
from pathlib import Path

import ezdxf
from ezdxf import bbox as ezbbox
from ezdxf.document import Drawing

from .checks.review import ReviewSheet
from .families import FAMILIES
from .families.drafting import A3, DIMSTYLE, frame, new_sheet, place, rect
from .grade import grade
from .mutate import MUTANTS, Skip, apply, roundtrip, seed_errors
from .regions import TOL, title_block
from .schema import Finding, Task, TaskResult, Truth
from .sheet import MM, load, parse

LAYOUTS = (0, 1, 2)
NEAR_ZERO = 0.2
SHOWN = 12  # failures printed in the table; the JSON report holds all of them
DEGENERATE = ("empty", "title-block-only", "copied-input", "boxes-and-floating-dims")

# Fairness variants: the same sheet written the other standard ways. Every one must score 1 on every check.
FAIR = ("attrib-title", "as-lines", "mtext", "named-linetypes", "split-section")

_ISO_LINETYPES = {
    "ACAD_ISO02W100": "A,1.27,-0.254",  # ISO dashed
    "ACAD_ISO04W100": "A,3.175,-0.635,0.635,-0.635",  # ISO long dash-dot (centre)
    "ACAD_ISO10W100": "A,5.08,-0.635,0.635,-0.635",  # ISO long dash-dot-dot (phantom)
}
_LINETYPE_RENAMES = {
    "DASHED": "ACAD_ISO02W100",
    "HIDDEN": "ACAD_ISO02W100",
    "DASHDOT": "ACAD_ISO10W100",
    "CENTER": "ACAD_ISO04W100",
    "PHANTOM": "ACAD_ISO10W100",
}


def _attrib_title(doc: Drawing, truth: Truth) -> Drawing:
    """Title-block values carried as ATTRIBs of an INSERT, the standard AutoCAD way."""
    sheet, msp = parse(doc), doc.modelspace()
    box = title_block(sheet)
    if box is None:
        raise Skip("no title block")
    labels = {k.upper() for k in truth.title}
    for e in list(msp.query("TEXT")):
        p = e.dxf.insert
        if box[0] <= p.x <= box[2] and box[1] <= p.y <= box[3] and e.dxf.text.strip().upper() not in labels:
            msp.delete_entity(e)
    block = doc.blocks.new("TITLEBLOCK")
    for n, key in enumerate(truth.title):
        block.add_attdef(key.upper(), (0, -10 * n), dxfattribs={"height": 3.5})
    insert = msp.add_blockref("TITLEBLOCK", (box[0] + 60, box[3] - 11))
    insert.add_auto_attribs({k.upper(): v for k, v in truth.title.items()})
    return doc


def _as_lines(doc: Drawing, truth: Truth) -> Drawing:
    """Polylines exploded into plain LINE and ARC entities."""
    msp = doc.modelspace()
    for e in list(msp.query("LWPOLYLINE POLYLINE")):
        layer, linetype = e.dxf.layer, e.dxf.get("linetype", "BYLAYER")
        for v in e.explode():
            v.dxf.layer = layer
            if linetype != "BYLAYER":
                v.dxf.linetype = linetype
    return doc


def _mtext(doc: Drawing, truth: Truth) -> Drawing:
    """Every TEXT rewritten as an MTEXT."""
    msp = doc.modelspace()
    for t in list(msp.query("TEXT")):
        m = msp.add_mtext(t.dxf.text, dxfattribs={"char_height": t.dxf.height, "layer": t.dxf.layer})
        m.dxf.insert = t.dxf.insert
        msp.delete_entity(t)
    return doc


def _named_linetypes(doc: Drawing, truth: Truth) -> Drawing:
    """ISO linetype names (ACAD_ISO02W100, ACAD_ISO04W100, ...) in place of DASHED, CENTER and friends."""
    names = {e.dxf.name.upper(): e for e in doc.linetypes}
    for name, pattern in _ISO_LINETYPES.items():
        if name not in names:
            doc.linetypes.new(name, dxfattribs={"description": name, "pattern": pattern})
    for layer in doc.layers:
        old = (layer.dxf.linetype or "").upper()
        if old in _LINETYPE_RENAMES:
            layer.dxf.linetype = _LINETYPE_RENAMES[old]
    for space in (doc.modelspace(), *doc.blocks):
        for e in space:
            old = (e.dxf.get("linetype", "BYLAYER") or "BYLAYER").upper()
            if old in _LINETYPE_RENAMES:
                e.dxf.linetype = _LINETYPE_RENAMES[old]
    return doc


def _split_section(doc: Drawing, truth: Truth) -> Drawing:
    """The section drawn the other legal way: two separate hatched walls, no far-edge lines across the bore."""
    if not any(v.hatch_area for v in truth.views):
        raise Skip("no section view")
    msp = doc.modelspace()
    for hatch in list(msp.query("HATCH")):
        loops = [_loop_box(p) for p in hatch.paths]
        if len(loops) < 2:
            continue
        outer = max(loops, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        inner = [b for b in loops if b is not outer and _strictly_inside(b, outer, slack=-TOL)]
        if not inner:
            continue
        band = max(inner, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        walls = _walls(outer, band)
        if walls is None:
            continue
        stacked_y = walls[0][3] == band[1]  # walls stacked in y when the band spans the full x extent
        for e in list(msp):
            if e.dxftype() not in ("LWPOLYLINE", "LINE") or e.dxf.layer == "center":
                continue
            box = _entity_box(e)
            if _strictly_inside(box, outer, slack=-TOL):  # an island outline: keep the segments that stay on one wall
                kept = [seg for seg in _segments(e) if not _bridges(seg, band, stacked_y)]
                msp.delete_entity(e)
                for seg in kept:
                    msp.add_line(seg[0], seg[1], dxfattribs={"layer": "outline"})
            elif _strictly_inside(box, outer, slack=-TOL) and _strictly_inside(outer, box, slack=-TOL):
                # the silhouette: replaced by two closed wall outlines
                msp.delete_entity(e)
        for box in walls:
            msp.add_lwpolyline(
                [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])],
                close=True,
                dxfattribs={"layer": "outline"},
            )
    return doc


def _segments(e) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    if e.dxftype() == "LINE":
        return [((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))]
    pts = [(v[0], v[1]) for v in e.get_points()]
    pts = pts + [pts[0]] if e.closed else pts
    return list(zip(pts, pts[1:], strict=False))


def _bridges(seg, band, stacked_y: bool) -> bool:
    """A segment reaching within GAP of both wall faces joins the walls back into one region."""
    axis = 1 if stacked_y else 0
    lo, hi = min(seg[0][axis], seg[1][axis]), max(seg[0][axis], seg[1][axis])
    return lo <= band[axis] + 3.0 and hi >= band[axis + 2] - 3.0


def _loop_box(path) -> tuple[float, float, float, float]:
    xs = [v[0] for v in path.vertices]
    ys = [v[1] for v in path.vertices]
    return (min(xs), min(ys), max(xs), max(ys))


def _entity_box(e) -> tuple[float, float, float, float]:
    b = ezbbox.extents([e])
    return (b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y)


def _strictly_inside(inner, outer, slack: float = 0.0) -> bool:
    return (
        inner[0] > outer[0] + slack
        and inner[1] > outer[1] + slack
        and inner[2] < outer[2] - slack
        and inner[3] < outer[3] - slack
    )


def _walls(outer, band) -> list[tuple[float, float, float, float]] | None:
    """The two material strips between the outer box and the bore band, along whichever axis the band splits."""
    if band[0] <= outer[0] + TOL and band[2] >= outer[2] - TOL:
        walls = [(outer[0], outer[1], outer[2], band[1]), (outer[0], band[3], outer[2], outer[3])]
    elif band[1] <= outer[1] + TOL and band[3] >= outer[3] - TOL:
        walls = [(outer[0], outer[1], band[0], outer[3]), (band[2], outer[1], outer[2], outer[3])]
    else:
        return None
    return walls if all(w[2] - w[0] > TOL and w[3] - w[1] > TOL for w in walls) else None


def fair_variant(name: str, doc: Drawing, truth: Truth) -> Drawing:
    """A copy of the reference sheet rewritten `name`-style; raises Skip when it cannot apply."""
    run = {
        "attrib-title": _attrib_title,
        "as-lines": _as_lines,
        "mtext": _mtext,
        "named-linetypes": _named_linetypes,
        "split-section": _split_section,
    }[name]
    return run(roundtrip(doc), truth)


def _score(doc: Drawing, task: Task, truth: Truth) -> TaskResult:
    """Grade a document the way a submission is graded: saved to a file, reloaded by `sheet.load`."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sheet.dxf"
        doc.saveas(path)
        return grade(load(path), task, truth)


def _below_one(result: TaskResult) -> list[str]:
    return [f"{c.id}={c.score:g}" for c in result.checks if c.score < 1.0]


def _content_mean(result: TaskResult) -> float:
    scores = [v for part, v in result.parts.items() if part != "gate"]
    return statistics.fmean(scores) if scores else 0.0


def degenerate(kind: str, request: str, truth: Truth) -> Drawing:
    """Sheets that must score near 0: nothing, a title block with blank fields, or the request text copied in."""
    if kind == "empty":
        doc = ezdxf.new("R2018")
        doc.header["$INSUNITS"] = MM
        return doc
    doc = new_sheet()
    if kind == "boxes-and-floating-dims":
        return _boxes_and_floating_dims(truth)
    if kind == "title-block-only":
        frame(doc, {label: "" for label in truth.title})
    else:
        frame(doc, {})
        doc.modelspace().add_text(request, height=3.5).set_placement((40.0, A3[1] / 2))
    return doc


def _boxes_and_floating_dims(truth: Truth) -> Drawing:
    """The audit's cheat, generalised: empty view-sized boxes in the right places, every required dimension as a
    DIMENSION floating in a margin with override text. Honest-looking, attached to nothing: it must not pass."""
    doc = new_sheet()
    msp = doc.modelspace()
    frame(doc, dict(truth.title))
    factor = {"1:1": 1.0, "1:2": 0.5, "2:1": 2.0}[truth.scale]
    for x, y, w, h in place({v.name: (v.width * factor, v.height * factor) for v in truth.views}, 0).values():
        rect(msp, x, y, w, h)
    y = A3[1] - 30.0
    for d in truth.dims:
        prefix = {"diameter": "%%c", "radius": "R"}.get(d.kind, "")
        if d.kind == "angular":
            dim = msp.add_angular_dim_3p(
                base=(30, y + 5),
                center=(30, y),
                p1=(35, y),
                p2=(30, y + 5),
                dimstyle=DIMSTYLE,
                text=f"{d.value:g}%%d",
            )
        else:
            dim = msp.add_linear_dim(
                base=(25, y),
                p1=(22, y - 3),
                p2=(23, y - 3),
                dimstyle=DIMSTYLE,
                text=f"{prefix}{d.value:g}{d.fit or ''}",
            )
        dim.render()
        y -= 5.0
    return doc


def calibrate(families: list[str], seeds: int, require_targets: bool = True) -> dict:
    """Run every calibration case; the report has `ok`, `failures`, per-family `counts` and every `cases` row."""
    registered: set[str] = set()
    cases: list[dict] = []
    counts: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    applied: dict[str, int] = defaultdict(int)
    skipped: dict[str, set[str]] = defaultdict(set)

    def record(family: str, seed: int, case: str, ok: bool, **extra) -> None:
        counts[family][case][1] += 1
        counts[family][case][0] += ok
        cases.append({"family": family, "seed": seed, "case": case, "ok": ok, **extra})

    for family in families:
        fam = FAMILIES[family]
        for seed in range(seeds):
            for level in ("given", "calc"):
                inputs = fam.sample(seed) if level == "given" else fam.calc(seed)
                truth = fam.truth(inputs)
                task = Task(
                    id=f"{family}-{seed:04d}{'-calc' if level == 'calc' else ''}",
                    track="calc-sheet",
                    family=family,
                    seed=seed,
                    level=level,
                )
                found = _calibrate_task(
                    fam, inputs, truth, task, family, seed, level, record, applied, skipped, require_targets
                )
                registered |= found

    failures = [f"{c['family']}-{c['seed']} {c['case']}: {_why(c)}" for c in cases if not c["ok"]]
    for name in MUTANTS:
        if not applied[name] and not any("not available" in r for r in skipped[name]):
            failures.append(f"mutant {name} never applied: {sorted(skipped[name])}")
    return {
        "ok": not failures,
        "failures": failures,
        "counts": {f: dict(c) for f, c in counts.items()},
        "mutants": {n: {"applied": applied[n], "skipped": sorted(skipped[n])} for n in MUTANTS},
        "checks": sorted(registered),
        "cases": cases,
    }


def _calibrate_task(
    fam,
    inputs: dict,
    truth: Truth,
    task: Task,
    family: str,
    seed: int,
    level: str,
    record,
    applied,
    skipped,
    require_targets: bool,
) -> set[str]:
    """One sheet task across layouts, fairness variants, mutants and degenerate sheets; returns its check ids."""
    registered: set[str] = set()
    reference = fam.draw(inputs, 0)
    for layout in LAYOUTS:
        result = _score(reference if layout == 0 else fam.draw(inputs, layout), task, truth)
        if layout == 0:
            registered = {c.id for c in result.checks}
        record(
            family,
            seed,
            "reference" if layout == 0 else "variant",
            not _below_one(result),
            below=_below_one(result),
            layout=layout,
            level=level,
        )
    for name in FAIR:
        try:
            variant = fair_variant(name, reference, truth)
        except Skip as exc:
            skipped[name].add(str(exc))
            continue
        result = _score(variant, task, truth)
        record(family, seed, name, not _below_one(result), below=_below_one(result), level=level)
    for name in MUTANTS:
        try:
            mutation = apply(name, reference, truth, random.Random(f"{family}:{seed}:{name}"))
        except Skip as exc:
            skipped[name].add(str(exc))
            continue
        applied[name] += 1
        result = _score(mutation.doc, task, truth)
        score = {c.id: c.score for c in result.checks}
        missing = [t for t in mutation.targets if t not in score]
        survived = [t for t in mutation.targets if score.get(t, 0.0) >= 1.0]
        also = [c for c in _below_one(result) if c.split("=")[0] not in mutation.targets]
        ok = not survived and (not missing or not require_targets)
        record(family, seed, name, ok, survived=survived, unregistered=missing, also_failed=also, level=level)
    for kind in DEGENERATE:
        result = _score(degenerate(kind, fam.request(inputs), truth), task, truth)
        mean = _content_mean(result)
        # the cheat may pass many non-critical checks; what matters is that the task fails
        ok = (
            not result.passed if kind == "boxes-and-floating-dims" else (not result.passed and mean <= NEAR_ZERO + 1e-9)
        )
        record(family, seed, kind, ok, passed=result.passed, mean=round(mean, 3), level=level)
    if level == "given":  # the review track has one level: its task is the same sheet either way
        ok, extra = _review_case(fam, inputs, truth, family, seed)
        record(family, seed, "review", ok, **extra)
    return registered


def _review_case(fam, inputs: dict, truth: Truth, family: str, seed: int) -> tuple[bool, dict]:
    """Seed errors; the errors as findings must pass and an empty answer must fail."""
    task = Task(id=f"{family}-review-{seed:04d}", track="review", family=family, seed=seed)
    try:
        _, errors = seed_errors(fam.draw(inputs, 0), truth, random.Random(f"{family}:{seed}:review"))
    except Skip as exc:
        return False, {"reason": str(exc)}
    graded = truth.model_copy(update={"errors": errors})
    doc = fam.draw(inputs, 0)
    exact = [Finding(kind=e.kind, x=e.x, y=e.y) for e in errors]
    good = grade(ReviewSheet(doc, findings=exact), task, graded)
    none = grade(ReviewSheet(doc, findings=[]), task, graded)
    ok = good.passed and all(c.score == 1.0 for c in good.checks) and not none.passed
    return ok, {"errors": [e.kind for e in errors], "exact": good.parts, "empty": none.parts}


def _why(case: dict) -> str:
    parts = [f"{k}={v}" for k, v in case.items() if k not in ("family", "seed", "case", "ok") and v not in ([], "")]
    return " ".join(parts) or "failed"


def table(report: dict) -> str:
    """One row per family: cases ok / cases run, then the mutant coverage line."""
    cases = ("reference", "variant", *FAIR, *MUTANTS, *DEGENERATE, "review")
    head = ["family", *cases]
    rows = [head]
    for family, counts in report["counts"].items():
        rows.append([family, *(f"{counts[c][0]}/{counts[c][1]}" if c in counts else "-" for c in cases)])
    widths = [max(len(r[i]) for r in rows) for i in range(len(head))]
    lines = ["  ".join(cell.ljust(w) for cell, w in zip(r, widths, strict=True)).rstrip() for r in rows]
    extra = {
        n: sorted({x.split("=")[0] for c in report["cases"] if c["case"] == n for x in c.get("also_failed", [])})
        for n in MUTANTS
    }
    lines += [f"  {n} also failed: {' '.join(v)}" for n, v in extra.items() if v]
    lines += [f"  {n} skipped: {'; '.join(m['skipped'])}" for n, m in report["mutants"].items() if m["skipped"]]
    lines += [f"FAIL {f}" for f in report["failures"][:SHOWN]]
    if len(report["failures"]) > SHOWN:
        lines.append(f"... and {len(report['failures']) - SHOWN} more failures in the JSON report")
    lines.append("calibration " + ("ok" if report["ok"] else "FAILED"))
    return "\n".join(lines)


def run(families: list[str], seeds: int, out: Path | None) -> int:
    report = calibrate(families, seeds)
    print(table(report))
    if out:
        out.write_text(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1
