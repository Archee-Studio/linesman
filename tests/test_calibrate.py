"""Calibration on the plate family with the registered checks: references pass, mutants fail, empty sheets score 0."""

from linesman import calibrate as cal
from linesman.mutate import MUTANTS


def _case(report, name, seed=0):
    return next(c for c in report["cases"] if c["case"] == name and c["seed"] == seed)


def test_plate_calibration_with_the_checks_on_dev():
    report = cal.calibrate(["plate"], 2, require_targets=False)
    registered = set(report["checks"])
    for case in report["cases"]:
        if case["case"] in ("reference", "variant", "empty", "review"):
            assert case["ok"], case
        if case["case"] in MUTANTS:
            targets = [
                t for t in ("dims.recall", "fits.shown", "titleblock.fields", "views.present") if t in registered
            ]
            assert case["ok"] or not targets, case
    assert "gate.opens" in registered


def test_plate_calibration_passes_with_the_registered_checks():
    report = cal.calibrate(["plate", "gear-blank", "bracket"], 3)
    assert report["ok"], report["failures"]
    applied = {n for n, m in report["mutants"].items() if m["applied"]}
    assert set(MUTANTS) <= applied
    assert _case(report, "empty")["mean"] == 0.0
