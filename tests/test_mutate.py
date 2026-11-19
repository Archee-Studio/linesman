"""Every mutant has a witness in the saved file; a mutation without one is not counted."""

import random

import pytest

from linesman import mutate
from linesman.families import FAMILIES
from linesman.mutate import MUTANTS, Skip, apply, roundtrip, seed_errors
from linesman.sheet import load, parse

PLATE = FAMILIES["plate"]
SEEDS = range(6)


def _make(name: str, seed: int):
    inputs = PLATE.sample(seed)
    doc = PLATE.draw(inputs)
    truth = PLATE.truth(inputs)
    return doc, truth, apply(name, doc, truth, random.Random(seed))


def _saved(doc, tmp_path):
    path = tmp_path / "sheet.dxf"
    doc.saveas(path)
    sheet = load(path)
    assert sheet.valid, sheet.errors
    return sheet


def _first(name: str):
    for seed in SEEDS:
        try:
            return (seed, *_make(name, seed))
        except Skip:
            continue
    pytest.fail(f"{name} never applied to plate")


def test_registry_rows_are_complete():
    assert set(MUTANTS) == {"wrong-value", "missing-dim", "wrong-fit", "wrong-title-field", "missing-view"}
    for name, mutant in MUTANTS.items():
        assert callable(mutant.run) and callable(mutant.witness), name


def test_wrong_value_changes_one_displayed_value(tmp_path):
    seed, doc, truth, m = _first("wrong-value")
    before, after = parse(doc), _saved(m.doc, tmp_path)
    assert m.targets == ("dims.recall",) and m.error.kind == "wrong-value"
    changed = [(b, a) for b, a in zip(before.dims, after.dims, strict=True) if abs(a.value - b.value) > 0.01]
    assert len(changed) == 1 and len(after.dims) == len(before.dims)
    old, new = changed[0]
    want = next(d for d in truth.dims if d.id == m.error.dim_id)
    assert abs(old.value - want.value) < 0.01 and 0.8 < new.value / old.value < 1.3
    assert abs(new.x - m.error.x) < 1.0 and abs(new.y - m.error.y) < 1.0
    assert new.value not in {round(d.value, 2) for d in truth.dims}


def test_missing_dim_removes_one_dimension(tmp_path):
    _, doc, truth, m = _first("missing-dim")
    before, after = parse(doc), _saved(m.doc, tmp_path)
    assert m.targets == ("dims.recall",)
    assert len(after.dims) == len(before.dims) - 1
    want = next(d for d in truth.dims if d.id == m.error.dim_id)
    assert not [d for d in after.dims if d.kind == want.kind and abs(d.value - want.value) < 0.01]


def test_wrong_fit_changes_the_designation(tmp_path):
    _, doc, truth, m = _first("wrong-fit")
    after = _saved(m.doc, tmp_path)
    assert m.targets == ("fits.shown",)
    assert any("H7" in d.text for d in parse(doc).dims)
    assert not any("H7" in d.text for d in after.dims) and any("H8" in d.text for d in after.dims)
    assert all(abs(a.value - b.value) < 0.01 for a, b in zip(after.dims, parse(doc).dims, strict=True))


def test_wrong_title_field_changes_the_material(tmp_path):
    _, doc, truth, m = _first("wrong-title-field")
    after = _saved(m.doc, tmp_path)
    assert m.targets == ("titleblock.fields",)
    assert truth.title["material"] in [t.text for t in parse(doc).texts]
    assert truth.title["material"] not in [t.text for t in after.texts]
    assert len(after.texts) == len(parse(doc).texts)


def test_missing_view_deletes_a_views_geometry(tmp_path):
    pytest.importorskip("linesman.regions")
    _, doc, truth, m = _first("missing-view")
    assert m.targets == ("views.present",)
    assert len(_saved(m.doc, tmp_path).geometry) < len(parse(doc).geometry)


def test_apply_leaves_the_original_untouched_and_is_deterministic():
    inputs = PLATE.sample(2)
    doc, truth = PLATE.draw(inputs), PLATE.truth(inputs)
    before = [(d.value, d.text) for d in parse(doc).dims]
    first = apply("wrong-value", doc, truth, random.Random(5))
    second = apply("wrong-value", doc, truth, random.Random(5))
    assert [(d.value, d.text) for d in parse(doc).dims] == before
    assert first.error == second.error
    assert [(d.value, d.text) for d in parse(first.doc).dims] == [(d.value, d.text) for d in parse(second.doc).dims]


def test_a_mutation_without_a_witness_is_not_counted(monkeypatch):
    inputs = PLATE.sample(1)
    doc, truth = PLATE.draw(inputs), PLATE.truth(inputs)
    row = mutate.Mutant(MUTANTS["wrong-title-field"].run, lambda *_: False)
    monkeypatch.setitem(MUTANTS, "wrong-title-field", row)
    with pytest.raises(Skip, match="no witness"):
        apply("wrong-title-field", doc, truth, random.Random(1))


def test_inapplicable_mutants_skip():
    inputs = PLATE.sample(1)
    truth = PLATE.truth(inputs).model_copy(update={"dims": (), "title": {}})
    for name in ("wrong-value", "missing-dim", "wrong-fit", "wrong-title-field"):
        with pytest.raises(Skip):
            apply(name, PLATE.draw(inputs), truth, random.Random(1))


@pytest.mark.parametrize("seed", range(8))
def test_seed_errors_plants_one_to_three_distinct_errors(seed):
    inputs = PLATE.sample(seed)
    doc, truth = PLATE.draw(inputs), PLATE.truth(inputs)
    mutated, errors = seed_errors(doc, truth, random.Random(seed))
    assert 1 <= len(errors) <= 3
    assert [e.id for e in errors] == [f"e{i + 1}" for i in range(len(errors))]
    assert len({e.kind for e in errors}) == len(errors)
    touched = [e.dim_id for e in errors if e.dim_id]
    assert len(set(touched)) == len(touched)
    assert len(roundtrip(mutated).modelspace()) > 0


def test_targets_are_known_check_ids():
    known = {"dims.recall", "fits.shown", "titleblock.fields", "views.present"}
    for name in set(MUTANTS) - {"missing-view"}:
        assert set(_first(name)[3].targets) <= known, name
