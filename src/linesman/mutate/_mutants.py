"""The mutant implementations: each `_run` plants one defect, its `_seen` proves it survives a save/reload."""

import contextlib
import random
import re

from ezdxf import bbox as ezbbox
from ezdxf.document import Drawing
from ezdxf.entities.dimstyleoverride import DimStyleOverride
from ezdxf.math import Matrix44

from ..geo import linetype_class
from ..regions import frame, regions
from ..schema import SeededError, Truth
from ..sheet import Dimension, Sheet, parse
from . import FIT_SWAPS, MATERIALS, REACH, Mutant, Mutation, Skip


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


def _any_dim(doc: Drawing, rng: random.Random) -> Dimension:
    shown = parse(doc).dims
    if not shown:
        raise Skip("no dimensions on the sheet")
    return rng.choice(shown)


def _prefix(text: str, kind: str) -> str:
    if "%%c" in text.lower() or kind == "diameter":
        return "%%c"
    return "R" if text.upper().startswith("R") or kind == "radius" else ""


def _lying_text(doc: Drawing, truth: Truth, rng: random.Random) -> Mutation:
    """Two unique same-kind dimensions trade displayed values: both are present but both lie."""
    pair = _two_unique(doc, truth, rng)
    (want_a, dim_a), (want_b, dim_b) = pair
    prefix = _prefix(dim_a.text or dim_b.text, want_a.kind)
    _set_text(doc, dim_a, f"{prefix}{_fmt(want_b.value)}")
    moved = _set_text(doc, dim_b, f"{prefix}{_fmt(want_a.value)}")
    return Mutation(
        doc, ("dims.true",), SeededError(id="wrong-value", kind="wrong-value", x=moved.x, y=moved.y, dim_id=want_b.id)
    )


def _two_unique(doc: Drawing, truth: Truth, rng: random.Random):
    sheet = parse(doc)
    found = []
    for want in truth.dims:
        twins = [d for d in truth.dims if d.kind == want.kind and abs(d.value - want.value) < 0.01]
        shown = _matches(sheet, truth, want.id)
        if len(twins) == 1 and len(shown) == 1:
            found.append((want, shown[0]))
    kinds = {}
    for want, dim in found:
        kinds.setdefault(want.kind, []).append((want, dim))
    pairs = [(a, b) for group in kinds.values() for a, b in zip(group, group[1:], strict=False)]
    if not pairs:
        raise Skip("no two uniquely shown dimensions of a kind with different values")
    return rng.choice(pairs)


def _lying_text_seen(before: Sheet, after: Sheet, m: Mutation, truth: Truth) -> bool:
    changed = [(b, a) for b, a in zip(before.dims, after.dims, strict=False) if abs(a.value - b.value) > 0.01]
    return len(changed) >= 2 and len(after.dims) == len(before.dims)


def _detached_dim(doc: Drawing, truth: Truth, rng: random.Random) -> Mutation:
    """A dimension's definition points move 5 mm off the geometry; the displayed value is kept."""
    want, dim = _candidates(doc, truth, rng, fitted=False)
    entity = _entity(doc, dim)
    for name in ("defpoint2", "defpoint3", "defpoint4", "defpoint5"):
        if entity.dxf.hasattr(name):
            q = entity.dxf.get(name)
            entity.dxf.set(name, (q.x + 5.0, q.y + 5.0, q.z))
    text = dim.text.replace("<>", _fmt(dim.value)) if dim.text else _fmt(dim.value)
    moved = _set_text(doc, dim, text)
    return Mutation(
        doc,
        ("dims.attached",),
        SeededError(id="wrong-value", kind="wrong-value", x=moved.x, y=moved.y, dim_id=want.id),
    )


def _detached_dim_seen(before: Sheet, after: Sheet, m: Mutation, truth: Truth) -> bool:
    pairs = {d.handle: d for d in after.dims}
    moved = [b for b in before.dims if b.handle in pairs and pairs[b.handle].points != b.points]
    return bool(moved) and all(abs(pairs[b.handle].value - b.value) < 0.01 for b in moved)


def _off_sheet(doc: Drawing, truth: Truth, rng: random.Random) -> Mutation:
    """A view's geometry is moved across the frame's left edge."""
    sheet = parse(doc)
    fbox, found = frame(sheet), regions(sheet)
    if fbox is None or not found:
        raise Skip("no frame or no view region")
    r = rng.choice(found)
    dx = (fbox[0] - 8.0) - r.x0
    msp = doc.modelspace()
    doomed = [
        e for e in msp if e.dxftype() != "DIMENSION" and e.dxf.layer != "frame" and _inside(e, (r.x0, r.y0, r.x1, r.y1))
    ]
    if not doomed:
        raise Skip("no geometry inside the region")
    move = Matrix44.translate(dx, 0.0, 0.0)
    for e in doomed:
        e.transform(move)
    x, y = (r.x0 + r.x1) / 2 + dx, (r.y0 + r.y1) / 2
    return Mutation(doc, ("drafting.on_sheet",), SeededError(id="missing-view", kind="missing-view", x=x, y=y))


def _off_sheet_seen(before: Sheet, after: Sheet, m: Mutation, truth: Truth) -> bool:
    fbox = frame(after)
    moved_out = fbox is None or any(
        _safe_min_x(e) is not None and _safe_min_x(e) < fbox[0] - 0.5 for e in after.geometry
    )
    return after.valid and moved_out


def _safe_min_x(e):
    try:
        b = ezbbox.extents([e])
        return b.extmin.x if b.has_data else None
    except Exception:
        return None


def _tiny_text(doc: Drawing, truth: Truth, rng: random.Random) -> Mutation:
    """One dimension's text renders at 1.8 mm, under the ISO 3098 minimum."""
    dim = _any_dim(doc, rng)
    entity = _entity(doc, dim)
    override = DimStyleOverride(entity)
    override["dimtxt"] = 1.8
    override.commit()
    entity.render()
    return Mutation(doc, ("drafting.text",), SeededError(id="wrong-value", kind="wrong-value", x=dim.x, y=dim.y))


def _tiny_text_seen(before: Sheet, after: Sheet, m: Mutation, truth: Truth) -> bool:
    for d in after.dims:  # the defect is visible when some dimension's text renders under 2.5 mm
        entity = after.doc.entitydb.get(d.handle)
        try:
            heights = [
                v.dxf.get("char_height", 0.0) if v.dxftype() == "MTEXT" else v.dxf.get("height", 0.0)
                for v in entity.virtual_entities()
                if v.dxftype() in ("TEXT", "MTEXT")
            ]
        except Exception:
            heights = []
        if heights and all(h < 2.5 for h in heights):
            return True
    return False


def _overlap_text(doc: Drawing, truth: Truth, rng: random.Random) -> Mutation:
    """A text is dropped on top of a dimension's text."""
    dim = _any_dim(doc, rng)
    entity = _entity(doc, dim)
    try:
        boxes = [
            ezbbox.extents([v])
            for v in entity.virtual_entities()
            if v.dxftype() in ("TEXT", "MTEXT") and ezbbox.extents([v]).has_data
        ]
    except Exception:
        boxes = []
    if not boxes:
        raise Skip("dimension has no rendered text")
    b = boxes[0]
    doc.modelspace().add_text("0", height=b.extmax.y - b.extmin.y, dxfattribs={"layer": "dims"}).set_placement(
        (b.extmin.x, b.extmin.y)
    )
    return Mutation(doc, ("drafting.clear",), SeededError(id="wrong-value", kind="wrong-value", x=dim.x, y=dim.y))


def _overlap_text_seen(before: Sheet, after: Sheet, m: Mutation, truth: Truth) -> bool:
    return len(after.texts) > len(before.texts)


def _solid_hidden(doc: Drawing, truth: Truth, rng: random.Random) -> Mutation:
    """The dashed geometry of a view that must show hidden features is made continuous."""
    sheet = parse(doc)
    hidden = [v for v in truth.views if v.hidden]
    if not hidden:
        raise Skip("no view required to show hidden features")
    found = regions(sheet)
    for v in hidden:
        r = next((r for r in found if abs(r.width - v.width) <= 0.5 and abs(r.height - v.height) <= 0.5), None)
        if r is None:
            continue
        dashed = [e for e in r.entities if linetype_class(doc, e) == "dashed"]
        if not dashed:
            continue
        for e in dashed:
            e.dxf.linetype = "CONTINUOUS"
            e.dxf.layer = "outline"
        x, y = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        return Mutation(doc, ("drafting.linetypes",), SeededError(id="missing-view", kind="missing-view", x=x, y=y))
    raise Skip("no dashed geometry in a view that shows hidden features")


def _solid_hidden_seen(before: Sheet, after: Sheet, m: Mutation, truth: Truth) -> bool:
    found = regions(after)
    r = min(found, key=lambda r: abs((r.x0 + r.x1) / 2 - m.error.x) + abs((r.y0 + r.y1) / 2 - m.error.y), default=None)
    if r is None:
        return False
    return not any(linetype_class(after.doc, e) == "dashed" for e in r.entities)


def _missing_hatch(doc: Drawing, truth: Truth, rng: random.Random) -> Mutation:
    """The section view loses its hatching."""
    if not any(v.hatch_area for v in truth.views):
        raise Skip("no section view required")
    hatches = [e for e in doc.modelspace() if e.dxftype() == "HATCH"]
    if not hatches:
        raise Skip("no hatch on the sheet")
    victim = rng.choice(hatches)
    b = ezbbox.extents([victim])
    x, y = (b.extmin.x + b.extmax.x) / 2, (b.extmin.y + b.extmax.y) / 2
    doc.modelspace().delete_entity(victim)
    return Mutation(doc, ("views.section",), SeededError(id="missing-view", kind="missing-view", x=x, y=y))


def _missing_hatch_seen(before: Sheet, after: Sheet, m: Mutation, truth: Truth) -> bool:
    def count(sheet: Sheet) -> int:
        return sum(1 for e in sheet.doc.modelspace() if e.dxftype() == "HATCH")

    return count(after) < count(before)


def _wrong_roughness(doc: Drawing, truth: Truth, rng: random.Random) -> Mutation:
    """An `Ra <v>` mark shows a different roughness value."""
    if not truth.finish:
        raise Skip("no roughness required")
    sheet = parse(doc)
    marks = [
        (t, float(m.group(1).replace(",", ".")))
        for t in sheet.texts
        if (m := re.match(r"Ra\s*(\d+(?:[.,]\d+)?)$", t.text.strip()))
    ]
    if not marks:
        raise Skip("no roughness mark on the sheet")
    text, old = rng.choice(marks)
    targets = [m for m in marks if m[1] == old and abs(m[0].x - text.x) <= 30 and abs(m[0].y - text.y) <= 30]
    new = rng.choice([v for v in (0.8, 1.6, 3.2, 6.3, 12.5) if v != old])
    hit = 0
    for entity in doc.modelspace():
        if entity.dxftype() != "TEXT" or not entity.dxf.text.strip().startswith("Ra"):
            continue
        if any(
            abs(entity.dxf.insert.x - m[0].x) <= REACH and abs(entity.dxf.insert.y - m[0].y) <= REACH for m in targets
        ):
            entity.dxf.text = f"Ra {new:g}"
            hit += 1
    if hit != len(targets):
        raise Skip("a mark is not a plain text entity")
    return Mutation(doc, ("finish.roughness",), SeededError(id="wrong-value", kind="wrong-value", x=text.x, y=text.y))


def _wrong_roughness_seen(before: Sheet, after: Sheet, m: Mutation, truth: Truth) -> bool:
    return _text_at(after, m.error.x, m.error.y) != _text_at(before, m.error.x, m.error.y)


MUTANTS: dict[str, Mutant] = {
    "wrong-value": Mutant(_wrong_value, _wrong_value_seen),
    "missing-dim": Mutant(_missing_dim, _missing_dim_seen),
    "wrong-fit": Mutant(_wrong_fit, _wrong_fit_seen),
    "wrong-title-field": Mutant(_wrong_title_field, _wrong_title_seen),
    "missing-view": Mutant(_missing_view, _missing_view_seen),
    "lying-text": Mutant(_lying_text, _lying_text_seen),
    "detached-dim": Mutant(_detached_dim, _detached_dim_seen),
    "off-sheet": Mutant(_off_sheet, _off_sheet_seen),
    "tiny-text": Mutant(_tiny_text, _tiny_text_seen),
    "overlap-text": Mutant(_overlap_text, _overlap_text_seen),
    "solid-hidden": Mutant(_solid_hidden, _solid_hidden_seen),
    "missing-hatch": Mutant(_missing_hatch, _missing_hatch_seen),
    "wrong-roughness": Mutant(_wrong_roughness, _wrong_roughness_seen),
}
