"""Review track: a finding matches a seeded error of the same kind within REACH_MM of its point, one to one."""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from ..schema import CheckResult, Finding, SeededError, Task, Truth
from ..sheet import Sheet

REACH_MM = 15.0
MAX_BYTES = 1_000_000
MAX_FINDINGS = 500


@dataclass
class ReviewSheet(Sheet):
    """The task's sheet plus the submission's findings. `problem` is set when findings.json is missing or invalid."""

    findings: list[Finding] = field(default_factory=list)
    problem: str = ""


def read_findings(path: Path) -> tuple[list[Finding], str]:
    """Findings from a submitted findings.json (hostile input): a list of Finding, or the reason it is not one."""
    if not path.is_file():
        return [], "missing findings.json"
    if path.stat().st_size > MAX_BYTES:
        return [], f"findings.json over {MAX_BYTES} bytes"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        found = TypeAdapter(list[Finding]).validate_python(raw)
    except (OSError, ValueError, ValidationError, RecursionError) as exc:
        return [], f"findings.json is not a list of findings: {str(exc).splitlines()[0][:120]}"
    if len(found) > MAX_FINDINGS:
        return [], f"more than {MAX_FINDINGS} findings"
    if not all(math.isfinite(f.x) and math.isfinite(f.y) for f in found):
        return [], "a finding has a point that is not a finite number"
    return found, ""


def match(errors: tuple[SeededError, ...], findings: list[Finding]) -> list[tuple[SeededError, Finding]]:
    """The most one-to-one pairs of an error and a finding of its kind within REACH_MM (augmenting paths)."""
    near = [
        [j for j, f in enumerate(findings) if e.kind == f.kind and math.hypot(e.x - f.x, e.y - f.y) <= REACH_MM]
        for e in errors
    ]
    owner: dict[int, int] = {}

    def claim(i: int, seen: set[int]) -> bool:
        for j in near[i]:
            if j not in seen:
                seen.add(j)
                if j not in owner or claim(owner[j], seen):
                    owner[j] = i
                    return True
        return False

    for i in range(len(errors)):
        claim(i, set())
    return [(errors[i], findings[j]) for j, i in sorted(owner.items(), key=lambda p: p[1])]


def review(sheet: Sheet, task: Task, truth: Truth) -> list[CheckResult]:
    """Scores review-track tasks only; a calc-sheet task gets no review results."""
    if task.track != "review":
        return []
    if isinstance(sheet, ReviewSheet):
        problem, findings = sheet.problem, sheet.findings
    else:
        problem, findings = "no findings were read", []
    hits = len(match(truth.errors, findings))
    recall = hits / len(truth.errors) if truth.errors else 1.0
    precision = hits / len(findings) if findings else (1.0 if not truth.errors else 0.0)
    if problem:
        recall = precision = 0.0
    detail = (problem,) if problem else (f"{hits} of {len(truth.errors)} errors found with {len(findings)} findings",)
    return [
        CheckResult(id="review.recall", part="review", critical=True, score=recall, detail=detail),
        CheckResult(id="review.precision", part="review", critical=False, score=precision, detail=detail),
    ]
