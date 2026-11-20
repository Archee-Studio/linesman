"""`linesman report`: the per-system metrics of the spec over k independent runs.

Each results file is one run: the list of `TaskResult` rows `linesman grade --out` writes, or an object
`{"system": name, "results": [...]}`. The k index comes from a `run` field in the object, else the file's
order. Rows without a `system` field take it from their file's name (stem minus a trailing `-k<n>`).
"""

import json
import re
import statistics
from collections import defaultdict
from pathlib import Path


def _rows(path: Path) -> tuple[str, int, list[dict]]:
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict):
        rows = data["results"]
        system = data.get("system")
        run = int(data.get("run", 0))
    else:
        rows, system, run = data, None, 0
    if system is None:
        system = re.sub(r"-?k?\d+$", "", Path(path).stem) or Path(path).stem
    return system, run, rows


def _task_score(row: dict) -> float:
    """One task's score: the mean of its parts (a missing submission scores 0)."""
    parts = row.get("parts") or {}
    return sum(parts.values()) / len(parts) if parts else 0.0


def aggregate(files: list[Path]) -> dict:
    """Group the runs by system and compute the spec metrics for each."""
    systems: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for path in files:
        system, run, rows = _rows(path)
        for row in rows:
            systems[system].append((run, row))
    out = {}
    for system, entries in systems.items():
        scores = [_task_score(r) for _, r in entries]
        valid = [bool(r.get("valid")) for _, r in entries]
        passed = [bool(r.get("passed")) for _, r in entries]
        part_scores: dict[str, list[float]] = defaultdict(list)
        for _, r in entries:
            for part, score in (r.get("parts") or {}).items():
                part_scores[part].append(score)
        by_task: dict[str, list[float]] = defaultdict(list)
        for _, r in entries:
            by_task[r["task"]].append(_task_score(r))
        out[system] = {
            "tasks": len(by_task),
            "runs": max((len(v) for v in by_task.values()), default=0),
            "valid_rate": sum(valid) / len(entries),
            "pass_rate": sum(passed) / len(entries),
            "score_on_valid": (sum(s for s, v in zip(scores, valid, strict=False) if v) / max(1, sum(valid))),
            "score_as_zero": sum(s if v else 0.0 for s, v in zip(scores, valid, strict=False)) / len(entries),
            "parts": {p: sum(v) / len(v) for p, v in sorted(part_scores.items())},
            "median_of_k": statistics.mean(statistics.median(v) for v in by_task.values()),
            "worst_of_k": statistics.mean(min(v) for v in by_task.values()),
        }
    return out


def table(report: dict) -> str:
    """A compact board: one row per system."""
    head = ["system", "tasks", "runs", "valid", "pass", "score|valid", "score|zero", "median k", "worst k"]
    rows = [head]
    for system, m in sorted(report.items()):
        rows.append(
            [
                system,
                str(m["tasks"]),
                str(m["runs"]),
                f"{m['valid_rate']:.2f}",
                f"{m['pass_rate']:.2f}",
                f"{m['score_on_valid']:.3f}",
                f"{m['score_as_zero']:.3f}",
                f"{m['median_of_k']:.3f}",
                f"{m['worst_of_k']:.3f}",
            ]
        )
    widths = [max(len(r[i]) for r in rows) for i in range(len(head))]
    lines = ["  ".join(c.ljust(w) for c, w in zip(r, widths, strict=False)).rstrip() for r in rows]
    for system, m in sorted(report.items()):
        lines.append(f"{system} parts: " + " ".join(f"{p}={v:.3f}" for p, v in m["parts"].items()))
    return "\n".join(lines)
