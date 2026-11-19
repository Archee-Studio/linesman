"""Title block fields: each required value appears in some text of the sheet."""

import re

from ..regions import title_block
from ..schema import CheckResult, Task, Truth
from ..sheet import Sheet


def _normal(text: str) -> str:
    text = re.sub(r"\\[A-Za-z][^;]*;|[{}]", "", text)  # MTEXT formatting left in TEXT entities
    return " ".join(text.replace("%%c", "Ø").replace("%%C", "Ø").lower().split())


def titleblock(sheet: Sheet, task: Task, truth: Truth) -> list[CheckResult]:
    if not truth.title:
        return []  # nothing required, nothing scored
    box = title_block(sheet)
    if box is None:
        return [
            CheckResult(
                id="titleblock.fields",
                part="titleblock",
                critical=True,
                score=0.0,
                detail=("no title block: a closed rectangle at the frame's lower-right corner",),
            )
        ]
    x0, y0, x1, y1 = box
    texts = [_normal(t.text) for t in sheet.texts if x0 <= t.x <= x1 and y0 <= t.y <= y1]
    missing = []
    for label, value in truth.title.items():
        wanted = re.compile(rf"(?<![0-9a-z]){re.escape(_normal(value))}(?![0-9a-z])")
        if not any(wanted.search(t) for t in texts):
            missing.append(label)
    score = 1.0 - len(missing) / len(truth.title)
    return [
        CheckResult(
            id="titleblock.fields",
            part="titleblock",
            critical=True,
            score=score,
            detail=tuple(f"missing {m}" for m in missing),
        )
    ]
