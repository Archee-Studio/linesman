"""`linesman build`, `linesman report` and `linesman rules`: splits, aggregation and the entrant rules text."""

import json

import pytest

from linesman.build import CANARY, build
from linesman.report import aggregate
from linesman.rules import rules_text


def test_dev_build_is_deterministic_and_frozen(tmp_path):
    a = build("dev", tmp_path / "a", per_family=1)
    b = build("dev", tmp_path / "b", per_family=1)
    assert a["tasks"] == b["tasks"] and a["freeze"] == b["freeze"]
    for task in a["tasks"]:
        folder = tmp_path / "a" / task
        assert CANARY in (folder / "task.md").read_text()
        assert (folder / "RULES.md").read_text() == rules_text()
    manifest = json.loads((tmp_path / "a" / "MANIFEST.json").read_text())
    assert manifest["freeze"] == a["freeze"] and manifest["canary"] == CANARY


def test_dev_build_covers_families_levels_and_review(tmp_path):
    m = build("dev", tmp_path / "dev", per_family=1)
    tasks = {t: json.loads((tmp_path / "dev" / t / "task.json").read_text()) for t in m["tasks"]}
    kinds = {(t["family"], t["track"], t["level"]) for t in tasks.values()}
    from linesman.families import FAMILIES

    for name in FAMILIES:
        assert (name, "calc-sheet", "given") in kinds
        assert (name, "calc-sheet", "calc") in kinds
        assert (name, "review", "given") in kinds
    review = next(t for t in tasks.values() if t["track"] == "review")
    assert (tmp_path / "dev" / review["id"] / "sheet.dxf").exists()


def test_test_split_needs_a_salt_and_never_collides_with_dev(tmp_path):
    with pytest.raises(SystemExit):
        build("test", tmp_path / "t")
    salt = tmp_path / "salt.txt"
    salt.write_text("top secret")
    dev = build("dev", tmp_path / "dev", per_family=1)
    test = build("test", tmp_path / "test", salt_file=salt, per_family=1)
    assert dev["tasks"].keys() & test["tasks"].keys() == set()
    from linesman.build import _inputs_hash

    dev_hashes = {
        _inputs_hash(json.loads(p.read_text()))
        for f in (tmp_path / "dev").iterdir()
        if (p := f / "inputs.json").exists()
    }
    test_hashes = {
        _inputs_hash(json.loads(p.read_text()))
        for f in (tmp_path / "test").iterdir()
        if (p := f / "inputs.json").exists()
    }
    assert dev_hashes & test_hashes == set()


def test_report_aggregates_runs(tmp_path):
    row = {"task": "t1", "valid": True, "passed": True, "parts": {"gate": 1.0, "dims": 0.5}}
    bad = {"task": "t1", "valid": False, "passed": False, "parts": {}}
    f1 = tmp_path / "sys-k1.json"
    f1.write_text(json.dumps([row]))
    f2 = tmp_path / "sys-k2.json"
    f2.write_text(json.dumps([bad]))
    report = aggregate([f1, f2])
    m = report["sys"]
    assert m["runs"] == 2 and m["valid_rate"] == 0.5 and m["pass_rate"] == 0.5
    assert m["score_on_valid"] == pytest.approx(0.75) and m["score_as_zero"] == pytest.approx(0.375)
    assert m["worst_of_k"] == 0.0 and m["median_of_k"] == pytest.approx(0.375)


def test_report_reads_system_and_run_fields(tmp_path):
    f = tmp_path / "r.json"
    f.write_text(
        json.dumps(
            {
                "system": "bench",
                "run": 0,
                "results": [{"task": "t", "valid": True, "passed": True, "parts": {"gate": 1.0}}],
            }
        )
    )
    assert "bench" in aggregate([f])


def test_rules_extracts_the_spec_section():
    text = rules_text()
    assert text.startswith("Sheet rules every entrant can read:")
    assert "attached" in text and "$INSUNITS = 4" in text
    assert text.rstrip().endswith("Save DXF R2018 or later.")
