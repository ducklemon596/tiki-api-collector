# Crawler Package

## Responsibility

Contains the supported two-browser crawler application: browser transport, execution coordination, durable persistence, and optional benchmark reporting.

## Where It Fits

`main.py` is the root application entrypoint. It dispatches `crawl` to execution orchestration and `monitor` to the benchmark subsystem.

## Inputs

- Product IDs from the configured input text file.
- CLI batch range, per-browser concurrency, Selenium call size, and `run_dir`.
- A local Chrome installation controlled through Selenium.

## Outputs

A run directory containing a manifest, aggregate summary/log, isolated worker state, and optional throughput milestones.

## Important Files

- `main.py` - `crawl` / `monitor` command dispatcher.
- `config.py` - stable application defaults only.
- `browser/` - Chrome transport, JavaScript, and response policy.
- `execution/` - partitioning, worker lifecycle, and concurrent coordination.
- `persistence/` - paths, checkpoints, progress, and durable metric journals.
- `benchmark/` - latency summaries and read-only monitoring.
- `utils/` - input parsing and product cleanup.

## Design Notes

- Runtime storage paths are derived from `run_dir` in `persistence.paths`, not from machine-specific configuration.
- Execution depends on browser, persistence, and utilities. Benchmark modules consume worker output after execution rather than controlling the workers.
- The public invocation remains `uv run python crawler/main.py crawl ...` or `monitor ...`.
