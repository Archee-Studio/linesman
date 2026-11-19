"""The gate and the parsed sheet. Submitted files are hostile input, so every limit here is enforced before parsing."""

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from ezdxf import recover
from ezdxf.document import Drawing

MM = 4  # $INSUNITS value for millimetres


@dataclass(frozen=True)
class Limits:
    bytes: int = 20_000_000
    entities: int = 200_000
    block_depth: int = 16  # block references inside block references; real title blocks nest one or two deep


LIMITS = Limits()

GEOMETRY = ("LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "SPLINE", "ELLIPSE")


@dataclass(frozen=True)
class Text:
    text: str
    x: float
    y: float
    height: float


@dataclass(frozen=True)
class Dimension:
    """A DIMENSION entity as the reader of the sheet sees it."""

    kind: str  # linear, diameter, radius, angular, other
    value: float  # displayed value: override text if numeric, else measurement * DIMLFAC
    text: str  # the displayed text, empty when the measurement is shown as is
    x: float  # text position
    y: float
    handle: str


@dataclass
class Sheet:
    doc: Drawing
    errors: list[str] = field(default_factory=list)
    geometry: list = field(default_factory=list)
    texts: list[Text] = field(default_factory=list)
    dims: list[Dimension] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


def load(path: Path) -> Sheet:
    """Open a submitted DXF and run the gate; a sheet with `errors` scores zero everywhere."""
    if not path.is_file():
        return _failed(f"missing {path.name}")
    if path.stat().st_size > LIMITS.bytes:
        return _failed(f"file over {LIMITS.bytes} bytes")
    try:
        doc, auditor = recover.readfile(path)
    except (OSError, ezdxf.DXFStructureError) as exc:
        return _failed(f"does not open: {exc}")
    return parse(doc, unrecoverable=len(auditor.errors))


def parse(doc: Drawing, unrecoverable: int = 0) -> Sheet:
    sheet = Sheet(doc)
    msp = doc.modelspace()
    if len(msp) > LIMITS.entities:
        sheet.errors.append(f"more than {LIMITS.entities} entities")
        return sheet
    if unrecoverable:
        sheet.errors.append(f"{unrecoverable} unrecoverable audit errors")
    if doc.header.get("$INSUNITS", 0) != MM:
        sheet.errors.append("units are not millimetres ($INSUNITS != 4)")
    try:
        flat = list(_flatten(msp))
    except (_TooDeep, RecursionError) as exc:
        sheet.errors.append(str(exc) or "block references nest too deeply")
        return sheet
    for e in flat:
        kind = e.dxftype()
        if kind in GEOMETRY:
            sheet.geometry.append(e)
        elif kind in ("TEXT", "MTEXT"):
            sheet.texts.append(_text(e))
        elif kind == "DIMENSION":
            sheet.dims.append(_dimension(e))
    if not sheet.geometry:
        sheet.errors.append("no geometry")
    return sheet


def _failed(reason: str) -> Sheet:
    return Sheet(ezdxf.new("R2018"), errors=[reason])


class _TooDeep(Exception):
    """Block references nest deeper, or expand to more entities, than the limits allow."""


def _flatten(space, depth: int = 0, budget: list[int] | None = None):
    """Entities of a space with block references expanded (title blocks are often blocks), within LIMITS."""
    budget = [LIMITS.entities] if budget is None else budget
    if depth > LIMITS.block_depth:
        raise _TooDeep(f"block references nested deeper than {LIMITS.block_depth}")
    for e in space:
        budget[0] -= 1
        if budget[0] < 0:
            raise _TooDeep(f"block references expand to more than {LIMITS.entities} entities")
        if e.dxftype() == "INSERT":
            yield from _flatten(e.virtual_entities(), depth + 1, budget)
        else:
            yield e


def _text(e) -> Text:
    if e.dxftype() == "MTEXT":
        content, height = e.plain_text(), e.dxf.get("char_height", 2.5)
    else:
        content, height = e.dxf.text, e.dxf.get("height", 2.5)
    p = e.dxf.insert
    return Text(content.strip(), p.x, p.y, height)


_KINDS = {0: "linear", 1: "linear", 2: "angular", 3: "diameter", 4: "radius", 5: "angular", 6: "linear"}


def _dimension(e) -> Dimension:
    kind = _KINDS.get(e.dimtype & 0x0F, "other")
    shown = (e.dxf.get("text", "") or "").strip()
    measured = _measurement(e)
    if kind != "angular":
        measured *= e.get_dim_style().dxf.get("dimlfac", 1.0) if e.get_dim_style() else 1.0
    value = number(shown.replace("<>", f"{measured:g}")) if shown else None
    p = e.dxf.get("text_midpoint", e.dxf.get("defpoint"))
    return Dimension(kind, measured if value is None else value, shown, p.x, p.y, e.dxf.handle)


def _measurement(e) -> float:
    try:
        m = e.get_measurement()
    except (ValueError, TypeError, AttributeError):
        return math.nan
    return math.degrees(m) if isinstance(m, float) and (e.dimtype & 0x0F) in (2, 5) else float(m)


_COUNT = re.compile(r"^\s*\d+\s*[x×X]\s*")
_CHAMFER = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*[x×X]\s*\d+(?:[.,]\d+)?\s*(?:°|deg|%%d)", re.IGNORECASE)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def number(text: str) -> float | None:
    """The value in a dimension text: `%%c40H7` -> 40.0, `4x %%c6.6` -> 6.6, `R12` -> 12.0, `30°` -> 30.0,
    and a chamfer `1 x 45°` -> 1.0 (the leg, not a count)."""
    plain = re.sub(r"\\[A-Za-z][^;]*;|[{}]", "", text).replace("%%c", "").replace("%%C", "")
    chamfer = _CHAMFER.match(plain)
    if chamfer:
        return float(chamfer.group(1).replace(",", "."))
    found = _NUMBER.search(_COUNT.sub("", plain))
    return float(found.group().replace(",", ".")) if found else None
