"""The one registry of part families. Each module exposes NAME, sample, request, truth and draw (docs/spec.md)."""

from types import ModuleType

from . import bracket, bushing, cover, flange, gear_blank, lever, plate, pulley, shaft

FAMILIES: dict[str, ModuleType] = {
    m.NAME: m for m in (plate, shaft, flange, bushing, gear_blank, bracket, pulley, lever, cover)
}
