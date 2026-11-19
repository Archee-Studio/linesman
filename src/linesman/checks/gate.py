"""The gate as a check, so it is reported like every other part."""

from ..schema import CheckResult, Task, Truth
from ..sheet import Sheet


def gate(sheet: Sheet, task: Task, truth: Truth) -> list[CheckResult]:
    return [
        CheckResult(
            id="gate.opens",
            part="gate",
            critical=True,
            score=0.0 if sheet.errors else 1.0,
            detail=tuple(sheet.errors),
        )
    ]
