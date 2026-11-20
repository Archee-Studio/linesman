"""DIN 471 retaining rings for shafts: groove diameter d2 and groove width m by shaft diameter d1 (mm).

Transcribed from DIN 471 (retaining rings for shafts — normal type), standard series. `groove` is the only
entry point.
"""

# (largest shaft diameter d1, groove floor d2, groove width m, ring thickness s)
GROOVES = (
    (20, 19.0, 1.3, 1.2),
    (22, 21.0, 1.3, 1.2),
    (24, 22.9, 1.3, 1.2),
    (25, 23.9, 1.3, 1.2),
    (28, 26.6, 1.6, 1.5),
    (30, 28.6, 1.6, 1.5),
    (32, 30.3, 1.6, 1.5),
    (35, 33.0, 1.6, 1.5),
    (38, 36.0, 1.85, 1.75),
    (40, 37.5, 1.85, 1.75),
)


def groove(d: float) -> dict[str, float]:
    """The retaining-ring groove for a shaft of diameter d: `d2` (floor) and `m` (width)."""
    for d_max, d2, m, s in GROOVES:
        if d <= d_max:
            return {"d2": d2, "m": m, "s": s}
    raise ValueError(f"no DIN 471 groove for diameter {d}")
