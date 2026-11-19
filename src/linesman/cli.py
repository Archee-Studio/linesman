"""`linesman make`, `linesman grade`: compact output, non-interactive, exit 0 on success."""

import argparse
import json
import random
from pathlib import Path

from .calibrate import run as run_calibration
from .families import FAMILIES
from .grade import grade_files
from .mutate import Skip, seed_errors
from .schema import Finding, Task

REVIEW_REQUEST = (
    "Review the attached detail sheet (sheet.dxf) of the {part}. It holds one to three seeded errors: a dimension "
    "that shows a wrong value, a required dimension that is missing, a wrong fit designation, a wrong title-block "
    "field, or a missing view. Return findings.json: a list of objects with kind (wrong-value, missing-dim, "
    "wrong-fit, wrong-title-field or missing-view), x and y (the point on the sheet in "
    "millimetres) and an optional note."
)


def make_review(family: str, seeds: range, out: Path) -> list[Path]:
    """Write review task folders: sheet.dxf is the reference with 1-3 seeded errors; `reference/` holds the oracle."""
    fam = FAMILIES[family]
    made = []
    for seed in seeds:
        inputs = fam.sample(seed)
        truth = fam.truth(inputs)
        try:
            doc, errors = seed_errors(fam.draw(inputs, 0), truth, random.Random(f"{family}:{seed}:review"))
        except Skip:
            continue
        task = Task(id=f"{family}-review-{seed:04d}", track="review", family=family, seed=seed)
        folder = out / "tasks" / task.id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "task.json").write_text(task.model_dump_json(indent=2))
        (folder / "task.md").write_text(REVIEW_REQUEST.format(part=inputs["part"].lower()) + "\n")
        (folder / "inputs.json").write_text(json.dumps(inputs, indent=2))
        (folder / "truth.json").write_text(truth.model_copy(update={"errors": errors}).model_dump_json(indent=2))
        doc.saveas(folder / "sheet.dxf")
        sub = out / "reference" / task.id
        sub.mkdir(parents=True, exist_ok=True)
        findings = [Finding(kind=e.kind, x=e.x, y=e.y).model_dump() for e in errors]
        (sub / "findings.json").write_text(json.dumps(findings, indent=2))
        made.append(folder)
    return made


def make(family: str, seeds: range, out: Path, layout: int) -> list[Path]:
    """Write calc-sheet task folders and the reference sheet of each as a submission."""
    fam = FAMILIES[family]
    made = []
    for seed in seeds:
        inputs = fam.sample(seed)
        task = Task(id=f"{family}-{seed:04d}", track="calc-sheet", family=family, seed=seed)
        folder = out / "tasks" / task.id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "task.json").write_text(task.model_dump_json(indent=2))
        (folder / "task.md").write_text(fam.request(inputs) + "\n")
        (folder / "inputs.json").write_text(json.dumps(inputs, indent=2))
        (folder / "truth.json").write_text(fam.truth(inputs).model_dump_json(indent=2))
        sub = out / "reference" / task.id
        sub.mkdir(parents=True, exist_ok=True)
        fam.draw(inputs, layout).saveas(sub / "sheet.dxf")
        made.append(folder)
    return made


def grade_all(tasks: Path, submissions: Path) -> list[dict]:
    rows = []
    for folder in sorted(p for p in tasks.iterdir() if (p / "task.json").is_file()):
        rows.append(grade_files(folder, submissions / folder.name).model_dump())
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="linesman", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("make", help="generate tasks and reference sheets")
    m.add_argument("--family", choices=sorted(FAMILIES), required=True)
    m.add_argument("--seeds", type=int, default=5, help="seeds 0..N-1")
    m.add_argument("--track", choices=["calc-sheet", "review"], default="calc-sheet")
    m.add_argument("--layout", type=int, default=0, help="0 is the reference layout")
    m.add_argument("--out", type=Path, default=Path("out"))
    g = sub.add_parser("grade", help="grade a submissions folder against a tasks folder")
    g.add_argument("tasks", type=Path)
    g.add_argument("submissions", type=Path)
    g.add_argument("--out", type=Path, help="write results JSON here")
    c = sub.add_parser("calibrate", help="prove the checks: references pass, mutants fail, empty sheets score 0")
    c.add_argument("--families", default="all", help="comma-separated families or 'all'")
    c.add_argument("--seeds", type=int, default=3, help="seeds 0..N-1 per family")
    c.add_argument("--out", type=Path, help="write the JSON report here")
    args = parser.parse_args(argv)
    if args.command == "calibrate":
        names = sorted(FAMILIES) if args.families == "all" else args.families.split(",")
        unknown = [n for n in names if n not in FAMILIES]
        if unknown:
            parser.error(f"unknown families: {', '.join(unknown)}")
        return run_calibration(names, args.seeds, args.out)
    if args.command == "make":
        if args.track == "review":
            made = make_review(args.family, range(args.seeds), args.out)
        else:
            made = make(args.family, range(args.seeds), args.out, args.layout)
        print(f"made {len(made)} tasks in {args.out / 'tasks'}; reference sheets in {args.out / 'reference'}")
        return 0
    rows = grade_all(args.tasks, args.submissions)
    passed = sum(r["passed"] for r in rows)
    print(f"graded {len(rows)} tasks: {passed} passed, {sum(r['valid'] for r in rows)} valid")
    for r in rows:
        failed = [c["id"] for c in r["checks"] if c["critical"] and c["score"] < 1]
        print(f"  {r['task']}: {'pass' if r['passed'] else 'fail'} {' '.join(failed)}")
    if args.out:
        args.out.write_text(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
