"""ISO 286-1 limit deviations for holes and shafts up to 500 mm, IT5 to IT11, from the standard's tables.

Every table is in micrometres and indexed by nominal size range (over, up to and including). `limits` is the only
entry point: it returns the upper and lower deviation in millimetres.
"""

import re
from bisect import bisect_left

# Upper bound (mm, inclusive) of each size range. A size of exactly 30 belongs to 18-30, 30.01 to 30-50.
RANGES = (3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500)
# r and s are tabulated per finer range above 10 mm.
FINE_RANGES = (
    3,
    6,
    10,
    14,
    18,
    24,
    30,
    40,
    50,
    65,
    80,
    100,
    120,
    140,
    160,
    180,
    200,
    225,
    250,
    280,
    315,
    355,
    400,
    450,
    500,
)

# Standard tolerance grades (Table 1), one column per range above.
IT = {
    5: (4, 5, 6, 8, 9, 11, 13, 15, 18, 20, 23, 25, 27),
    6: (6, 8, 9, 11, 13, 16, 19, 22, 25, 29, 32, 36, 40),
    7: (10, 12, 15, 18, 21, 25, 30, 35, 40, 46, 52, 57, 63),
    8: (14, 18, 22, 27, 33, 39, 46, 54, 63, 72, 81, 89, 97),
    9: (25, 30, 36, 43, 52, 62, 74, 87, 100, 115, 130, 140, 155),
    10: (40, 48, 58, 70, 84, 100, 120, 140, 160, 185, 210, 230, 250),
    11: (60, 75, 90, 110, 130, 160, 190, 220, 250, 290, 320, 360, 400),
}

# Shaft fundamental deviations (Table 2): upper deviation es for d to g, lower deviation ei for k to p.
SHAFT = {
    "d": (-20, -30, -40, -50, -65, -80, -100, -120, -145, -170, -190, -210, -230),
    "e": (-14, -20, -25, -32, -40, -50, -60, -72, -85, -100, -110, -125, -135),
    "f": (-6, -10, -13, -16, -20, -25, -30, -36, -43, -50, -56, -62, -68),
    "g": (-2, -4, -5, -6, -7, -9, -10, -12, -14, -15, -17, -18, -20),
    "k": (0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 5),  # IT5 to IT7 only; ei is 0 for other grades
    "m": (2, 4, 6, 7, 8, 9, 11, 13, 15, 17, 20, 21, 23),
    "n": (4, 8, 10, 12, 15, 17, 20, 23, 27, 31, 34, 37, 40),
    "p": (6, 12, 15, 18, 22, 26, 32, 37, 43, 50, 56, 62, 68),
}
SHAFT_FINE = {
    "r": (10, 15, 19, 23, 23, 28, 28, 34, 34, 41, 43, 51, 54, 63, 65, 68, 77, 80, 84, 94, 98, 108, 114, 126, 132),
    "s": (
        14,
        19,
        23,
        28,
        28,
        35,
        35,
        43,
        43,
        53,
        59,
        71,
        79,
        92,
        100,
        108,
        122,
        130,
        140,
        158,
        170,
        190,
        208,
        232,
        252,
    ),
}

# Delta (Table 3) added to the hole deviation of K, M, N (IT5 to IT8) and P, R, S (IT5 to IT7); columns IT5 to IT8.
DELTA = (
    (0, 0, 0, 0),
    (1, 3, 4, 6),
    (2, 3, 6, 7),
    (3, 3, 7, 9),
    (3, 4, 8, 12),
    (4, 5, 9, 14),
    (5, 6, 11, 16),
    (5, 7, 13, 19),
    (6, 7, 15, 23),
    (6, 9, 17, 26),
    (7, 9, 20, 29),
    (7, 11, 21, 32),
    (7, 13, 23, 34),
)

# Hole letters whose deviation is the mirror of the shaft letter of the same name (general rule).
HOLE_MIRROR = {"D": "d", "E": "e", "F": "f", "G": "g"}
# Hole letters with the special rule and the last IT grade that adds Delta.
HOLE_DELTA = {"K": ("k", 8), "M": ("m", 8), "N": ("n", 8), "P": ("p", 7)}

_DESIGNATION = re.compile(r"^([A-Za-z]{1,2})(\d{1,2})$")


def _range(nominal: float, bounds: tuple[int, ...]) -> int:
    if not 0 < nominal <= bounds[-1]:
        raise ValueError(f"nominal size {nominal} outside 0-{bounds[-1]} mm")
    return bisect_left(bounds, nominal)


def _shaft_fd(letter: str, grade: int, nominal: float) -> float:
    """Fundamental deviation of a shaft letter in micrometres: es for d to h, ei for js to s."""
    if letter in SHAFT_FINE:
        return SHAFT_FINE[letter][_range(nominal, FINE_RANGES)]
    value = SHAFT[letter][_range(nominal, RANGES)]
    return 0 if letter == "k" and grade > 7 else value


def _shaft(letter: str, grade: int, nominal: float) -> tuple[float, float]:
    width = IT[grade][_range(nominal, RANGES)]
    if letter == "h":
        return 0, -width
    if letter == "js":
        return width / 2, -width / 2
    fd = _shaft_fd(letter, grade, nominal)
    return (fd, fd - width) if letter in "defg" else (fd + width, fd)


def _hole(letter: str, grade: int, nominal: float) -> tuple[float, float]:
    index = _range(nominal, RANGES)
    width = IT[grade][index]
    if letter == "H":
        return width, 0
    if letter == "JS":
        return width / 2, -width / 2
    if letter in HOLE_MIRROR:
        low = -_shaft_fd(HOLE_MIRROR[letter], grade, nominal)
        return low + width, low
    shaft, last = HOLE_DELTA[letter]
    # K above IT8 is 0 because the shaft table gives k no deviation there; M and N keep their value, P too.
    base = -_shaft_fd(shaft, 7 if shaft == "k" and grade <= last else grade, nominal)
    upper = base + (DELTA[index][grade - 5] if grade <= last else 0)
    return upper, upper - width


def limits(designation: str, nominal: float) -> tuple[float, float]:
    """(upper, lower) deviation in mm of a designation such as `H7` or `g6` at a nominal size in mm."""
    found = _DESIGNATION.match(designation)
    if not found:
        raise ValueError(f"unknown designation {designation!r}")
    letter, grade = found.group(1), int(found.group(2))
    if grade not in IT:
        raise ValueError(f"unsupported tolerance grade IT{grade} in {designation!r}")
    hole = letter.isupper()
    known = (*HOLE_MIRROR, *HOLE_DELTA, "H", "JS") if hole else (*SHAFT, *SHAFT_FINE, "h", "js")
    if letter not in known:
        raise ValueError(f"unknown designation {designation!r}")
    upper, lower = (_hole if hole else _shaft)(letter, grade, nominal)
    return round(upper / 1000, 6), round(lower / 1000, 6)
