"""RULES.md: the spec's "Sheet rules every entrant can read" section, extracted so it never drifts."""

from pathlib import Path

_SPEC = Path(__file__).resolve().parents[2] / "docs" / "spec.md"
_HEAD = "Sheet rules every entrant can read:"
_UNITS = "Units: millimetres ($INSUNITS = 4). Save DXF R2018 or later."


def rules_text(spec: Path | None = None) -> str:
    """The entrant rules section verbatim, then the units and DXF version line."""
    path = spec or _SPEC
    text = path.read_text()
    start = text.index(_HEAD) + len(_HEAD)
    end = text.find("\n## ", start)
    body = text[start : end if end != -1 else len(text)].strip()
    return f"{_HEAD}\n\n{body}\n\n{_UNITS}\n"
