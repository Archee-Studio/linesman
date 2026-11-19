# Linesman spec 0.1.0

Linesman scores generated 2D mechanical drafting sheets against the calculation they came from. It reads files only; how a sheet was made is not scored.

## Words

| Word | Meaning |
| --- | --- |
| Task | One folder a system must answer. |
| Track | The kind of task: `calc-sheet` (draw a detail sheet from typed parameters) or `review` (find the seeded errors in a sheet). |
| Family | A parametric part type that generates tasks: `plate`, `shaft`, `flange`, `bushing`, `gear-blank`, `bracket`. |
| Truth | `truth.json`: the required features of the answer. Never a golden drawing to imitate. |
| Submission | The files a system returns for one task. |
| Check | One deterministic test with an id, a part, a criticality and a score from 0 to 1. |
| Part | A group of checks reported together: `gate`, `views`, `dims`, `fits`, `titleblock`, `review`. |
| Variant | Another valid answer for the same truth (other view or dimension placement). Must score 1. |
| Mutant | A reference sheet with one seeded defect. Must drop the check it targets. |

## Task folder

```text
<task-id>/
  task.json      Task: id, track, family, seed, spec version
  task.md        the request in plain English
  inputs.json    typed parameters, every length in millimetres
  sheet.dxf      review track only: the sheet to review
  truth.json     hidden from systems; kept beside the task in the private copy
```

## Submission folder

```text
<task-id>/
  sheet.dxf      calc-sheet track: DXF R2018 or later, $INSUNITS = 4 (mm)
  findings.json  review track: list of Finding
```

Sheet rules every entrant can read: first-angle projection (ISO 128 / TCVN), dimensions as DIMENSION entities (exploded dimensions are plain lines and text and do not count), the displayed value is the override text when present, otherwise the measurement times DIMLFAC. One sheet frame (the outermost closed rectangle) and one title block: a closed rectangle at the frame's lower-right corner. Title-block fields count only when their text sits inside it. Tolerances and fits count only when shown in the dimension's own text; values set only in a dimension style are not read.

## Scoring

1. **Gate.** The file opens with `ezdxf.recover`, has no unrecoverable audit errors, declares millimetres, holds geometry, stays under the size, entity and block-nesting limits in `linesman.sheet.LIMITS`. A failed gate makes every other check 0.
2. **Parts.** Each check returns `CheckResult`. A part's score is the mean of its checks; a task passes only when every critical check passes.
3. **Reported per system:** valid rate, pass rate, score on valid files, score with failures as zero, each part, median and worst of k = 3 runs.

## Code contract

- `linesman.schema`: every model above (`Task`, `Truth`, `Finding`, `CheckResult`, `TaskResult`). Changing a field changes the spec version.
- `linesman.sheet.load(path) -> Sheet`: the gate and the parsed sheet (geometry, texts, dimensions). Checks never open files themselves.
- `linesman.checks.CHECKS`: the one registry. Each entry is a function `(sheet, task, truth) -> list[CheckResult]`. A test fails when a part has no check or a check has no calibration case.
- `linesman.families.FAMILIES`: the one registry of families. Each has `sample(seed) -> inputs`, `draw(inputs, layout) -> ezdxf.Document`, `truth(inputs) -> Truth`, `request(inputs) -> str`. `layout` 0 is the reference; other values are variants.
- `linesman.mutate.MUTANTS`: the one registry of mutants, each a `Mutant(run, witness)`. `mutate.apply` runs one on a copy of the sheet and returns a `Mutation` (the document, the checks it targets, the seeded error), or skips it when the witness cannot see the defect in the saved file.
- `linesman.calibrate`: for every family and seed, reference and variants score 1 on every check, each mutant fails its targeted checks, and the empty, title-block-only and copied-input sheets score near 0.

## Tolerances and fits

Linear and diameter values match when the displayed value equals the truth within 0.01 mm; angles within 0.1 degree. A fit matches when the designation (for example `H7`, `g6`) is shown with the value, or the limit deviations are shown and equal the ISO 286-1 values within 0.001 mm.
