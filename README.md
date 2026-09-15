# Selenium Product Crawler

## Project Overview

A resumable crawler for collecting Tiki product API responses through real,
Selenium-controlled Chrome sessions. It prioritizes correct, durable data
collection first, then improves throughput through controlled benchmarks.

**Recommended configuration:** 2 persistent Chrome sessions × 4 bounded
browser-side `fetch()` requests per session (2 Chrome × C4).

## Key Engineering Highlights

- **Browser-context requests:** API calls execute inside Chrome rather than a
  separate Python HTTP client.
- **Bounded concurrency:** each Chrome runs a fixed JavaScript worker pool;
  the crawler never creates an unbounded `Promise.all()` burst.
- **Safe parallelism:** deterministic contiguous ID partitions and isolated
  per-browser state prevent concurrent checkpoint writers.
- **Crash-safe progress:** append-only terminal journals, immutable finalized
  batches, and a manifest make resume idempotent.
- **Failure-aware behavior:** terminal responses, WAF challenges, and browser
  errors are handled differently so unfinished work remains recoverable.
- **Measured tuning:** durable request timings, logs, summaries, and monitor
  milestones make throughput and latency trade-offs visible.

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

Only successful JSON and HTTP 404/410 responses are terminal. They are written
to durable JSONL journals, and a batch becomes immutable only after every ID is
terminal. Repeating the original command reloads checkpoints and fetches only
unfinished IDs.

The run manifest requires the batch range, browser count, browser concurrency,
and Selenium call size to match. Active elapsed time excludes idle time between
restarts from effective IDs/hour.

| Outcome | Behavior |
| --- | --- |
| HTTP 200 + valid JSON | Success; checkpointed. |
| HTTP 404/410 | Not found; checkpointed and never retried. |
| Timeout or known browser/network transient | Retries after 1s, then 2s; remains resumable if unresolved. |
| WAF/challenge | Stops new in-page scheduling; retries after 5, 10, and 20 minutes. A persistent challenge coordinates a global stop and leaves unfinished IDs resumable. |
| Other browser error | Logged to a structured error journal and left resumable. |

`rerun.py` selects unique IDs from structured not-found checkpoints and error
journals, freezes the selection in a separate destination run, and reuses the
normal crawler pipeline. The source run stays unchanged; reruns are resumable.

## Benchmark Highlights

Tests use persistent Chrome, browser-side JavaScript `fetch()`, zero artificial
delay, and bounded concurrency. Throughput varies with host, network, and upstream conditions.

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

The progression shows that bounded concurrency and a second Chrome delivered
the meaningful gains. In the stable 20,000-ID comparison, doubling aggregate
concurrency added only about **3.4%** while substantially increasing tail
latency. Therefore 2 Chrome × C4 remains the practical default for rate,
latency, memory use, and operational simplicity.

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
uv run python crawler/main.py crawl
```

Run a smaller sample in its own output directory:

```bash
uv run python crawler/main.py crawl --start-batch 1 --end-batch 10 --run-dir data/runs/my-10k-run
```

Resume an interrupted run with the same options:

```bash
uv run python crawler/main.py crawl --start-batch 1 --end-batch 10 --run-dir data/runs/my-10k-run
```

Monitor a running crawl in another terminal:

```bash
uv run python crawler/main.py monitor --run-dir data/runs/my-10k-run
```

Rerun structured not-found and browser-error IDs into a separate run:

```bash
uv run python crawler/rerun.py --source-run data/runs/my-10k-run --run-dir data/runs/my-10k-rerun
```

For all supported options:

```bash
uv run python crawler/main.py crawl --help
uv run python crawler/main.py monitor --help
uv run python crawler/rerun.py --help
```

## Project Structure

```text
crawler/
├── config.py          stable crawler defaults and optional local driver override
├── main.py            `crawl` and `monitor` command entry point
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

The dependency direction is intentionally simple: browser transport,
persistence, and utilities are low-level modules; execution coordinates them;
benchmark modules consume durable execution output. This keeps measurement
separate from crawling behavior.

Each `<run-dir>` contains:

- `benchmark_manifest.json` — immutable settings used to validate resume.
- `benchmark_summary.json` — aggregate counts, latency, elapsed time, and rate.
- `workers/browser-XX/` — isolated checkpoints, logs, metrics, and progress for
  one Chrome worker.
- `workers/browser-XX/metrics/errors.jsonl` — structured resumable browser
  errors used by reruns.
- `throughput_milestones.jsonl` — optional monitor observations.

## Engineering Takeaways

- Establish a stable, observable data-collection baseline before optimizing.
- Increase one concurrency variable at a time and measure both rate and tail
  latency; more parallelism is not automatically a better operating point.
- Treat durable terminal state as the source of truth so restarts are
  predictable and idempotent.
- Preserve non-terminal outcomes for later recovery instead of silently losing
  potentially useful data.

Use the crawler only with authorization and in accordance with the target
service's terms and applicable law.
