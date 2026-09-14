# Execution

## Responsibility

Owns crawl execution rather than benchmark analysis: deterministic workload partitioning, persistent Chrome worker lifecycle, shared stop coordination, and crawl CLI composition.

## Where It Fits

`main.py crawl` calls `orchestration.py`. It starts two worker threads, each of which owns one Chrome and one isolated persistence tree.

## Inputs

- Selected logical input batches.
- Browser count, concurrency, call size, and caller-provided `run_dir`.
- Browser responses produced by `browser/`.

## Outputs

- Worker-boundary data for benchmark summary construction.
- Terminal checkpoints, metrics journal rows, state files, and final batches through `persistence/`.

## Important Files

- `orchestration.py` - crawl CLI parser and two-worker composition.
- `partitioning.py` - ordered chunking and contiguous browser assignments.
- `worker.py` - stop state, resumable batches, worker lifecycle, and terminal persistence decisions.

## Design Notes

- Selected IDs are split into deterministic contiguous partitions before either browser starts.
- Each worker owns its checkpoint/log/metric files; no checkpoint has concurrent writers.
- The first WAF response records a shared cutoff. Only terminal results ending at or before that timestamp are persisted.
- Repeated browser errors stop new work; WAF and error results are deliberately left resumable.
