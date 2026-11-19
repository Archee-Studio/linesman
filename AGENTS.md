# Linesman

A benchmark that scores generated 2D drafting sheets (DXF) against the calculation they came from. Read [docs/spec.md](docs/spec.md) before changing anything: words, folders, scoring and the code contract.

## Commands

```sh
uv sync
uv run ruff format --check src tests tools && uv run ruff check src tests tools
uv run pytest -q                                   # all tests; one file: uv run pytest -q tests/test_views.py
uv run linesman calibrate --families all --seeds 5 # every check proven on every family
uv run python tools/banner.py assets               # regenerate the README banner
```

## Map

| Path | Holds |
| --- | --- |
| `src/linesman/sheet.py` | The gate and the parsed sheet. Only `sheet.load` opens a submitted file. |
| `src/linesman/checks/` | One module per part; `CHECKS` is the registry. |
| `src/linesman/families/` | Parametric part families; `FAMILIES` is the registry. |
| `src/linesman/mutate.py` | Seeded defects; `MUTANTS` is the registry. |
| `src/linesman/calibrate.py` | The proof that every check passes good sheets and fails its defect. |
| `src/linesman/iso286.py` | ISO 286-1 limit deviations. |

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
