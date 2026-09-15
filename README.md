# Selenium Product Crawler

A resumable product crawler that fetches Tiki product data API responses from inside real Chrome sessions.
It is designed to collect as much correct data as possible, keep a clear record
of every run, and improve throughput gradually through measurement.

The maintained configuration uses two persistent Chrome browsers with four
bounded browser-side `fetch()` requests in each browser.

## What It Provides

- Real Selenium/Chrome transport instead of a separate Python HTTP client.
- Bounded browser-side concurrency: no unlimited `Promise.all()` request burst.
- Deterministic ID partitions across two browser workers.
- Clear per-product, not-found, event, and aggregate logs.
- Durable checkpoints, terminal metrics, active elapsed time, and final run
  summaries.
- Idempotent resume: completed IDs are not fetched again.
- A standalone rerun command for structured not-found/error IDs.

## How It Works

```text
Product ID text file
        |
        v
Input batching + deterministic contiguous partitioning
        |
        +------------------------+
        |                        |
        v                        v
 Chrome worker 1            Chrome worker 2
 bounded JS fetch pool      bounded JS fetch pool
        |                        |
        +-----------+------------+
                    v
       classify: success / not-found / WAF / error
                    |
        +-----------+------------+
        |                        |
        v                        v
 Append-only checkpoint   Terminal metrics journal
 isolated per browser     isolated per browser
        |                        |
        +-----------+------------+
                    v
     durable aggregation, summary, and monitor milestones
```

Python starts two Chrome workers. Each browser receives its own contiguous ID
range, its own JavaScript worker pool, and its own checkpoint/log/metric tree.
This keeps persistence simple: two browsers never write the same checkpoint.

## Quick Start

Requirements:

- Python 3.13+
- Google Chrome
- `uv` recommended

Install dependencies:

```bash
uv sync
```

Put one numeric product ID per line in:

```text
data/input/products-01.txt
```

Run the default full crawl:

```bash
uv run python crawler/main.py crawl
```

| Default setting | Value |
| --- | --- |
| Browser workers | 2 persistent Chrome sessions |
| Browser-side concurrency | 4 fetches per Chrome |
| Input range | batches 1-200 (up to 200,000 IDs) |
| Selenium call size | 50 IDs |
| Output directory | `data/runs/default-crawl` |

Use a different output directory for a separate experiment:

```bash
uv run python crawler/main.py crawl --run-dir data/runs/my-full-run
```

For a smaller test, override the batch range:

```bash
uv run python crawler/main.py crawl --start-batch 1 --end-batch 10 --run-dir data/runs/my-10k-run
```

## Resume, Idempotency, and Logging

Run the exact same command again to resume. The manifest verifies that the
batch range, browser count, browser concurrency, and Selenium call size still
match. A finalized batch is immutable, so its IDs are skipped on every later
attempt. Partially completed batches reload their terminal IDs and fetch only
the remaining ones.

The run directory is the durable source of truth after a crash:

- Success and not-found records are append-only JSONL checkpoints.
- Final batch JSON is created only after every ID in that batch is terminal.
- `progress.json` stores cumulative active processing time; idle time between
  attempts is excluded from effective IDs/hour.
- Each browser writes readable event and not-found logs plus terminal metric
  records. The aggregate log and summary provide run-level metrics.
- On a WAF/challenge response, workers stop. Only terminal responses ending at
  or before the shared cutoff timestamp are persisted.
- WAF and timeout responses receive two bounded retries with 1s then 2s
  exponential backoff. Success and 404/410 responses are never retried.

## Monitor a Run

Run this in another terminal while the crawler is active:

```bash
uv run python crawler/main.py monitor --run-dir data/runs/default-crawl
```

It records periodic throughput milestones. Use `benchmark_summary.json` for the
final success/not-found counts, latency metrics, elapsed time, and IDs/hour.

## Rerun Not-Found and Error IDs

Create a new run from the structured results of an earlier run:

```bash
uv run python crawler/rerun.py --source-run data/runs/my-full-run --run-dir data/runs/my-full-run-rerun
```

The source run is never changed. The new run stores its selected IDs in
`rerun_metadata.json` and `rerun_ids.txt`, then uses the normal crawl command,
including timeout/WAF retries, checkpoints, and resume behavior.
`rerun_summary.json` reports recovered
successes, remaining not-found IDs, unresolved/error IDs, WAF state, and the
browser-error count.

Not-found IDs are always available from structured checkpoint JSONL files.
Error IDs are included only when the source run already has structured
`metrics/errors.jsonl`; older runs do not contain recoverable per-ID errors and
the tool intentionally does not parse human-readable logs.

## Benchmark Results

The benchmark work improved rate step by step while watching latency, memory,
classification correctness, and WAF/error signals.

| Configuration | IDs/hour | Speedup | WAF / browser errors |
| --- | ---: | ---: | --- |
| 1 Chrome x C1 | 28,061 | starting point | 0 / 0 |
| 1 Chrome x C4 | 70,297 | 2.51x vs C1 on the same 500-ID test | 0 / 0 |
| 1 Chrome x C4 | 113,234 | stable 10,000-ID baseline | 0 / 0 |
| 1 Chrome x C8 | 152,620 | 1.35x vs 1 Chrome x C4 | 0 / 0 |
| 2 Chrome x C4 | 192,140 | 1.25x vs 1 Chrome x C8; 6.61x vs earliest C1 trial | 0 / 0 |

Two Chrome x C4 is the default. It delivered the best practical balance:
compared with it, two Chrome x C8 gained only 0.02% throughput while sharply
raising tail latency, and four Chrome x C4 gained only 0.9% while roughly
doubling Chrome memory use. Full methodology and measurements are in
[data/runs/BENCHMARK_RESULTS.md](data/runs/BENCHMARK_RESULTS.md).

## Project Layout

```text
.
|-- crawler/
|   |-- main.py                 # crawl and monitor commands
|   |-- rerun.py                # standalone rerun command
|   |-- config.py               # stable defaults
|   |-- browser/                # Selenium client, JS fetch script, classification
|   |-- execution/              # partitioning, workers, WAF stop coordination
|   |-- persistence/            # checkpoints, active-time progress, run paths
|   |-- benchmark/              # latency metrics, summaries, monitor
|   |-- utils/                  # input parsing and product cleanup
|   `-- logger/                 # UTF-8 file logger setup
|-- data/
|   |-- input/                  # source product-ID text files
|   `-- runs/                   # generated runs and benchmark record
|-- tests/                      # focused regression tests
|-- converter/                  # optional XLSX-to-ID-text helper
`-- README.md
```

## Run Output

```text
<run-dir>/
|-- benchmark_manifest.json       # fixed settings; protects correct resume
|-- benchmark_summary.json        # final aggregate metrics
|-- benchmark.log                 # aggregate lifecycle and summary log
|-- throughput_milestones.jsonl   # monitor observations, if used
`-- workers/
    |-- browser-01/
    |   |-- checkpoints/
    |   |   |-- success/          # successful product JSONL journals
    |   |   |-- not_found/        # 404/410 JSONL journals
    |   |   `-- final/            # immutable completed-batch JSON
    |   |-- logs/
    |   |   |-- events.log        # request/classification events
    |   |   `-- not_found.log     # compact 404/410 ID log
    |   `-- metrics/
    |       |-- terminal.jsonl    # terminal result latency records
    |       |-- errors.jsonl      # retryable browser-error IDs for reruns
    |       `-- progress.json     # cumulative active elapsed seconds
    `-- browser-02/ ...
```

For a rerun, the root also contains `rerun_metadata.json`, `rerun_ids.txt`, and
`rerun_summary.json`.

## Engineering Lessons

- **Data first:** keep collecting valid API data with a stable browser setup,
  even before the rate is ideal. A reliable baseline is more useful than an
  aggressive design that loses or misclassifies data.
- **Improve gradually:** measure one concurrency or browser-count change at a
  time, then keep only improvements that remain stable.
- **Idempotency matters:** durable terminal checkpoints make restarts safe and
  make repeated commands predictable.
- **Rerun incomplete data:** retry structured not-found/error IDs in a separate
  run to recover more data without damaging the original run.
- **Rate has a cost:** more browsers and higher concurrency can raise throughput,
  but memory use and tail latency can grow faster than the gain.

## Useful Commands

```bash
uv run python crawler/main.py crawl --help
uv run python crawler/main.py monitor --help
uv run python crawler/rerun.py --help
```

Use the crawler only with authorization and in accordance with the target
service's terms and applicable law.
