"""The one registry of mutants: a reference sheet with one seeded defect, and the proof that the defect is visible.

A mutant is applied with `apply`, which works on a copy, saves and reloads it, and only returns a mutation whose
witness holds in the reloaded file (the value text differs, the entity is gone). A defect with no witness is not
counted: `apply` raises `Skip` for it, as it does for a mutant that does not fit the family.
"""

import io
import random
from collections.abc import Callable
from dataclasses import dataclass

import ezdxf
from ezdxf.document import Drawing

from ..schema import SeededError, Truth
from ..sheet import Sheet, parse

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


from ._mutants import MUTANTS  # noqa: E402

# Mutants that are also reviewable defects (their error kinds are in the review vocabulary).
REVIEW_MUTANTS = ("wrong-value", "missing-dim", "wrong-fit", "wrong-title-field", "missing-view")


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
    names = sorted(REVIEW_MUTANTS)
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
