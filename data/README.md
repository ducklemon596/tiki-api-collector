# Project Data

## Responsibility

This folder holds local collector input and generated benchmark/run artifacts.

## Where It Fits

The collector reads its default input from `data/input/`. Each collection writes
to a chosen directory under `data/runs/` unless `--run-dir` points elsewhere.

## Inputs

- `input/products-01.txt` — the default configured input; one numeric product ID per line.
- Optional `.xlsx` input files for the converter utility.

## Outputs

- `runs/<run-name>/` — manifests, summaries, logs, worker checkpoints, metric journals, and final batches.
- `runs/BENCHMARK_RESULTS.md` may be kept as a human-readable benchmark history.

## Important Files and Folders

- `input/` — source product IDs.
- `runs/` — runtime output root. Git normally ignores it because generated data can be large.

## Design Notes

- Use a separate `--run-dir` for each experiment. Its manifest rejects reuse with incompatible settings.
- You can inspect and resume existing run artifacts. Do not edit checkpoint journals by hand.
- The repository ignores generated runs. Benchmark files linked from the root README may therefore be local unless retained or published separately.
