"""Fits shown: a fitted dimension carries its ISO 286 designation or the matching limit deviations."""

import re

from .. import iso286
from ..schema import CheckResult, Dim, Task, Truth
from ..sheet import Dimension, Sheet
from .dims import match

DEVIATION_TOLERANCE = 0.001  # mm
_NUM = r"\d+(?:[.,]\d+)?"
_ZERO = r"(?<![\d.,])0(?:[.,]0+)?(?![\d.,])"
_TOKEN = rf"(?:[+-]\s*{_NUM}|{_ZERO})"
_PAIR = re.compile(rf"({_TOKEN})\s*[/^]?\s*({_TOKEN})")
_SYMMETRIC = re.compile(rf"±\s*({_NUM})")


def _plain(text: str) -> str:
    """Dimension text with MTEXT stacking turned into `upper/lower` and symbols spelled out."""
    text = re.sub(r"\\S([^;]*);", lambda m: " " + m.group(1).replace("^", "/").replace("#", "/") + " ", text)
    text = re.sub(r"\\[A-Za-z][^;]*;|[{}]", "", text)
    return text.replace("%%c", "Ø").replace("%%C", "Ø").replace("%%p", "±").replace("%%P", "±").replace("−", "-")


def _value(token: str) -> float:
    return float(token.replace(" ", "").replace(",", "."))


def deviations(text: str) -> tuple[float, float] | None:
    """The (upper, lower) deviations written in a dimension text, or None."""
    plain = _plain(text)
    pair = _PAIR.search(plain)
    if pair:
        return _value(pair.group(1)), _value(pair.group(2))
    symmetric = _SYMMETRIC.search(plain)
    if symmetric:
        half = _value(symmetric.group(1))
        return half, -half
    return None


def shows(dim: Dim, shown: Dimension) -> bool:
    """True when the dimension text carries the designation or the limit deviations of `dim.fit`. A `deviations`
    fit_form asks for the written deviations only: the designation alone does not satisfy it."""
    if not dim.fit:
        return True
    plain = _plain(shown.text)
    written = deviations(shown.text)
    upper, lower = iso286.limits(dim.fit, dim.value)
    right = written is not None and (
        abs(written[0] - upper) <= DEVIATION_TOLERANCE + 1e-9 and abs(written[1] - lower) <= DEVIATION_TOLERANCE + 1e-9
    )
    if dim.fit_form == "deviations":
        return right
    return right or bool(re.search(rf"(?<![A-Za-z]){re.escape(dim.fit)}(?!\d)", plain))


def fits(sheet: Sheet, task: Task, truth: Truth) -> list[CheckResult]:
    fitted = [d for d in truth.dims if d.fit]
    if not fitted:
        return []  # a check that does not apply returns nothing; a free 1.0 would lift empty sheets
    matched = match(sheet, truth, prefer=lambda dim, shown: shows(dim, shown))
    missing = [d.id for d in fitted if d.id not in matched or not shows(d, matched[d.id])]
    score = 1.0 - len(missing) / len(fitted)
    return [
        CheckResult(
            id="fits.shown",
            part="fits",
            critical=True,
            score=score,
            detail=tuple(f"fit not shown on {m}" for m in missing),
        )
    ]
