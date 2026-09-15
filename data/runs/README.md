# Benchmark Run Artifacts

## Responsibility

This folder is the default home for generated crawl runs and the retained human-readable benchmark record.

## Where It Fits

`crawl --run-dir data/runs/<name>` creates an isolated run root here. The root README uses the retained benchmark ledger to describe measured performance.

## Inputs

- A caller-selected run name passed through `--run-dir`.
- Product IDs, crawler configuration, and browser results from a benchmark run.

## Outputs

- One run directory with its manifest, aggregate summary/log, per-browser checkpoints, logs, metrics, and final batches.
- `BENCHMARK_RESULTS.md`, a compact historical ledger of controlled experiments.

## Important Files

- `BENCHMARK_RESULTS.md` — recorded 500- to 20,000-ID controlled comparisons and notes on historical multi-browser experiments.
- `<run>/benchmark_summary.json` — final authoritative summary for one completed or stopped run.
- `<run>/workers/browser-XX/` — isolated durable state for one browser worker.

## Design Notes

- Generated run directories remain ignored by Git because they can be large and may be deleted after analysis.
- The README and benchmark ledger are explicitly unignored so a portfolio repository can retain the methodology and measured results without committing raw checkpoint data.
- Treat a completed run's `benchmark_summary.json` and its durable checkpoint journals as the authoritative record; monitor milestones are operational observations.
