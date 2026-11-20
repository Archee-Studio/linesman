<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Archee-Studio/linesman/main/assets/banner-dark.png">
  <img alt="Linesman by Archee Studio: a stepped shaft drawn and dimensioned, stamped PASS 1.00" src="https://raw.githubusercontent.com/Archee-Studio/linesman/main/assets/banner-light.png">
</picture>

**Can your agent draft?** Linesman gives it an engineering request, takes back one DXF and scores the file itself: views, dimensions, ISO 286 fits and the title block. Any model, agent or CAD tool can enter.

```sh
pip install linesman-bench                                    # just the grader, from PyPI
uv sync                                                       # or work in this checkout
uv run linesman build --split dev --out dev                  # the practice split
runner/run.sh devin dev out 1 --no-docker                     # run a local harness on it (or your own)
uv run linesman grade dev out/submissions/run1 --out r.json   # score the submissions
uv run linesman report r.json                                 # the board
```

The benchmark protocol (splits, sandbox, k runs, grading) is [docs/protocol.md](https://github.com/Archee-Studio/linesman/blob/main/docs/protocol.md).

Nine part families, sixteen checks, a `review` track for finding seeded errors, and a grader proven on every family. The contract is [docs/spec.md](https://github.com/Archee-Studio/linesman/blob/main/docs/spec.md).

## For agents

Paste this into your coding agent:

```text
Read AGENTS.md and docs/spec.md in this repository. Then generate 5 shaft tasks, draft a DXF for each, grade them with Linesman and fix every failed check.
```

## Licence

Code Apache-2.0, task data CC BY 4.0. Cite with [CITATION.cff](https://github.com/Archee-Studio/linesman/blob/main/CITATION.cff). Task data: [huggingface.co/datasets/archee-studio/linesman](https://huggingface.co/datasets/archee-studio/linesman).
