"""Review track: findings match seeded errors of the same kind within 15 mm, one to one."""

import json

import pytest

from linesman.checks import CHECKS
from linesman.checks.review import REACH_MM, ReviewSheet, match, read_findings, review
from linesman.cli import make_review
from linesman.families import FAMILIES
from linesman.grade import grade, grade_files
from linesman.schema import CheckResult, Finding, SeededError, Task, Truth

TASK = Task(id="r", track="review", family="plate", seed=0)
ERRORS = (
    SeededError(id="e1", kind="wrong-value", x=100.0, y=100.0, dim_id="width"),
    SeededError(id="e2", kind="missing-dim", x=200.0, y=50.0, dim_id="pitch_x"),
)
TRUTH = Truth(views=(), dims=(), errors=ERRORS)


def _scores(findings, errors=ERRORS):
    truth = TRUTH.model_copy(update={"errors": errors})
    sheet = ReviewSheet(FAMILIES["plate"].draw(FAMILIES["plate"].sample(0)), findings=findings)
    return {r.id: r.score for r in review(sheet, TASK, truth)}


def test_exact_hits_score_one():
    found = [Finding(kind=e.kind, x=e.x, y=e.y) for e in ERRORS]
    assert _scores(found) == {"review.recall": 1.0, "review.precision": 1.0}


def test_inside_the_reach_matches_and_outside_does_not():
    assert _scores([Finding(kind="wrong-value", x=100 + REACH_MM, y=100)], ERRORS[:1])["review.recall"] == 1.0
    near_miss = [Finding(kind="wrong-value", x=100 + REACH_MM + 0.1, y=100)]
    assert _scores(near_miss, ERRORS[:1]) == {"review.recall": 0.0, "review.precision": 0.0}


def test_wrong_kind_does_not_match():
    found = [Finding(kind="missing-dim", x=100, y=100)]
    assert _scores(found, ERRORS[:1]) == {"review.recall": 0.0, "review.precision": 0.0}


def test_duplicate_findings_count_once_and_cost_precision():
    twice = [Finding(kind="wrong-value", x=100, y=100), Finding(kind="wrong-value", x=101, y=100)]
    assert _scores(twice, ERRORS[:1]) == {"review.recall": 1.0, "review.precision": 0.5}


def test_one_finding_cannot_cover_two_errors():
    close = (ERRORS[0], ERRORS[0].model_copy(update={"id": "e3", "x": 105.0}))
    assert _scores([Finding(kind="wrong-value", x=102, y=100)], close)["review.recall"] == 0.5


def test_pairing_prefers_nearest_and_is_one_to_one():
    close = (ERRORS[0], ERRORS[0].model_copy(update={"id": "e3", "x": 110.0}))
    found = [Finding(kind="wrong-value", x=111, y=100), Finding(kind="wrong-value", x=99, y=100)]
    pairs = match(close, found)
    assert len(pairs) == 2 and {id(f) for _, f in pairs} == {id(f) for f in found}


def test_no_findings_scores_zero():
    assert _scores([]) == {"review.recall": 0.0, "review.precision": 0.0}


def test_criticality():
    sheet = ReviewSheet(FAMILIES["plate"].draw(FAMILIES["plate"].sample(0)), findings=[])
    by_id = {r.id: r.critical for r in review(sheet, TASK, TRUTH)}
    assert by_id == {"review.recall": True, "review.precision": False}


@pytest.mark.parametrize(
    "content",
    ["not json", "{}", '[{"kind": "bogus", "x": 1, "y": 2}]', '[{"kind": "wrong-value", "x": NaN, "y": 2}]', "[1]"],
)
def test_invalid_findings_file_scores_zero(tmp_path, content):
    (tmp_path / "findings.json").write_text(content)
    found, problem = read_findings(tmp_path / "findings.json")
    assert found == [] and problem


def test_missing_findings_file(tmp_path):
    assert read_findings(tmp_path / "findings.json") == ([], "missing findings.json")


def test_track_guard_keeps_review_out_of_calc_sheet_and_calc_checks_out_of_review():
    fam = FAMILIES["plate"]
    inputs = fam.sample(0)
    calc = Task(id="c", track="calc-sheet", family="plate", seed=0)
    from linesman.sheet import parse

    sheet = parse(fam.draw(inputs))
    assert review in CHECKS and review(sheet, calc, fam.truth(inputs)) == []
    result = grade(sheet, calc, fam.truth(inputs))
    assert "review" not in result.parts and result.passed


def test_review_grading_ignores_calc_checks(monkeypatch, tmp_path):
    def always_fails(sheet, task, truth):
        return [CheckResult(id="dims.x", part="dims", critical=True, score=0)]

    monkeypatch.setattr("linesman.grade.CHECKS", (*CHECKS, always_fails))
    made = make_review("plate", range(1), tmp_path)
    task_dir = made[0]
    sub = tmp_path / "reference" / task_dir.name
    result = grade_files(task_dir, sub)
    assert result.passed and result.valid and [c.id for c in result.checks] == ["review.recall", "review.precision"]


def test_make_review_and_grade_round_trip(tmp_path):
    made = make_review("plate", range(4), tmp_path)
    assert len(made) == 4
    for folder in made:
        task = Task.model_validate_json((folder / "task.json").read_text())
        truth = Truth.model_validate_json((folder / "truth.json").read_text())
        assert task.track == "review" and 1 <= len(truth.errors) <= 3 and (folder / "sheet.dxf").is_file()
        sub = tmp_path / "reference" / folder.name
        assert grade_files(folder, sub).parts == {"review": 1.0}
        empty = tmp_path / "empty" / folder.name
        empty.mkdir(parents=True)
        missing = grade_files(folder, empty)
        assert not missing.valid and not missing.passed and missing.parts == {"review": 0.0}
        (empty / "findings.json").write_text("[]")
        none = grade_files(folder, empty)
        assert none.valid and not none.passed
        (empty / "findings.json").write_text(json.dumps([{"kind": "nope", "x": 0, "y": 0}]))
        assert not grade_files(folder, empty).valid
