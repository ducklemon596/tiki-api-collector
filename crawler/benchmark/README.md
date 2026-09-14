# Benchmark

## Responsibility

Contains measurement logic that observes completed crawl state: latency calculations, durable per-browser/aggregate summaries, and live throughput milestones.

## Where It Fits

Execution returns worker-boundary data after Chrome sessions end. `benchmark.summary` builds the final result from durable state; `main.py monitor` runs the read-only monitor.

## Inputs

- Worker-boundary execution data and isolated persistence paths.
- Durable terminal metric journals, checkpoints, and active elapsed files.

## Outputs

- Per-browser and aggregate benchmark summaries.
- `benchmark_summary.json` and optional `throughput_milestones.jsonl` observations.

## Important Files

- `metrics.py` - mean, median, and nearest-rank P95 latency calculation.
- `summary.py` - durable browser and aggregate summary construction.
- `monitor.py` - incremental terminal-journal tailing and milestone recording.

## Design Notes

- Summary data is rebuilt from durable checkpoints so it remains meaningful after a restart.
- Active elapsed time excludes idle gaps between process attempts.
- Monitor output is operational telemetry; the final summary and checkpoints are authoritative.
