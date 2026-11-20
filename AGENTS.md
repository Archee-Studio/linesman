# Linesman

A benchmark that scores generated 2D drafting sheets (DXF) against the calculation they came from. Read [docs/spec.md](docs/spec.md) before changing anything: words, folders, scoring and the code contract.

## Commands

```sh
uv sync
uv run ruff format --check src tests && uv run ruff check src tests
uv run pytest -q                                   # all tests; one file: uv run pytest -q tests/test_views.py
uv run linesman calibrate --families all --seeds 5 # every check proven on every family
```

## Map

| Path | Holds |
| --- | --- |
| `src/linesman/sheet.py` | The gate and the parsed sheet. Only `sheet.load` opens a submitted file. |
| `src/linesman/checks/` | One module per part; `CHECKS` is the registry. |
| `src/linesman/checks/drafting.py` | Sheet hygiene: on-sheet, text size, clearance and linetype checks. |
| `src/linesman/geo.py` | Shared geometry: point-to-entity distance, linetype classes, text boxes. |
| `src/linesman/families/` | Parametric part families; `FAMILIES` is the registry. |
| `src/linesman/mutate.py` | Seeded defects; `MUTANTS` is the registry. |
| `src/linesman/calibrate.py` | The proof that every check passes good sheets and fails its defect. |
| `src/linesman/build.py`, `report.py`, `rules.py` | `linesman build|report|rules`: splits with canary and freeze hash, the metrics board, the entrant rules text. |
| `runner/` | The harness: prompt.txt, Dockerfile, run.sh — see docs/protocol.md. |
| `docs/` | spec.md, protocol.md and the Hugging Face dataset card. |
| `src/linesman/iso286.py` | ISO 286-1 limit deviations. |
| `src/linesman/iso273.py`, `src/linesman/din471.py`, `src/linesman/families/keys.py` | ISO 273 clearance holes, DIN 471 grooves, DIN 6885 keys — the tables calc level resolves against. |

## Rules

- Checks are deterministic and read the file only: no model judges, no raster scoring, no tags a drafter would not write.
- A new check, family or mutant gets a row in its registry; tests fail when one is missing.
- A check that does not apply returns nothing, never a free 1.0.
- Every check ships with calibration: the reference and its variants score 1, a targeted mutant fails it, empty sheets score near 0.
- Submitted files are hostile input.
- Lengths in millimetres, angles in degrees; ISO 286 values come from `iso286`, never typed into a check.
- Changing scoring or a record raises the version: the package in `pyproject.toml`, the schema in `linesman.schema.SPEC_VERSION` and the spec title.
- Comments are short and say why. Files stay under 20,000 bytes.
- Never edit `assets/` by hand: regenerate it.
- The package publishes to PyPI (`linesman-bench`) and the dev split to Hugging Face by the monorepo's manual release workflow; the test split is never uploaded.
