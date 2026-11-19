"""Regressions for hostile input and sheet defects found in review."""

import ezdxf

from linesman.checks.review import match, read_findings
from linesman.families import FAMILIES
from linesman.families.drafting import drawing_area
from linesman.schema import Finding, SeededError
from linesman.sheet import LIMITS, MM, load


def test_nested_block_references_fail_the_gate(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = MM
    doc.modelspace().add_line((0, 0), (1, 1))
    previous = None
    for n in range(LIMITS.block_depth + 5):
        block = doc.blocks.new(f"B{n}")
        block.add_line((0, 0), (1, 0))
        if previous:
            block.add_blockref(previous, (0, 0))
        previous = f"B{n}"
    doc.modelspace().add_blockref(previous, (0, 0))
    doc.saveas(tmp_path / "sheet.dxf")
    sheet = load(tmp_path / "sheet.dxf")
    assert not sheet.valid and "nested" in sheet.errors[0]


def test_deeply_nested_findings_json_is_a_problem_not_a_crash(tmp_path):
    path = tmp_path / "findings.json"
    path.write_text("[" * 100_000)
    found, problem = read_findings(path)
    assert found == [] and problem


def test_review_match_is_maximum_not_greedy():
    errors = (SeededError(id="e1", kind="wrong-value", x=0, y=0), SeededError(id="e2", kind="wrong-value", x=20, y=0))
    findings = [Finding(kind="wrong-value", x=10, y=0), Finding(kind="wrong-value", x=-10, y=0)]
    assert len(match(errors, findings)) == 2


def test_no_dimension_text_doubles_its_symbol():
    for family in FAMILIES.values():
        doc = family.draw(family.sample(0))
        for block in doc.blocks:
            for e in block.query("MTEXT TEXT"):
                text = e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text
                assert "ØØ" not in text and "RR" not in text, (family.NAME, text)


def test_plate_dimensions_stay_inside_the_drawing_area():
    plate = FAMILIES["plate"]
    top = drawing_area()[3]
    for seed in range(200):
        for layout in range(3):
            doc = plate.draw(plate.sample(seed), layout)
            for dim in doc.modelspace().query("DIMENSION"):
                assert dim.dxf.defpoint.y <= top, seed
