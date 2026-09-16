# Selenium Product Collector

## Project Overview

This resumable collector gets Tiki product API responses through real
Selenium-controlled Chrome sessions. It focuses first on correct, durable
collection, then uses controlled benchmarks to improve throughput.

**Recommended configuration:** 2 persistent Chrome sessions × 4 bounded
browser-side `fetch()` requests per session (2 Chrome × C4).

## Key Engineering Highlights

- **Browser-context requests:** API calls run inside Chrome, not through a
  separate Python HTTP client.
- **Bounded concurrency:** each Chrome uses a fixed JavaScript worker pool.
  The collector never creates an unbounded `Promise.all()` burst.
- **Safe parallelism:** deterministic contiguous ID partitions and isolated
  per-browser state prevent concurrent checkpoint writers.
- **Crash-safe progress:** append-only terminal journals, immutable completed
  batches, and a manifest make resume safe and idempotent.
- **Failure-aware behavior:** terminal responses, WAF challenges, and browser
  errors are handled differently so unfinished work can be recovered.
- **Measured tuning:** durable timings, logs, summaries, and monitor milestones
  show throughput and latency trade-offs.

## Architecture

```text
Product IDs
    |
    v
Batching + deterministic contiguous partitions
    |
    +-------------------------+
    |                         |
    v                         v
Chrome worker 1          Chrome worker 2
bounded JS fetch pool    bounded JS fetch pool
    |                         |
    +-----------+-------------+
                v
  classify: success / not-found / WAF / error
                |
    +-----------+-------------+
    |                         |
    v                         v
terminal checkpoints     terminal metrics
(isolated per worker)    + progress journals
    |                         |
    +-----------+-------------+
                v
      aggregate summary and monitor milestones
```

## Reliability and Failure Handling

Only successful JSON responses and HTTP 404/410 responses are terminal. They
are written to durable JSONL journals. A batch becomes immutable only after
every ID is terminal. Re-run the original command to reload checkpoints and
fetch only unfinished IDs.

The run manifest requires the batch range, browser count, browser concurrency,
and Selenium call size to match. Active elapsed time excludes idle time between
restarts when calculating effective IDs/hour.

| Outcome | Behavior |
| --- | --- |
| HTTP 200 + valid JSON | Success; checkpointed. |
| HTTP 404/410 | Not found; checkpointed and never retried. |
| Timeout or known browser/network transient | Retries after 1s, then 2s; stays resumable if unresolved. |
| WAF/challenge | Stops new in-page scheduling; retries after 5, 10, and 20 minutes. A persistent challenge triggers a global stop and leaves unfinished IDs resumable. |
| Other browser error | Written to a structured error journal and left resumable. |

`rerun.py` selects unique IDs from structured not-found checkpoints and error
journals. It saves that selection in a separate destination run and sends it
through the normal collector pipeline. The source run is unchanged, and reruns
can resume.

## Benchmark Highlights

Tests use persistent Chrome, browser-side JavaScript `fetch()`, no artificial
delay, and bounded concurrency. Throughput depends on the host, network, and
upstream conditions.

| Stage | Configuration | Sample | IDs/hour | Measured result |
| --- | --- | ---: | ---: | --- |
| Starting point | 1 Chrome × C1 | 500 | 28,061 | Sequential browser fetches |
| Bounded concurrency | 1 Chrome × C4 | 500 | 70,297 | 2.51× on the same sample |
| Stable single-browser baseline | 1 Chrome × C4 | 10,000 | 113,234 | Sustained C4 run |
| Higher single-browser concurrency | 1 Chrome × C8 | 10,000 | 152,620 | 1.35× vs 1 Chrome × C4 |
| Two-browser baseline | 2 Chrome × C4 | 10,000 | 192,140 | Aggregate concurrency remains 8 |
| **Recommended stable baseline** | **2 Chrome × C4** | **20,000** | **193,457** | **0 WAF / 0 errors; P95 280.5 ms** |
| Higher aggregate concurrency | 2 Chrome × C8 | 20,000 | 200,086 | +3.4%; P95 484.3 ms |
| More browser processes | 4 Chrome × C4 | 20,000 | 199,951 | +3.4%; P95 577.1 ms |

Bounded concurrency and a second Chrome produced the main gains. In the stable
20,000-ID comparison, doubling aggregate concurrency added only about **3.4%**
while increasing tail latency substantially. For rate, latency, memory use,
and simplicity, 2 Chrome × C4 remains the practical default.

See [the full benchmark record](data/runs/BENCHMARK_RESULTS.md) for history,
methodology, reproducibility notes, and historical comparisons.

## Usage

Requirements: Python 3.13+, Google Chrome, and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
```

Put one numeric product ID per line in `data/input/products-01.txt`.

Run the default full input (batches 1–200, up to 200,000 IDs):

```bash
uv run python collector/main.py collect
```

Run a smaller sample in its own output directory:

```bash
uv run python collector/main.py collect --start-batch 1 --end-batch 10 --run-dir data/runs/my-10k-run
```

Resume an interrupted run with the same options:

```bash
uv run python collector/main.py collect --start-batch 1 --end-batch 10 --run-dir data/runs/my-10k-run
```

Monitor a running collection in another terminal:

```bash
uv run python collector/main.py monitor --run-dir data/runs/my-10k-run
```

Rerun structured not-found and browser-error IDs in a separate run:

```bash
uv run python collector/rerun.py --source-run data/runs/my-10k-run --run-dir data/runs/my-10k-rerun
```

Show all supported options:

```bash
uv run python collector/main.py collect --help
uv run python collector/main.py monitor --help
uv run python collector/rerun.py --help
```

## Project Structure

```text
collector/
├── config.py          stable collector defaults and optional local driver override
├── main.py            `collect` and `monitor` command entry point
├── rerun.py           standalone replay of persisted not-found/error IDs
├── browser/
│   ├── client.py      persistent Selenium transport and raw result normalization
│   ├── scripts.py     bounded browser-side JavaScript fetch worker pool
│   └── classification.py  terminal/resumable response classification
├── execution/
│   ├── orchestration.py  CLI composition and concurrent worker startup
│   ├── partitioning.py  deterministic batching and contiguous ID partitions
│   └── worker.py        browser lifecycle, retries, stop state, persistence flow
├── persistence/
│   ├── checkpoint.py    append-only checkpoints, final batches, atomic writes
│   ├── progress.py      active-time, terminal-metric, and error journals
│   └── paths.py         run-scoped path derivation
├── benchmark/
│   ├── metrics.py       latency and throughput calculations
│   ├── summary.py       per-browser and aggregate summaries
│   └── monitor.py       read-only milestone monitor
├── utils/               input loading and product cleanup
└── logger/              UTF-8 file logger setup

data/
├── input/               source product-ID files
└── runs/                generated runs and retained benchmark documentation
tests/                   focused regression tests without live Chrome/API calls
converter/               optional XLSX-to-ID-text helper
```

The dependency flow is simple: browser transport, persistence, and utilities
are lower-level modules; execution coordinates them; benchmark modules read
durable execution output. This keeps measurement separate from collection.

Each `<run-dir>` contains:

- `benchmark_manifest.json` — immutable settings used to validate resume.
- `benchmark_summary.json` — aggregate counts, latency, elapsed time, and rate.
- `workers/browser-XX/` — isolated checkpoints, logs, metrics, and progress for
  one Chrome worker.
- `workers/browser-XX/metrics/errors.jsonl` — structured resumable browser
  errors used by reruns.
- `throughput_milestones.jsonl` — optional monitor observations.

## Engineering Takeaways

- Build a stable, observable collection baseline before optimizing.
- Change one concurrency setting at a time. Measure both rate and tail latency;
  more parallelism is not always better.
- Use durable terminal state as the source of truth so restarts are predictable
  and idempotent.
- Keep non-terminal outcomes for later recovery instead of losing useful data.

Use the collector only with authorization and in accordance with the target
service's terms and applicable law.

## Troubleshooting: The collector starts, but no Chrome browser opens

This is usually an environment or Selenium Manager driver-resolution issue,
not collection logic.

Try the following:

1. Stop any stuck collection, Chrome, or ChromeDriver processes.
2. Test Selenium independently with a minimal `webdriver.Chrome()` script: `uv run python -c "from selenium import webdriver; driver = webdriver.Chrome(); driver.quit()"`
3. Check whether a ChromeDriver executable is available on your system.
4. Verify that Chrome and ChromeDriver versions are compatible.
5. If Selenium Manager appears stuck, clear/reset its driver cache and try again.
6. If automatic driver resolution still fails, download a compatible ChromeDriver
   manually and set `CHROMEDRIVER_PATH` in `collector/config.py`.

The exact commands vary by operating system.
