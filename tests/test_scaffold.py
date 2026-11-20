"""The base contract: families draw valid sheets, the gate passes them and rejects bad files."""

from pathlib import Path

import ezdxf
import pytest

from linesman.checks import CHECKS
from linesman.families import FAMILIES
from linesman.grade import grade
from linesman.schema import SPEC_VERSION, Task
from linesman.sheet import load, number, parse

PARTS = ("gate", "views", "dims", "fits", "titleblock", "drafting")  # every listed part needs a check


@pytest.mark.parametrize("family", sorted(FAMILIES))
@pytest.mark.parametrize("layout", [0, 1, 2])
def test_reference_and_variants_pass_the_gate(family, layout, tmp_path):
    fam = FAMILIES[family]
    inputs = fam.sample(7)
    path = tmp_path / "sheet.dxf"
    fam.draw(inputs, layout).saveas(path)
    sheet = load(path)
    assert sheet.valid, sheet.errors
    assert sheet.dims and sheet.texts
    result = grade(sheet, Task(id="t", track="calc-sheet", family=family, seed=7), fam.truth(inputs))
    assert result.passed, [c for c in result.checks if not c.passed]


def test_gate_rejects_missing_wrong_units_and_empty(tmp_path):
    assert not load(tmp_path / "nothing.dxf").valid
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 1  # inches
    doc.modelspace().add_line((0, 0), (1, 1))
    assert "units" in parse(doc).errors[0]
    empty = ezdxf.new("R2018")
    empty.header["$INSUNITS"] = 4
    assert parse(empty).errors == ["no geometry"]


def test_every_part_has_a_check():
    sheet = parse(FAMILIES["plate"].draw(FAMILIES["plate"].sample(1)))
    truth = FAMILIES["plate"].truth(FAMILIES["plate"].sample(1))
    parts = {
        r.part
        for check in CHECKS
        for r in check(sheet, Task(id="t", track="calc-sheet", family="plate", seed=1), truth)
    }
    assert set(PARTS) <= parts


@pytest.mark.parametrize(
    "text, value",
    [
        ("%%c40H7", 40.0),
        ("4x %%c6.6", 6.6),
        ("R12", 12.0),
        ("30°", 30.0),
        ("12,5", 12.5),
        ("1 x 45 deg (4X)", 1.0),
        ("1.5x45%%d", 1.5),
        ("2 × 45°", 2.0),
        ("{\\fArial;%%c25}", 25.0),
        ("", None),
        ("d - t1 = 30", 30.0),
        ("Ø25 H8", 25.0),
        ("⌀25 H8", 25.0),
    ],
)
def test_number_reads_dimension_text(text, value):
    assert number(text) == value


def test_reference_dimensions_show_truth_values():
    fam = FAMILIES["plate"]
    inputs = fam.sample(3)
    sheet = parse(fam.draw(inputs))
    shown = sorted(round(d.value, 3) for d in sheet.dims)
    wanted = sorted(round(d.value, 3) for d in fam.truth(inputs).dims)
    assert shown == wanted


def test_spec_title_states_the_schema_version():
    spec = Path(__file__).parents[1] / "docs" / "spec.md"
    assert spec.read_text().splitlines()[0] == f"# Linesman spec {SPEC_VERSION}"
