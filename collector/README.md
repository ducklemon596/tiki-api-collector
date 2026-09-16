# Collector Package

## Responsibility

This package contains the collector: browser transport, execution
coordination, durable storage, and optional benchmark reports. The standard
setup uses two Chrome workers. The CLI also supports four workers for
controlled benchmark experiments.

## Where It Fits

`main.py` is the main entry point. It sends `collect` to execution orchestration
and `monitor` to the benchmark package. `rerun.py` is a separate entry point
for replaying saved non-terminal IDs.

## Inputs

- Product IDs from the configured input text file.
- CLI batch range, per-browser concurrency, Selenium call size, and `run_dir`.
- A local Chrome installation used through Selenium.

## Outputs

A run directory with a manifest, aggregate summary and log, isolated worker
state, and optional throughput milestones.

## Important Files

- `main.py` - dispatches the `collect` and `monitor` commands.
- `rerun.py` - replays prior not-found and browser-error IDs.
- `config.py` - stable application defaults.
- `browser/` - Chrome transport, JavaScript, and response policy.
- `execution/` - partitioning, worker lifecycle, and concurrent coordination.
- `persistence/` - paths, checkpoints, progress, and durable metric journals.
- `benchmark/` - latency summaries and read-only monitoring.
- `utils/` - input parsing and product cleanup.

## Design Notes

- `persistence.paths` derives runtime storage from `run_dir`, not machine-specific settings.
- Execution uses browser, persistence, and utility modules. Benchmark modules read worker output after execution; they do not control workers.
- Run the public CLI with `uv run python collector/main.py collect ...` or `monitor ...`.
