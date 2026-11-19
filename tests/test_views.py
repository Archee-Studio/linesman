"""Views: regions found without tags, and the three view checks calibrated on the plate and hand-built bad sheets."""

import ezdxf
import pytest

from linesman.checks.views import views
from linesman.families import FAMILIES
from linesman.families.drafting import frame, new_sheet
from linesman.regions import regions
from linesman.schema import Task, Truth, View
from linesman.sheet import parse

PLATE = FAMILIES["plate"]
TASK = Task(id="t", track="calc-sheet", family="plate", seed=7)
W, H, T = 100.0, 60.0, 10.0
TRUTH = Truth(views=(View(name="front", width=W, height=H), View(name="top", width=W, height=T)), dims=())


def rect(msp, x, y, w, h, layer="outline"):
    msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True, dxfattribs={"layer": layer})


def sheet(top=(40.0, 60.0, W, T), front=(40.0, 120.0), furniture=True):
    """A front view with a bore and a top view with hidden lines; `top` is (x, y, w, h), None leaves it out."""
    doc = new_sheet()
    msp = doc.modelspace()
    if furniture:
        frame(doc, {"part": "p", "material": "m", "scale": "1:1"})
    fx, fy = front
    rect(msp, fx, fy, W, H)
    msp.add_circle((fx + W / 2, fy + H / 2), 12)
    if top:
        tx, ty, tw, th = top
        rect(msp, tx, ty, tw, th)
        msp.add_line((tx + 30, ty), (tx + 30, ty + th), dxfattribs={"layer": "hidden"})
    return parse(doc)


def scores(s, truth=TRUTH):
    return {r.id: r.score for r in views(s, TASK, truth)}


GOOD = {"views.present": 1.0, "views.aligned": 1.0, "views.first_angle": 1.0}


@pytest.mark.parametrize("layout", [0, 1, 2])
def test_plate_reference_and_layouts_score_one(layout):
    inputs = PLATE.sample(7)
    s = parse(PLATE.draw(inputs, layout))
    assert scores(s, PLATE.truth(inputs)) == GOOD


def test_hand_built_good_sheet_scores_one():
    assert scores(sheet()) == GOOD


def test_missing_top_view_fails_only_present():
    assert scores(sheet(top=None)) == {**GOOD, "views.present": 0.5}


def test_top_view_of_wrong_thickness_fails_only_present():
    assert scores(sheet(top=(40.0, 60.0, W, T + 2))) == {**GOOD, "views.present": 0.5}


def test_top_view_shifted_sideways_fails_only_aligned():
    assert scores(sheet(top=(55.0, 60.0, W, T))) == {**GOOD, "views.aligned": 0.0}


def test_top_view_above_front_is_third_angle_and_fails_only_first_angle():
    assert scores(sheet(top=(40.0, 200.0, W, T))) == {**GOOD, "views.first_angle": 0.0}


def test_left_view_beside_the_front():
    truth = Truth(views=(*TRUTH.views, View(name="left", width=T, height=H)), dims=())

    def build(left_x):
        doc = new_sheet()
        msp = doc.modelspace()
        frame(doc, {"part": "p"})
        rect(msp, 100, 130, W, H)
        rect(msp, 100, 90, W, T)
        rect(msp, left_x, 130, T, H)
        return parse(doc)

    assert scores(build(230.0), truth) == GOOD
    assert scores(build(60.0), truth)["views.first_angle"] == 0.5  # left view drawn on the left is third angle


def test_scale_applies_to_the_truth_size():
    half = TRUTH.model_copy(update={"scale": "1:2"})
    doc = new_sheet()
    msp = doc.modelspace()
    frame(doc, {"part": "p"})
    rect(msp, 100, 150, W / 2, H / 2)
    rect(msp, 100, 120, W / 2, T / 2)
    assert scores(parse(doc), half) == GOOD
    assert scores(sheet(), half)["views.present"] == 0.0


def test_centre_line_overshoot_does_not_change_the_view_size():
    doc = new_sheet()
    msp = doc.modelspace()
    frame(doc, {"part": "p"})
    rect(msp, 100, 130, W, H)
    msp.add_line((150, 125), (150, 195), dxfattribs={"layer": "center"})
    rect(msp, 100, 90, W, T)
    assert scores(parse(doc)) == GOOD


def test_frame_and_title_block_are_never_regions():
    s = sheet()
    found = regions(s)
    assert [(round(r.width), round(r.height)) for r in found] == [(100, 60), (100, 10)]
    handles = {h for r in found for h in r.handles}
    assert all(e.dxf.layer != "frame" for r in found for e in r.entities)
    assert len(handles) == len(s.geometry) - sum(e.dxf.layer == "frame" for e in s.geometry)


def test_frame_and_title_block_alone_hold_no_view():
    s = parse(_frame_only())
    assert regions(s) == []
    assert scores(s) == {"views.present": 0.0, "views.aligned": 0.0, "views.first_angle": 0.0}


def _frame_only():
    doc = new_sheet()
    frame(doc, {"part": "p", "material": "m", "scale": "1:1"})
    return doc


def test_plate_regions_hold_holes_and_hidden_lines_with_their_view():
    inputs = PLATE.sample(7)
    found = regions(parse(PLATE.draw(inputs)))
    assert len(found) == 2
    front, top = found
    assert (front.width, front.height) == (inputs["width"], inputs["height"])
    assert len(front.entities) == 6 and len(top.entities) == 3


def test_sheet_without_frame_keeps_every_view():
    s = sheet(furniture=False)
    assert len(regions(s)) == 2
    assert scores(s) == GOOD


def test_frame_drawn_as_four_lines_is_still_removed():
    doc = new_sheet()
    msp = doc.modelspace()
    for a, b in (((20, 10), (410, 10)), ((410, 10), (410, 287)), ((410, 287), (20, 287)), ((20, 287), (20, 10))):
        msp.add_line(a, b)
    rect(msp, 100, 130, W, H)
    rect(msp, 100, 90, W, T)
    assert len(regions(parse(doc))) == 2


def test_centre_lines_on_a_center_layer_drawn_continuous_do_not_grow_the_view():
    """Found by the first practice run: centre lines on a CENTER layer with a continuous linetype."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4
    doc.layers.add("CENTER", linetype="Continuous")
    msp = doc.modelspace()
    msp.add_lwpolyline([(50, 50), (135, 50), (135, 95), (50, 95)], close=True)
    msp.add_line((44, 72.5), (141, 72.5), dxfattribs={"layer": "CENTER"})
    from linesman.regions import regions
    from linesman.sheet import parse

    (region,) = regions(parse(doc))
    assert (round(region.width, 3), round(region.height, 3)) == (85.0, 45.0)
