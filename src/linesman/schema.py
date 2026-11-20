"""Every record Linesman reads or writes. Changing a field changes the spec version (docs/spec.md)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SPEC_VERSION = "0.2.1"

Track = Literal["calc-sheet", "review"]
Part = Literal["gate", "views", "dims", "fits", "titleblock", "drafting", "finish", "review"]
ViewName = Literal["front", "top", "left", "right", "bottom", "rear", "section"]
DimKind = Literal["linear", "diameter", "radius", "angular"]
ErrorKind = Literal["wrong-value", "missing-dim", "wrong-fit", "missing-view", "wrong-title-field"]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Task(Frozen):
    id: str
    track: Track
    family: str
    seed: int
    spec: str = SPEC_VERSION
    level: Literal["given", "calc"] = "given"  # calc tasks give requirements, not finished values


class View(Frozen):
    """A required view: its name and the true size of its outline in millimetres; the grader applies `Truth.scale`."""

    name: ViewName
    width: float
    height: float
    hidden: bool = False  # the view holds features shown with hidden (dashed) lines
    hatch_area: float | None = None  # section views: true mm2 of cut material the hatch must cover


class Dim(Frozen):
    """A required dimension. `value` is in millimetres (degrees for angular); `fit` is an ISO 286 designation."""

    id: str
    kind: DimKind
    value: float
    view: ViewName
    fit: str | None = None
    fit_form: Literal["any", "deviations"] = "any"  # "deviations" requires limit deviations, not a designation
    alt: tuple[float, ...] = ()  # other values that locate the same feature equally (pitch or edge distance)


class SeededError(Frozen):
    """Review track: one defect planted in the task's sheet, located by a point on the sheet (mm)."""

    id: str
    kind: ErrorKind
    x: float
    y: float
    dim_id: str | None = None


class Truth(Frozen):
    views: tuple[View, ...]
    dims: tuple[Dim, ...]
    title: dict[str, str] = Field(default_factory=dict)
    scale: str = "1:1"
    finish: dict[str, float] = Field(default_factory=dict)  # dim id -> required Ra in micrometres
    errors: tuple[SeededError, ...] = ()


class Finding(Frozen):
    kind: ErrorKind
    x: float
    y: float
    note: str = ""


class CheckResult(Frozen):
    id: str
    part: Part
    critical: bool
    score: float = Field(ge=0.0, le=1.0)
    detail: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.score >= 1.0


class TaskResult(Frozen):
    task: str
    valid: bool
    passed: bool
    checks: tuple[CheckResult, ...]
    parts: dict[str, float]
