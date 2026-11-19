"""ISO 286-1 deviations against values read from the standard's tables (micrometres in the table, mm here)."""

import pytest

from linesman import iso286
from linesman.iso286 import limits

# designation, nominal, upper (um), lower (um)
KNOWN = [
    ("H7", 40, 25, 0),
    ("H6", 10, 9, 0),
    ("H7", 18, 18, 0),  # 18 belongs to 10-18
    ("H7", 18.01, 21, 0),
    ("H7", 30, 21, 0),  # 30 belongs to 18-30
    ("H7", 30.01, 25, 0),
    ("H7", 3, 10, 0),
    ("H7", 3.01, 12, 0),
    ("H7", 500, 63, 0),
    ("H8", 40, 39, 0),
    ("H9", 100, 87, 0),
    ("H11", 40, 160, 0),
    ("H5", 1, 4, 0),
    ("JS7", 40, 12.5, -12.5),
    ("JS6", 40, 8, -8),
    ("K7", 40, 7, -18),
    ("K6", 40, 3, -13),
    ("K8", 40, 12, -27),
    ("K9", 40, 0, -62),
    ("M7", 40, 0, -25),
    ("M6", 300, -11, -43),
    ("M6", 250, -8, -37),
    ("N7", 40, -8, -33),
    ("N9", 40, -17, -79),
    ("P7", 40, -17, -42),
    ("P6", 40, -21, -37),
    ("F8", 40, 64, 25),
    ("G7", 40, 34, 9),
    ("E9", 40, 112, 50),
    ("D10", 40, 180, 80),
    ("h6", 40, 0, -16),
    ("h7", 40, 0, -25),
    ("h11", 40, 0, -160),
    ("g6", 40, -9, -25),
    ("f7", 40, -25, -50),
    ("e8", 40, -50, -89),
    ("d9", 40, -80, -142),
    ("js6", 40, 8, -8),
    ("k6", 40, 18, 2),
    ("k6", 100, 25, 3),
    ("k8", 40, 39, 0),
    ("m6", 40, 25, 9),
    ("n6", 40, 33, 17),
    ("p6", 40, 42, 26),
    ("r6", 40, 50, 34),
    ("r6", 60, 60, 41),  # 50-65
    ("r6", 70, 62, 43),  # 65-80
    ("s6", 40, 59, 43),
    ("s6", 28, 48, 35),  # 24-30
    ("s6", 60, 72, 53),
    ("g6", 3, -2, -8),
    ("g6", 3.01, -4, -12),
]


@pytest.mark.parametrize("designation, nominal, upper, lower", KNOWN)
def test_limits_match_the_standard(designation, nominal, upper, lower):
    assert limits(designation, nominal) == pytest.approx((upper / 1000, lower / 1000), abs=1e-9)


def test_examples_from_the_brief():
    assert limits("H7", 40) == (0.025, 0.0)
    assert limits("g6", 40) == (-0.009, -0.025)
    assert limits("k6", 40) == (0.018, 0.002)


@pytest.mark.parametrize("designation", ["", "H", "7", "H4", "H12", "X7", "h", "Hh7", "A7", "hh6", "H7x", "S7", "R7"])
def test_unknown_designations_raise(designation):
    with pytest.raises(ValueError):
        limits(designation, 40)


@pytest.mark.parametrize("nominal", [0, -5, 500.01, 1000])
def test_sizes_outside_the_tables_raise(nominal):
    with pytest.raises(ValueError):
        limits("H7", nominal)


def test_tables_have_one_column_per_range():
    assert all(len(row) == len(iso286.RANGES) for row in [*iso286.IT.values(), *iso286.SHAFT.values()])
    assert all(len(row) == len(iso286.FINE_RANGES) for row in iso286.SHAFT_FINE.values())
    assert len(iso286.DELTA) == len(iso286.RANGES)


def test_delta_is_the_step_to_the_next_finer_grade():
    for i in range(1, len(iso286.RANGES)):
        steps = [iso286.IT[g][i] - iso286.IT[g - 1][i] for g in (6, 7, 8)]
        assert list(iso286.DELTA[i][1:]) == steps


def test_every_range_edge_changes_the_tolerance_band():
    for i, edge in enumerate(iso286.RANGES[:-1]):
        assert limits("H7", edge)[0] == iso286.IT[7][i] / 1000
        assert limits("H7", edge + 0.01)[0] == iso286.IT[7][i + 1] / 1000


@pytest.mark.parametrize("nominal", [2, 5, 8, 15, 25, 40, 70, 100, 150, 200, 280, 350, 450])
@pytest.mark.parametrize("letter", ["JS", "K", "M", "N", "P", "F", "G", "E", "D", "H"])
def test_hole_width_is_the_tolerance_grade(letter, nominal):
    index = iso286.bisect_left(iso286.RANGES, nominal)
    for grade in (6, 7, 8, 9):
        upper, lower = limits(f"{letter}{grade}", nominal)
        assert upper - lower == pytest.approx(iso286.IT[grade][index] / 1000)


@pytest.mark.parametrize("nominal", [2, 5, 8, 15, 25, 40, 70, 100, 150, 200, 280, 350, 450])
@pytest.mark.parametrize("letter", ["js", "k", "m", "n", "p", "r", "s", "f", "g", "e", "d", "h"])
def test_shaft_width_is_the_tolerance_grade(letter, nominal):
    index = iso286.bisect_left(iso286.RANGES, nominal)
    for grade in (5, 6, 7, 8, 9):
        upper, lower = limits(f"{letter}{grade}", nominal)
        assert upper - lower == pytest.approx(iso286.IT[grade][index] / 1000)
