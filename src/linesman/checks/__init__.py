"""The one registry of checks. Each check reads a parsed sheet and the truth and returns its results."""

from collections.abc import Callable

from ..schema import CheckResult, Task, Truth
from ..sheet import Sheet
from . import dims, drafting, finish, fits, gate, review, titleblock, views

Check = Callable[[Sheet, Task, Truth], list[CheckResult]]

# Order is report order. Modules stay importable by name; tests fail for a part without a check.
# review.review returns nothing for calc-sheet tasks; grade() runs only it for review tasks.
CHECKS: tuple[Check, ...] = (
    gate.gate,
    review.review,
    views.views,
    dims.dims,
    fits.fits,
    titleblock.titleblock,
    drafting.drafting,
    finish.finish,
)
