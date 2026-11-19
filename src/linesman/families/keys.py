"""DIN 6885 parallel key sizes by shaft diameter: width b, height h, shaft depth t1, hub depth t2 (mm)."""

# (largest shaft diameter, b, h, t1, t2)
KEYS = (
    (8, 2, 2, 1.2, 1.0),
    (10, 3, 3, 1.8, 1.4),
    (12, 4, 4, 2.5, 1.8),
    (17, 5, 5, 3.0, 2.3),
    (22, 6, 6, 3.5, 2.8),
    (30, 8, 7, 4.0, 3.3),
    (38, 10, 8, 5.0, 3.3),
    (44, 12, 8, 5.0, 3.3),
    (50, 14, 9, 5.5, 3.8),
    (58, 16, 10, 6.0, 4.3),
)

KEY_LENGTHS = (14, 16, 18, 20, 22, 25, 28, 32, 36, 40, 45, 50, 56, 63, 70)


def key(d: float) -> dict[str, float]:
    """The key for a shaft of diameter d: `b`, `h`, `t1` (shaft depth) and `t2` (hub depth)."""
    for d_max, b, h, t1, t2 in KEYS:
        if d <= d_max:
            return {"b": float(b), "h": float(h), "t1": t1, "t2": t2}
    raise ValueError(f"no key for diameter {d}")
