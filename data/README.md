# Project Data

## Responsibility

Holds local crawler inputs and generated benchmark/run artifacts.

## Where It Fits

The crawler reads its default input from `data/input/`. Every crawl writes to a chosen directory under `data/runs/` unless `--run-dir` points elsewhere.

## Inputs

- `input/products-01.txt` — one numeric product ID per line; the default configured input.
- Optional `.xlsx` input files for the converter utility.

## Outputs

- `runs/<run-name>/` — generated manifests, summaries, logs, worker checkpoints, metric journals, and final batches.
- `runs/BENCHMARK_RESULTS.md` may be retained as a human-readable historical benchmark ledger.

## Important Files and Folders

- `input/` — source product IDs.
- `runs/` — runtime output root; normally ignored by Git because it can contain large generated data.

## Design Notes

- Keep a distinct `--run-dir` for each experiment. Reusing a directory with incompatible settings is rejected by its manifest.
- Existing run artifacts can be used for forensic inspection and resume. Do not manually edit checkpoint journals.
- The source repository ignores generated runs, so benchmark files referenced by the root README may be local artifacts unless separately retained or published.
