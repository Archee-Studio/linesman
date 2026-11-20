"""finish.roughness: a mark near either of two identical dimensions counts (a lever's twin bores)."""

import ezdxf

from linesman.checks.finish import finish
from linesman.schema import Dim, Task, Truth
from linesman.sheet import Dimension, Sheet, Text

TASK = Task(id="t", track="calc-sheet", family="lever", seed=0)
DIMS = (
    Dim(id="bore_big", kind="diameter", value=25, view="front"),
    Dim(id="bore_small", kind="diameter", value=25, view="front"),
)
TRUTH = Truth(views=(), dims=DIMS, finish={"bore_big": 1.6, "bore_small": 3.2})


def sheet(dims, texts):
    return Sheet(
        doc=ezdxf.new(),
        dims=[
            Dimension(kind="diameter", value=25, text=t, x=x, y=y, handle=str(i)) for i, (t, x, y) in enumerate(dims)
        ],
        texts=[Text(text=t, x=x, y=y, height=2.5) for t, x, y in texts],
    )


def test_marks_near_interchangeable_identical_dimensions_score_one():
    s = sheet(
        [("⌀25 H8", 95, 180), ("⌀25 H8", 255, 180)],
        [("Ra 1.6", 84, 169), ("Ra 3.2", 244, 169)],
    )
    assert finish(s, TASK, TRUTH)[0].score == 1.0


def test_mark_far_from_every_matching_dimension_fails():
    s = sheet(
        [("⌀25 H8", 95, 180), ("⌀25 H8", 255, 180)],
        [("Ra 1.6", 84, 169), ("Ra 3.2", 84, 169)],
    )
    assert finish(s, TASK, TRUTH)[0].score == 0.5
