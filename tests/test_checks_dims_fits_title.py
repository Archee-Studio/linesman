"""Dimension, fit and title block checks: references score 1, each hand-built defect fails exactly its check."""

import ezdxf
import pytest

from linesman.checks.dims import dims, kind_of
from linesman.checks.fits import deviations, fits, shows
from linesman.checks.titleblock import titleblock
from linesman.families import FAMILIES
from linesman.families.drafting import frame, new_sheet
from linesman.schema import Dim, Task, Truth, View
from linesman.sheet import Dimension, Sheet, parse

PLATE = FAMILIES["plate"]
INPUTS = PLATE.sample(7)
TRUTH = PLATE.truth(INPUTS)
TASK = Task(id="t", track="calc-sheet", family="plate", seed=7)
CHECK_IDS = ("dims.recall", "dims.precision", "fits.shown", "titleblock.fields")


def scores(sheet: Sheet, truth: Truth = TRUTH) -> dict[str, float]:
    return {r.id: r.score for check in (dims, fits, titleblock) for r in check(sheet, TASK, truth)}


def failing(sheet: Sheet, truth: Truth = TRUTH) -> set[str]:
    return {check for check, score in scores(sheet, truth).items() if score < 1.0}


def plate_doc(layout: int = 0):
    return PLATE.draw(INPUTS, layout)


def dimension_entities(doc):
    return [e for e in doc.modelspace() if e.dxftype() == "DIMENSION"]


def dim(text: str = "", value: float = 40.0, kind: str = "diameter") -> Dimension:
    return Dimension(kind, value, text, 0.0, 0.0, "1")


@pytest.mark.parametrize("seed", [1, 2, 3, 7, 11])
@pytest.mark.parametrize("layout", [0, 1, 2])
def test_reference_and_variants_score_one_everywhere(seed, layout):
    inputs = PLATE.sample(seed)
    result = scores(parse(PLATE.draw(inputs, layout)), PLATE.truth(inputs))
    assert result == dict.fromkeys(CHECK_IDS, 1.0)


def test_wrong_value_fails_recall_not_fits_or_title():
    doc = plate_doc()
    width = next(
        e for e in dimension_entities(doc) if e.dxf.text == "<>" and abs(e.get_measurement() - INPUTS["width"]) < 1e-6
    )
    width.dxf.text = f"{INPUTS['width'] + 5:g}"
    sheet = parse(doc)
    assert failing(sheet) == {"dims.recall", "dims.precision"}
    assert any("width" in line for line in dims(sheet, TASK, TRUTH)[0].detail)
    assert scores(sheet)["fits.shown"] == 1.0 and scores(sheet)["titleblock.fields"] == 1.0


def test_value_within_tolerance_still_matches():
    doc = plate_doc()
    for e in dimension_entities(doc):
        if e.dxf.text == "<>" and abs(e.get_measurement() - INPUTS["width"]) < 1e-6:
            e.dxf.text = f"{INPUTS['width'] + 0.004:g}"
    assert failing(parse(doc)) == set()


def test_missing_dimension_fails_recall_only():
    doc = plate_doc()
    msp = doc.modelspace()
    thickness = next(e for e in dimension_entities(doc) if abs(e.get_measurement() - INPUTS["thickness"]) < 1e-6)
    msp.delete_entity(thickness)
    sheet = parse(doc)
    assert failing(sheet) == {"dims.recall"}
    assert dims(sheet, TASK, TRUTH)[0].detail == ("missing thickness",)
    assert scores(sheet)["dims.recall"] == pytest.approx(6 / 7)


def test_wrong_fit_fails_fits_only():
    doc = plate_doc()
    bore = next(e for e in dimension_entities(doc) if e.dxf.text == "<>H7")
    bore.dxf.text = "<>H8"
    assert failing(parse(doc)) == {"fits.shown"}


def test_missing_fit_text_fails_fits_only():
    doc = plate_doc()
    bore = next(e for e in dimension_entities(doc) if e.dxf.text == "<>H7")
    bore.dxf.text = ""
    assert failing(parse(doc)) == {"fits.shown"}


def test_missing_material_fails_titleblock_only():
    doc = plate_doc()
    msp = doc.modelspace()
    material = next(e for e in msp if e.dxftype() == "TEXT" and e.dxf.text == INPUTS["material"])
    msp.delete_entity(material)
    sheet = parse(doc)
    assert failing(sheet) == {"titleblock.fields"}
    assert titleblock(sheet, TASK, TRUTH)[0].detail == ("missing material",)
    assert scores(sheet)["titleblock.fields"] == pytest.approx(2 / 3)


def test_extra_dimension_fails_precision_only():
    doc = plate_doc()
    doc.modelspace().add_linear_dim(
        base=(100, 30), p1=(100, 60), p2=(133, 60), dxfattribs={"layer": "dims"}, dimstyle="ISO-35"
    ).render()
    sheet = parse(doc)
    assert failing(sheet) == {"dims.precision"}
    assert scores(sheet)["dims.precision"] == pytest.approx(7 / 8)
    assert dims(sheet, TASK, TRUTH)[1].detail == ("unmatched linear 33",)


def test_one_sheet_dimension_cannot_satisfy_two_required_dimensions():
    truth = Truth(
        views=(View(name="front", width=50, height=50),),
        dims=(
            Dim(id="a", kind="linear", value=50, view="front"),
            Dim(id="b", kind="linear", value=50, view="front"),
        ),
    )
    sheet = Sheet(ezdxf.new(), dims=[dim(kind="linear", value=50.0)])
    assert dims(sheet, TASK, truth)[0].score == 0.5
    sheet.dims.append(dim(kind="linear", value=50.004))
    assert [r.score for r in dims(sheet, TASK, truth)] == [1.0, 1.0]


def test_kind_must_agree_and_a_diameter_mark_makes_a_linear_dimension_a_diameter():
    truth = Truth(views=(), dims=(Dim(id="d", kind="diameter", value=40, view="front"),))
    assert dims(Sheet(ezdxf.new(), dims=[dim("%%c<>", 40.0, "linear")]), TASK, truth)[0].score == 1.0
    assert dims(Sheet(ezdxf.new(), dims=[dim("Ø40", 40.0, "linear")]), TASK, truth)[0].score == 1.0
    assert dims(Sheet(ezdxf.new(), dims=[dim("", 40.0, "linear")]), TASK, truth)[0].score == 0.0
    assert dims(Sheet(ezdxf.new(), dims=[dim("", 40.0, "radius")]), TASK, truth)[0].score == 0.0
    assert kind_of(dim("%%c40", kind="linear")) == "diameter"


def test_angular_values_use_the_degree_tolerance():
    truth = Truth(views=(), dims=(Dim(id="a", kind="angular", value=30, view="front"),))
    assert dims(Sheet(ezdxf.new(), dims=[dim(kind="angular", value=30.08)]), TASK, truth)[0].score == 1.0
    assert dims(Sheet(ezdxf.new(), dims=[dim(kind="angular", value=30.2)]), TASK, truth)[0].score == 0.0


def test_empty_sheet_scores_zero_and_unrequired_checks_score_nothing():
    empty = Sheet(ezdxf.new())
    assert scores(empty) == {"dims.recall": 0.0, "dims.precision": 0.0, "fits.shown": 0.0, "titleblock.fields": 0.0}
    bare = Truth(views=(), dims=())
    assert scores(empty, bare) == {}  # a check that does not apply returns nothing, never a free 1.0


@pytest.mark.parametrize(
    "text, fit, nominal, expected",
    [
        ("<>H7", "H7", 40, True),
        ("%%c40H7", "H7", 40, True),
        ("%%c<>H7", "H7", 40, True),
        ("<>H8", "H7", 40, False),
        ("<>H71", "H7", 40, False),
        ("<>g6", "H6", 40, False),
        ("<>", "H7", 40, False),
        ("%%c<>\\S+0.025^0;", "H7", 40, True),
        ("%%c<>\\S+0.025^ 0;", "H7", 40, True),
        ("%%c<>\\S+0.035^0;", "H7", 40, False),
        ("<> +0.025/0", "H7", 40, True),
        ("<> +0.0255/0", "H7", 40, True),
        ("<> +0.025/-0.010", "H7", 40, False),
        ("<> +0.025 0", "H7", 40, True),
        ("40 -0.009/-0.025", "g6", 40, True),
        ("40 -0.009/−0.025", "g6", 40, True),
        ("\\S-0.009^-0.025;", "g6", 40, True),
        ("40 -0.009/-0.020", "g6", 40, False),
        ("40 +0.018/+0.002", "k6", 40, True),
        ("40 ±0.008", "js6", 40, True),
        ("40 %%p0.008", "js6", 40, True),
        ("40 ±0.012", "js6", 40, False),
        ("<>", "g6", 40, False),
    ],
)
def test_fit_shown_by_designation_or_deviations(text, fit, nominal, expected):
    assert shows(Dim(id="d", kind="diameter", value=nominal, view="front", fit=fit), dim(text, nominal)) is expected


def test_deviations_reads_common_stacked_text():
    assert deviations("\\S+0.025^0;") == (0.025, 0.0)
    assert deviations("+0.025/0") == (0.025, 0.0)
    assert deviations("40") is None
    assert deviations("40H7") is None


def test_fit_credit_goes_to_the_dimension_that_shows_it():
    truth = Truth(
        views=(),
        dims=(
            Dim(id="plain", kind="diameter", value=40, view="front"),
            Dim(id="fitted", kind="diameter", value=40, view="front", fit="H7"),
        ),
    )
    sheet = Sheet(ezdxf.new(), dims=[dim("", 40.0), dim("<>H7", 40.0)])
    assert [r.score for r in dims(sheet, TASK, truth)] == [1.0, 1.0]
    assert fits(sheet, TASK, truth)[0].score == 1.0
    assert fits(Sheet(ezdxf.new(), dims=[dim("", 40.0), dim("", 40.0)]), TASK, truth)[0].score == 0.0


def test_titleblock_ignores_case_whitespace_and_formatting_but_not_substrings():
    truth = Truth(views=(), dims=(), title={"part": "Mounting plate", "scale": "1:1", "material": "S235"})
    doc = new_sheet()
    frame(doc, {})  # frame and an empty title block; texts go inside it
    msp = doc.modelspace()
    msp.add_mtext("{\\fArial|b1;MOUNTING   PLATE}\\PMaterial: s235").set_location((240, 40))
    msp.add_text("SCALE 1:10").set_placement((240, 20))
    msp.add_text("Scale 1:1").set_placement((100, 150))  # outside the title block: does not count
    sheet = parse(doc)
    result = titleblock(sheet, TASK, truth)[0]
    assert result.detail == ("missing scale",)
    msp.add_text("Scale 1:1").set_placement((240, 14))
    assert titleblock(parse(doc), TASK, truth)[0].score == 1.0


def test_hole_positions_from_the_edges_count_as_well_as_the_pitch():
    """Found by the first practice run: dimensioning holes from the edges is as valid as their pitch."""
    truth = Truth(
        views=(),
        dims=(Dim(id="pitch_x", kind="linear", value=120.0, view="front", alt=(10.0,)),),
    )
    edge = Sheet(ezdxf.new(), dims=[Dimension("linear", 10.0, "10", 0, 0, "1")])
    assert scores(edge, truth)["dims.recall"] == 1.0
    wrong = Sheet(ezdxf.new(), dims=[Dimension("linear", 12.0, "12", 0, 0, "1")])
    assert scores(wrong, truth)["dims.recall"] == 0.0
