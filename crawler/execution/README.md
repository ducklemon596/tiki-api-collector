# Execution

## Responsibility

Owns crawl execution rather than benchmark analysis: deterministic workload partitioning, persistent Chrome worker lifecycle, shared stop coordination, and crawl CLI composition.

## Where It Fits

`main.py crawl` calls `orchestration.py`. The default starts two worker threads,
each with one Chrome and one isolated persistence tree. `--browser-count 4` is
available for controlled benchmark experiments.

## Inputs

- Selected logical input batches.
- Browser count, concurrency, call size, and caller-provided `run_dir`.
- Browser responses produced by `browser/`.

## Outputs

- Worker-boundary data for benchmark summary construction.
- Terminal checkpoints, metrics journal rows, state files, and final batches through `persistence/`.

## Important Files

- `orchestration.py` - crawl CLI parser and worker composition.
- `partitioning.py` - ordered chunking and contiguous browser assignments.
- `worker.py` - stop state, resumable batches, worker lifecycle, and terminal persistence decisions.

## Design Notes

- Selected IDs are split into deterministic contiguous partitions before either browser starts.
- Each worker owns its checkpoint/log/metric files; no checkpoint has concurrent writers.
- A WAF first stops new in-page request scheduling, then retries after 5, 10,
  and 20 minutes. Only a WAF still present after those attempts records the
  shared cutoff. Terminal results ending at or before that cutoff are persisted.
- Browser errors are counted across a worker attempt; reaching the configured
  threshold stops new work. WAF and error results remain resumable.
- Timeouts and known transient browser transport failures retry with the short
  1/2-second exponential backoff. HTTP 404/410 is terminal and never retried.
