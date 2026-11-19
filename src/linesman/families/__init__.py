"""The one registry of part families. Each module exposes NAME, sample, request, truth and draw (docs/spec.md)."""

from types import ModuleType

from . import bracket, bushing, flange, gear_blank, plate, shaft

FAMILIES: dict[str, ModuleType] = {m.NAME: m for m in (plate, shaft, flange, bushing, gear_blank, bracket)}
