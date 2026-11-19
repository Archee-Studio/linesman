"""Grade one submission against one task's truth."""

from collections import defaultdict
from pathlib import Path

from .checks import CHECKS
from .checks.review import ReviewSheet, read_findings, review
from .schema import CheckResult, Task, TaskResult, Truth
from .sheet import Sheet, load


def grade_files(task_dir: Path, submission_dir: Path) -> TaskResult:
    task = Task.model_validate_json((task_dir / "task.json").read_text())
    truth = Truth.model_validate_json((task_dir / "truth.json").read_text())
    if task.track == "review":  # the sheet is the task's own; the answer is the submission's findings.json
        return grade(load(task_dir / "sheet.dxf"), task, truth, submission_dir)
    return grade(load(submission_dir / "sheet.dxf"), task, truth, submission_dir)


def grade(sheet: Sheet, task: Task, truth: Truth, submission_dir: Path | None = None) -> TaskResult:
    if task.track == "review":
        return _grade_review(sheet, task, truth, submission_dir)
    results: list[CheckResult] = []
    for check in CHECKS:
        found = check(sheet, task, truth)
        if not sheet.valid:  # a failed gate zeroes every other check
            found = [r if r.part == "gate" else r.model_copy(update={"score": 0.0}) for r in found]
        results.extend(found)
    parts: dict[str, list[float]] = defaultdict(list)
    for r in results:
        parts[r.part].append(r.score)
    return TaskResult(
        task=task.id,
        valid=sheet.valid,
        passed=all(r.passed for r in results if r.critical),
        checks=tuple(results),
        parts={p: sum(s) / len(s) for p, s in parts.items()},
    )


def _grade_review(sheet: Sheet, task: Task, truth: Truth, submission_dir: Path | None) -> TaskResult:
    """Review tasks run only the review check: the calc-sheet checks would score the flawed sheet, not the findings.
    Missing or invalid findings.json scores 0 and the result is not valid."""
    if not isinstance(sheet, ReviewSheet):
        findings, problem = read_findings(submission_dir / "findings.json") if submission_dir else ([], "no findings")
        sheet = ReviewSheet(sheet.doc, sheet.errors, sheet.geometry, sheet.texts, sheet.dims, findings, problem)
    results = review(sheet, task, truth)
    return TaskResult(
        task=task.id,
        valid=not sheet.problem,
        passed=all(r.passed for r in results if r.critical),
        checks=tuple(results),
        parts={"review": sum(r.score for r in results) / len(results)},
    )
