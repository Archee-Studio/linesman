"""Every family: deterministic samples, sheets that pass the gate, dimensions equal to the truth, views that fit."""

import json

import ezdxf.bbox
import pytest

from linesman.families import FAMILIES
from linesman.families.drafting import drawing_area
from linesman.grade import grade
from linesman.schema import Task
from linesman.sheet import load, parse

SEEDS = range(20)
LAYOUTS = (0, 1, 2)
TOL = 0.01


def _boxes_in_area_and_apart(boxes):
    x0, y0, x1, y1 = drawing_area()
    for x, y, w, h in boxes.values():
        assert x0 <= x and y0 <= y and x + w <= x1 and y + h <= y1, (x, y, w, h)
    items = list(boxes.items())
    for n, (a, (ax, ay, aw, ah)) in enumerate(items):
        for b, (bx, by, bw, bh) in items[n + 1 :]:
            apart = ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay
            assert apart, f"views {a} and {b} overlap"


@pytest.mark.parametrize("family", sorted(FAMILIES))
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("layout", LAYOUTS)
def test_sheet_matches_truth(family, seed, layout, tmp_path):
    fam = FAMILIES[family]
    inputs = fam.sample(seed)
    truth = fam.truth(inputs)
    path = tmp_path / "sheet.dxf"
    fam.draw(inputs, layout).saveas(path)
    sheet = load(path)
    assert sheet.valid, sheet.errors
    result = grade(sheet, Task(id="t", track="calc-sheet", family=family, seed=seed), truth)
    assert result.passed, [c for c in result.checks if not c.passed]
    shown = sorted(round(d.value, 3) for d in sheet.dims)
    assert shown == sorted(round(d.value, 3) for d in truth.dims)
    texts = {t.text for t in sheet.texts}
    assert set(truth.title.values()) <= texts
    assert truth.scale == "1:1" and truth.title["scale"] == truth.scale


@pytest.mark.parametrize("family", sorted(FAMILIES))
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("layout", LAYOUTS)
def test_views_fit_apart_and_hold_the_geometry(family, seed, layout):
    fam = FAMILIES[family]
    inputs = fam.sample(seed)
    truth = fam.truth(inputs)
    boxes = fam.views(inputs, layout)
    assert {v.name for v in truth.views} == set(boxes)
    for v in truth.views:
        assert boxes[v.name][2:] == pytest.approx((v.width, v.height))
    _boxes_in_area_and_apart(boxes)
    # every outline, hidden and centre entity lies inside one view and the views are exactly filled
    drawn = {name: [] for name in boxes}
    for e in fam.draw(inputs, layout).modelspace():
        if e.dxf.layer not in ("outline", "hidden", "center"):
            continue
        box = ezdxf.bbox.extents([e])
        homes = [
            n
            for n, (x, y, w, h) in boxes.items()
            if x - TOL <= box.extmin.x
            and box.extmax.x <= x + w + TOL
            and y - TOL <= box.extmin.y <= y + h + TOL
            and box.extmax.y <= y + h + TOL
        ]
        assert len(homes) == 1, f"{e.dxftype()} on {e.dxf.layer} is in {homes}"
        drawn[homes[0]].append(box)
    for name, (x, y, w, h) in boxes.items():
        union = ezdxf.bbox.BoundingBox()
        for box in drawn[name]:
            union.extend(box)
        assert union.size.x == pytest.approx(w, abs=TOL) and union.size.y == pytest.approx(h, abs=TOL), name
        assert union.extmin.x == pytest.approx(x, abs=TOL) and union.extmin.y == pytest.approx(y, abs=TOL), name


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_samples_are_deterministic_and_differ(family):
    fam = FAMILIES[family]
    samples = [json.dumps(fam.sample(s), sort_keys=True) for s in SEEDS]
    assert samples == [json.dumps(fam.sample(s), sort_keys=True) for s in SEEDS]
    assert len(set(samples)) >= 10
    for seed in (0, 1, 2):
        inputs = fam.sample(seed)
        assert fam.truth(inputs) == fam.truth(inputs)
        assert fam.request(inputs) == fam.request(inputs)
        assert inputs["material"] in fam.request(inputs)


@pytest.mark.parametrize("family", sorted(FAMILIES))
@pytest.mark.parametrize("seed", SEEDS)
def test_truth_is_consistent(family, seed):
    fam = FAMILIES[family]
    truth = fam.truth(fam.sample(seed))
    names = {v.name for v in truth.views}
    ids = [d.id for d in truth.dims]
    assert len(ids) == len(set(ids))
    assert {d.view for d in truth.dims} <= names
    assert all(d.value > 0 for d in truth.dims)


@pytest.mark.parametrize("seed", SEEDS)
def test_gear_blank_tip_diameter_follows_the_calculation(seed):
    fam = FAMILIES["gear-blank"]
    inputs = fam.sample(seed)
    tip = {d.id: d.value for d in fam.truth(inputs).dims}["tip"]
    assert tip == pytest.approx(inputs["module"] * (inputs["teeth"] + 2))


def test_every_family_is_listed():
    assert set(FAMILIES) == {"plate", "shaft", "flange", "bushing", "gear-blank", "bracket"}
    sheet = parse(FAMILIES["shaft"].draw(FAMILIES["shaft"].sample(0)))
    assert {d.kind for d in sheet.dims} == {"diameter", "linear"}
