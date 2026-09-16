# Benchmark

## Responsibility

This package measures completed collection state. It calculates latency,
writes durable per-browser and aggregate summaries, and records live throughput
milestones.

## Where It Fits

Execution returns data after Chrome sessions end. `benchmark.summary` builds
the final result from durable state. `main.py monitor` runs the read-only
monitor.

## Inputs

- Worker-boundary execution data and isolated persistence paths.
- Durable terminal metric journals, checkpoints, and active elapsed files.

## Outputs

- Per-browser and aggregate benchmark summaries.
- `benchmark_summary.json` and optional `throughput_milestones.jsonl` observations.

## Important Files

- `metrics.py` - calculates mean, median, and nearest-rank P95 latency.
- `summary.py` - builds durable browser and aggregate summaries.
- `monitor.py` - tails terminal journals and records milestones incrementally.

## Design Notes

- Summary data is rebuilt from durable checkpoints, so it remains useful after restart.
- Active elapsed time excludes idle gaps between process attempts.
- Monitor output is operational telemetry. The final summary and checkpoints are authoritative.
