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
from ezdxf.document import Drawing

from .checks.review import ReviewSheet
from .families import FAMILIES
from .families.drafting import A3, frame, new_sheet
from .grade import grade
from .mutate import MUTANTS, Skip, apply, seed_errors
from .schema import Finding, Task, TaskResult, Truth
from .sheet import MM, load

LAYOUTS = (0, 1, 2)
NEAR_ZERO = 0.2
SHOWN = 12  # failures printed in the table; the JSON report holds all of them
DEGENERATE = ("empty", "title-block-only", "copied-input")


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
    if kind == "title-block-only":
        frame(doc, {label: "" for label in truth.title})
    else:
        frame(doc, {})
        doc.modelspace().add_text(request, height=3.5).set_placement((40.0, A3[1] / 2))
    return doc


def calibrate(families: list[str], seeds: int, require_targets: bool = True) -> dict:
    """Run every calibration case; the report has `ok`, `failures`, per-family `counts` and every `cases` row."""
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
            inputs = fam.sample(seed)
            truth = fam.truth(inputs)
            task = Task(id=f"{family}-{seed:04d}", track="calc-sheet", family=family, seed=seed)
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
                )
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
                record(family, seed, name, ok, survived=survived, unregistered=missing, also_failed=also)
            for kind in DEGENERATE:
                result = _score(degenerate(kind, fam.request(inputs), truth), task, truth)
                mean = _content_mean(result)
                record(
                    family,
                    seed,
                    kind,
                    not result.passed and mean <= NEAR_ZERO + 1e-9,
                    passed=result.passed,
                    mean=round(mean, 3),
                )
            ok, extra = _review_case(fam, inputs, truth, family, seed)
            record(family, seed, "review", ok, **extra)

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
    cases = ("reference", "variant", *MUTANTS, *DEGENERATE, "review")
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
