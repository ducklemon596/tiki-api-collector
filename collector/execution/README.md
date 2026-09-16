# Execution

## Responsibility

This package runs collections, not benchmark analysis. It partitions work
deterministically, manages persistent Chrome workers, shares stop state, and
composes the collection CLI.

## Where It Fits

`main.py collect` calls `orchestration.py`. By default it starts two worker
threads, each with one Chrome and one isolated persistence tree.
`--browser-count 4` is available for controlled benchmark experiments.

## Inputs

- Selected logical input batches.
- Browser count, concurrency, call size, and caller-provided `run_dir`.
- Browser responses from `browser/`.

## Outputs

- Worker-boundary data for benchmark summary construction.
- Terminal checkpoints, metric journal rows, state files, and final batches through `persistence/`.

## Important Files

- `orchestration.py` - parses the collection CLI and composes workers.
- `partitioning.py` - chunks IDs in order and assigns contiguous browser ranges.
- `worker.py` - manages stop state, resumable batches, worker lifecycle, and terminal persistence decisions.

## Design Notes

- Selected IDs are split into deterministic contiguous partitions before either browser starts.
- Each worker owns its checkpoint, log, and metric files, so no checkpoint has concurrent writers.
- A WAF stops new in-page request scheduling, then retries after 5, 10, and 20 minutes. Only a WAF that remains after those attempts records the shared cutoff. Terminal results ending at or before that cutoff are persisted.
- Browser errors are counted for each worker attempt. Reaching the configured threshold stops new work. WAF and error results remain resumable.
- Timeouts and known transient browser transport failures use the short 1/2-second exponential backoff. HTTP 404/410 is terminal and never retried.
