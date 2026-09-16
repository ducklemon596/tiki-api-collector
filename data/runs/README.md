# Benchmark Run Artifacts

## Responsibility

This folder is the default location for generated collection runs and the
saved human-readable benchmark record.

## Where It Fits

`collect --run-dir data/runs/<name>` creates an isolated run here. The root
README uses the saved benchmark ledger to describe measured performance.

## Inputs

- A run name supplied through `--run-dir`.
- Product IDs, collector configuration, and browser results from a benchmark run.

## Outputs

- One run directory with its manifest, aggregate summary/log, per-browser checkpoints, logs, metrics, and final batches.
- `BENCHMARK_RESULTS.md`, a compact history of controlled experiments.

## Important Files

- `BENCHMARK_RESULTS.md` — recorded 500- to 20,000-ID controlled comparisons and notes on historical multi-browser experiments.
- `<run>/benchmark_summary.json` — final authoritative summary for one completed or stopped run.
- `<run>/workers/browser-XX/` — isolated durable state for one browser worker.

## Design Notes

- Git ignores generated run directories because they can be large and may be deleted after analysis.
- The README and benchmark ledger are explicitly unignored. A portfolio repository can therefore keep methodology and measured results without committing raw checkpoint data.
- Treat a completed run's `benchmark_summary.json` and durable checkpoint journals as the authoritative record. Monitor milestones are operational observations.
