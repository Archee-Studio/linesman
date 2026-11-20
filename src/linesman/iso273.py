"""ISO 273 clearance holes for bolts, medium series, in millimetres.

Transcribed from ISO 273 (fasteners — clearance holes for bolts and screws), medium series: the hole a
machined part gets for an ordinary bolted joint. `medium` is the only entry point.
"""

MEDIUM = {
    "M5": 5.5,
    "M6": 6.6,
    "M8": 9.0,
    "M10": 11.0,
    "M12": 13.5,
    "M14": 15.5,
    "M16": 17.5,
    "M18": 20.0,
    "M20": 22.0,
    "M24": 26.0,
}


def medium(bolt: str) -> float:
    """The medium-series clearance hole for a bolt designation such as `M8`."""
    return MEDIUM[bolt.upper()]
