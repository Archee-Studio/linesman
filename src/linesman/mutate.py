"""The one registry of mutants: a reference sheet with one seeded defect, and the proof that the defect is visible.

A mutant is applied with `apply`, which works on a copy, saves and reloads it, and only returns a mutation whose
witness holds in the reloaded file (the value text differs, the entity is gone). A defect with no witness is not
counted: `apply` raises `Skip` for it, as it does for a mutant that does not fit the family.
"""

import contextlib
import io
import random
import re
from collections.abc import Callable
from dataclasses import dataclass

import ezdxf
from ezdxf import bbox as ezbbox
from ezdxf.document import Drawing
from ezdxf.entities.dimstyleoverride import DimStyleOverride

from .regions import regions
from .schema import SeededError, Truth
from .sheet import Dimension, Sheet, parse

REACH = 1.0  # mm: how close a located point must be to the dimension or text it names
MATERIALS = ("S235", "C45", "AlMg3", "42CrMo4", "EN-GJL-250", "16MnCr5")
FIT_SWAPS = {"H7": "H8", "H6": "H7", "H8": "H9", "k6": "m6", "g6": "f7", "h6": "h7", "f7": "e8", "p6": "r6", "s6": "t6"}


class Skip(Exception):
    """The mutant does not apply to this sheet, or its defect has no witness in the saved file."""


@dataclass(frozen=True)
class Mutation:
    doc: Drawing
    targets: tuple[str, ...]
    error: SeededError


Run = Callable[[Drawing, Truth, random.Random], Mutation]
Witness = Callable[[Sheet, Sheet, Mutation, Truth], bool]


@dataclass(frozen=True)
class Mutant:
    run: Run
    witness: Witness


def roundtrip(doc: Drawing) -> Drawing:
    """Save and reload: what a reader of the file sees."""
    stream = io.StringIO()
    doc.write(stream)
    stream.seek(0)
    return ezdxf.read(stream)


def _dim_at(sheet: Sheet, x: float, y: float) -> Dimension | None:
    near = [d for d in sheet.dims if abs(d.x - x) <= REACH and abs(d.y - y) <= REACH]
    return min(near, key=lambda d: abs(d.x - x) + abs(d.y - y), default=None)


def _text_at(sheet: Sheet, x: float, y: float) -> str | None:
    near = [t for t in sheet.texts if abs(t.x - x) <= REACH and abs(t.y - y) <= REACH]
    return min(near, key=lambda t: abs(t.x - x) + abs(t.y - y)).text if near else None


def _matches(sheet: Sheet, truth: Truth, dim_id: str) -> list:
    """Sheet dimensions that show the truth dimension: same kind and value."""
    want = next(d for d in truth.dims if d.id == dim_id)
    return [d for d in sheet.dims if d.kind == want.kind and abs(d.value - want.value) < 0.01]


def _candidates(doc: Drawing, truth: Truth, rng: random.Random, fitted: bool | None = None):
    """Truth dimensions drawn once on the sheet, so changing or deleting one cannot be hidden by a twin."""
    sheet = parse(doc)
    found = []
    for want in truth.dims:
        if fitted is not None and bool(want.fit) != fitted:
            continue
        twins = [d for d in truth.dims if d.kind == want.kind and abs(d.value - want.value) < 0.01]
        shown = _matches(sheet, truth, want.id)
        if len(twins) == 1 and len(shown) == 1:
            found.append((want, shown[0]))
    if not found:
        raise Skip("no uniquely shown dimension")
    return rng.choice(found)


def _entity(doc: Drawing, dim: Dimension):
    return doc.entitydb[dim.handle]


def _set_text(doc: Drawing, dim: Dimension, text: str) -> Dimension:
    """Override a dimension's text and redraw its block so the picture agrees with the entity."""
    entity = _entity(doc, dim)
    entity.dxf.text = text
    with contextlib.suppress(Exception):  # an old block is only a stale picture; the override text is scored
        DimStyleOverride(entity).render()
    moved = next(d for d in parse(doc).dims if d.handle == dim.handle)
    return moved


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _wrong_value(doc: Drawing, truth: Truth, rng: random.Random) -> Mutation:
    want, dim = _candidates(doc, truth, rng, fitted=False)
    taken = {round(d.value, 2) for d in truth.dims}
    options = [
        round(want.value * f * 2) / 2 for f in (0.9, 0.95, 1.05, 1.1, 1.2) if round(want.value * f * 2) / 2 not in taken
    ]
    if not options:
        raise Skip("no plausible wrong value")
    new = rng.choice(options)
    old = dim.text or "<>"
    prefix = "%%c" if want.kind == "diameter" and "%%c" not in old else ""
    moved = _set_text(doc, dim, old.replace("<>", prefix + _fmt(new)))
    return Mutation(
        doc, ("dims.recall",), SeededError(id="wrong-value", kind="wrong-value", x=moved.x, y=moved.y, dim_id=want.id)
    )


def _wrong_value_seen(before: Sheet, after: Sheet, m: Mutation, truth: Truth) -> bool:
    dim = _dim_at(after, m.error.x, m.error.y)
    old = next((d for d in before.dims if dim and d.handle == dim.handle), None)
    return bool(dim and old and abs(dim.value - old.value) > 0.01 and len(after.dims) == len(before.dims))


def _missing_dim(doc: Drawing, truth: Truth, rng: random.Random) -> Mutation:
    want, dim = _candidates(doc, truth, rng)
    entity = _entity(doc, dim)
    block = entity.dxf.get("geometry")
    doc.modelspace().delete_entity(entity)
    if block and block in doc.blocks:
        doc.blocks.delete_block(block, safe=False)
    return Mutation(
        doc, ("dims.recall",), SeededError(id="missing-dim", kind="missing-dim", x=dim.x, y=dim.y, dim_id=want.id)
    )


def _missing_dim_seen(before: Sheet, after: Sheet, m: Mutation, truth: Truth) -> bool:
    gone = {d.handle for d in before.dims} - {d.handle for d in after.dims}
    return len(gone) == 1 and len(after.dims) == len(before.dims) - 1 and _dim_at(after, m.error.x, m.error.y) is None


def _swap_fit(text: str, fit: str) -> str | None:
    other = FIT_SWAPS.get(fit)
    if other is None:
        match = re.fullmatch(r"([A-Za-z]+)(\d+)", fit)
        other = f"{match.group(1)}{int(match.group(2)) + 1}" if match else None
    return text.replace(fit, other, 1) if other and fit in text else None


def _wrong_fit(doc: Drawing, truth: Truth, rng: random.Random) -> Mutation:
    want, dim = _candidates(doc, truth, rng, fitted=True)
    new = _swap_fit(dim.text, want.fit or "")
    if new is None:
        raise Skip("the fit is not shown in the dimension text")
    moved = _set_text(doc, dim, new)
    return Mutation(
        doc, ("fits.shown",), SeededError(id="wrong-fit", kind="wrong-fit", x=moved.x, y=moved.y, dim_id=want.id)
    )


def _wrong_fit_seen(before: Sheet, after: Sheet, m: Mutation, truth: Truth) -> bool:
    want = next((d for d in truth.dims if d.id == m.error.dim_id), None)
    dim = _dim_at(after, m.error.x, m.error.y)
    old = next((d for d in before.dims if dim and d.handle == dim.handle), None)
    return bool(want and want.fit and dim and old and want.fit in old.text and want.fit not in dim.text)


def _wrong_title_field(doc: Drawing, truth: Truth, rng: random.Random) -> Mutation:
    material = truth.title.get("material")
    texts = [e for e in doc.modelspace().query("TEXT") if e.dxf.text.strip() == material]
    if not material or len(texts) != 1:
        raise Skip("no single material text in the title block")
    entity = texts[0]
    entity.dxf.text = rng.choice([m for m in MATERIALS if m != material])
    p = entity.dxf.insert
    return Mutation(
        doc, ("titleblock.fields",), SeededError(id="wrong-title-field", kind="wrong-title-field", x=p.x, y=p.y)
    )


def _wrong_title_seen(before: Sheet, after: Sheet, m: Mutation, truth: Truth) -> bool:
    old, new = _text_at(before, m.error.x, m.error.y), _text_at(after, m.error.x, m.error.y)
    return old == truth.title.get("material") and new is not None and new != old


def _view_boxes(doc: Drawing) -> list[tuple[float, float, float, float]]:
    return [(r.x0, r.y0, r.x1, r.y1) for r in regions(parse(doc))]


def _inside(e, box, slack: float = 0.5) -> bool:
    ext = ezbbox.extents([e])
    return ext.has_data and (
        ext.extmin.x >= box[0] - slack
        and ext.extmin.y >= box[1] - slack
        and ext.extmax.x <= box[2] + slack
        and ext.extmax.y <= box[3] + slack
    )


def _missing_view(doc: Drawing, truth: Truth, rng: random.Random) -> Mutation:
    boxes = _view_boxes(doc)
    if len(boxes) < 2:
        raise Skip("fewer than two view regions")
    box = rng.choice(boxes)
    msp = doc.modelspace()
    doomed = [e for e in msp if e.dxftype() != "DIMENSION" and e.dxf.layer != "frame" and _inside(e, box)]
    if not doomed:
        raise Skip("no geometry inside the region")
    for e in doomed:
        msp.delete_entity(e)
    x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return Mutation(doc, ("views.present",), SeededError(id="missing-view", kind="missing-view", x=x, y=y))


def _missing_view_seen(before: Sheet, after: Sheet, m: Mutation, truth: Truth) -> bool:
    return len(after.geometry) < len(before.geometry) and after.valid


MUTANTS: dict[str, Mutant] = {
    "wrong-value": Mutant(_wrong_value, _wrong_value_seen),
    "missing-dim": Mutant(_missing_dim, _missing_dim_seen),
    "wrong-fit": Mutant(_wrong_fit, _wrong_fit_seen),
    "wrong-title-field": Mutant(_wrong_title_field, _wrong_title_seen),
    "missing-view": Mutant(_missing_view, _missing_view_seen),
}


def apply(name: str, doc: Drawing, truth: Truth, rng: random.Random) -> Mutation:
    """Apply one mutant to a copy of `doc`; the original is untouched. Raises `Skip` when there is no witness."""
    mutant = MUTANTS[name]
    before = parse(roundtrip(doc))
    mutation = mutant.run(roundtrip(doc), truth, rng)
    after = parse(roundtrip(mutation.doc))
    if not mutant.witness(before, after, mutation, truth):
        raise Skip(f"{name}: no witness in the saved file")
    return mutation


def seed_errors(doc: Drawing, truth: Truth, rng: random.Random, count: int | None = None):
    """Review track: seed 1-3 mutants of different kinds. Returns the mutated document and the seeded errors."""
    wanted = count or rng.randint(1, 3)
    names = sorted(MUTANTS)
    rng.shuffle(names)
    errors: list[SeededError] = []
    for name in names:
        if len(errors) == wanted:
            break
        left = truth.model_copy(update={"dims": tuple(d for d in truth.dims if d.id not in _touched(errors))})
        try:
            mutation = apply(name, doc, left, rng)
        except Skip:
            continue
        doc = mutation.doc
        errors.append(mutation.error.model_copy(update={"id": f"e{len(errors) + 1}"}))
    if not errors:
        raise Skip("no seeded error")
    return doc, tuple(errors)


def _touched(errors: list[SeededError]) -> set[str]:
    return {e.dim_id for e in errors if e.dim_id}
