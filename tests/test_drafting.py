"""The 0.2.1 grader checks: honest and attached dimensions, sheet drafting hygiene, and hostile-but-fair input."""

import math
import random

import pytest

from linesman.families import FAMILIES
from linesman.families.drafting import TITLE_H, TITLE_W, new_sheet
from linesman.mutate import apply, roundtrip, seed_errors
from linesman.schema import Task
from linesman.sheet import parse

PLATE = FAMILIES["plate"]


def _plate(seed=1):
    inputs = PLATE.sample(seed)
    return PLATE.draw(inputs), PLATE.truth(inputs)


def _check(result, check_id):
    return next(c for c in result.checks if c.id == check_id)


def _grade(doc, truth):
    from linesman.grade import grade

    return grade(parse(doc), Task(id="t", track="calc-sheet", family="plate", seed=1), truth)


def test_dimension_carries_measurement_and_points():
    doc, _ = _plate()
    for d in parse(doc).dims:
        assert math.isfinite(d.measured) and math.isfinite(d.raw)
        assert d.points, d.text
    linear = next(d for d in parse(doc).dims if d.kind == "linear")
    assert len(linear.points) == 2


def test_override_text_that_lies_fails_dims_true():
    doc, truth = _plate()
    mutated = apply("lying-text", doc, truth, random.Random(2))
    result = _grade(mutated.doc, truth)
    assert _check(result, "dims.true").score < 1.0
    assert _check(result, "dims.recall").score == 1.0


def test_detached_dimension_fails_dims_attached_not_recall():
    doc, truth = _plate()
    mutated = apply("detached-dim", doc, truth, random.Random(3))
    result = _grade(mutated.doc, truth)
    assert _check(result, "dims.attached").score < 1.0
    assert _check(result, "dims.recall").score == 1.0


def test_title_values_as_attribs_score_titleblock_one():
    doc, truth = _plate()
    doc = roundtrip(doc)
    msp = doc.modelspace()
    x0, top = 420 - 10 - TITLE_W, 10 + TITLE_H
    labels = {k.upper() for k in truth.title}
    for t in list(msp.query("TEXT")):
        p = t.dxf.insert
        if p.x >= x0 and p.y <= top and t.dxf.text.strip().upper() not in labels:
            msp.delete_entity(t)
    block = doc.blocks.new("TB")
    for n, key in enumerate(truth.title):
        block.add_attdef(key.upper(), (0, -10 * n), dxfattribs={"height": 3.5})
    insert = msp.add_blockref("TB", (x0 + 60, top - 11))
    insert.add_auto_attribs({k.upper(): v for k, v in truth.title.items()})
    sheet = parse(roundtrip(doc))
    assert any(t.text == truth.title["material"] for t in sheet.texts)  # attribs are read
    result = _grade(doc, truth)
    assert _check(result, "titleblock.fields").score == 1.0


def test_boxes_and_floating_dims_fail_the_task():
    from linesman.calibrate import degenerate

    doc, truth = _plate()
    cheat = degenerate("boxes-and-floating-dims", PLATE.request(PLATE.sample(1)), truth)
    result = _grade(cheat, truth)
    assert not result.passed
    assert _check(result, "dims.true").score < 1.0
    assert _check(result, "dims.attached").score < 1.0
    assert _check(result, "views.present").score == 1.0  # the cheat does draw view-sized boxes


def test_new_mutants_fail_their_targets():
    targets = {
        "off-sheet": "drafting.on_sheet",
        "tiny-text": "drafting.text",
        "overlap-text": "drafting.clear",
        "solid-hidden": "drafting.linetypes",
    }
    doc, truth = _plate()
    for name, check_id in targets.items():
        mutated = apply(name, doc, truth, random.Random(4))
        result = _grade(mutated.doc, truth)
        assert _check(result, check_id).score < 1.0, name


def test_review_seeding_still_uses_the_five_reviewable_kinds():
    doc, truth = _plate()
    kinds = set()
    for seed in range(12):
        _, errors = seed_errors(doc, truth, random.Random(seed))
        kinds |= {e.kind for e in errors}
    assert kinds <= {"wrong-value", "missing-dim", "wrong-fit", "wrong-title-field", "missing-view"}


@pytest.mark.parametrize("name", ("attrib-title", "as-lines", "mtext", "named-linetypes"))
def test_fairness_variants_score_one(name):
    from linesman.calibrate import fair_variant

    doc, truth = _plate()
    result = _grade(fair_variant(name, doc, truth), truth)
    assert all(c.score == 1.0 for c in result.checks), [c.id for c in result.checks if c.score < 1.0]


def test_no_frame_scores_drafting_on_sheet_zero():
    doc = new_sheet()
    msp = doc.modelspace()
    msp.add_circle((100, 100), 20)  # loose geometry; no closed rectangle means no frame
    msp.add_circle((160, 140), 15)
    _, truth = _plate()
    result = _grade(doc, truth)
    assert _check(result, "drafting.on_sheet").score == 0.0


def test_dimension_may_attach_in_another_view():
    """ISO lets the drafter choose the view: a 'front' dim drawn on top-view geometry still counts as attached."""
    inputs = PLATE.sample(1)
    doc, truth = PLATE.draw(inputs), PLATE.truth(inputs)
    doc = roundtrip(doc)
    top = PLATE.views(inputs)["top"]  # x, y, w, h of the top view's outline
    parsed = {d.value: d.handle for d in parse(doc).dims}
    height_dim = doc.entitydb[parsed[inputs["height"]]]
    height_dim.dxf.text = f"{inputs['height']:g}"  # freeze the honest value before moving the points
    p = (top[0] + top[2], top[1])  # the top view's right vertical edge
    height_dim.dxf.defpoint2 = p
    height_dim.dxf.defpoint3 = (p[0], top[1] + top[3])
    result = _grade(doc, truth)
    assert _check(result, "dims.attached").score == 1.0, _check(result, "dims.attached").detail
    assert _check(result, "dims.recall").score == 1.0


def _msp_dim_points(doc):
    return {d.kind: len(d.points) for d in parse(doc).dims}


def test_angular_two_line_dim_points_skip_the_arc_location():
    doc = new_sheet()
    doc.modelspace().add_angular_dim_2l(
        base=(50, 60), line1=((30, 40), (50, 50)), line2=((30, 40), (70, 30)), dimstyle="EZDXF"
    ).render()
    d = next(d for d in parse(doc).dims if d.kind == "angular")
    assert len(d.points) == 4  # the two line ends and the vertex, not the arc point


def test_angular_three_point_dim_points_skip_the_dim_line():
    doc = new_sheet()
    doc.modelspace().add_angular_dim_3p(
        base=(50, 60), center=(30, 40), p1=(50, 50), p2=(70, 30), dimstyle="EZDXF"
    ).render()
    d = next(d for d in parse(doc).dims if d.kind == "angular")
    assert len(d.points) == 3


def test_ordinate_dim_points_are_the_feature_only():
    doc = new_sheet()
    doc.modelspace().add_ordinate_dim(
        feature_location=(50, 50), offset=(10, 0), dtype=0, origin=(30, 30), dimstyle="EZDXF"
    ).render()
    d = next(d for d in parse(doc).dims if d.kind == "linear")
    assert d.points == ((50.0, 50.0),)


def test_linetype_class_trusts_known_names_over_malformed_patterns():
    import ezdxf

    from linesman.geo import linetype_class

    doc = ezdxf.new("R2018")
    doc.linetypes.add("BADCENTER", pattern="A,-2,2,-2", description="malformed centre")
    doc.linetypes.add("DOTDASH", pattern="A,10,-2,0.2,-2", description="dash-dot under an unknown name")
    doc.linetypes.add("MYSTERY", pattern="A,5,-2,5,-2", description="equal dashes under an unknown name")
    msp = doc.modelspace()

    def line(name):
        return msp.add_line((0, 0), (10, 0), dxfattribs={"linetype": name})

    assert linetype_class(doc, line("BADCENTER")) == "center"  # the name wins over the broken pattern
    assert linetype_class(doc, line("DOTDASH")) == "center"
    assert linetype_class(doc, line("MYSTERY")) == "dashed"
    assert linetype_class(doc, line("CONTINUOUS")) == "solid"
    for name, want in (
        ("CENTER", "center"),
        ("CENTER2", "center"),
        ("HIDDEN", "dashed"),
        ("DASHED", "dashed"),
        ("ACAD_ISO02W100", "dashed"),
        ("ACAD_ISO04W100", "center"),
    ):
        doc.linetypes.add(name, pattern="A,10,-2", description=name)
        assert linetype_class(doc, line(name)) == want, name
