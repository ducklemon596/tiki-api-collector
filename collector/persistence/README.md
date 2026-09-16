# Persistence

## Responsibility

This package derives portable run paths and stores checkpoint journals,
immutable final batches, active elapsed time, manifests, and terminal latency
journals safely.

## Where It Fits

Execution workers write through this package. Benchmark summaries and the
monitor read its durable files during or after a run.

## Inputs

- Caller-provided `run_dir`, browser number, batch number, and terminal results.
- Active elapsed time and immutable run configuration.

## Outputs

- Isolated `workers/browser-XX` paths.
- Append-only success/not-found JSONL journals, resumable error JSONL, `state.json`, final batch JSON, `progress.json`, and terminal metrics JSONL.

## Important Files

- `paths.py` - run and checkpoint path dataclasses; keeps legacy on-disk names.
- `checkpoint.py` - append-only checkpoints, partial-final-line repair, finalization, manifests, and atomic JSON writing.
- `progress.py` - active elapsed persistence plus durable terminal and browser-error journals.

## Design Notes

- Durable checkpoint journals are the source of truth after restart; `state.json` is informational.
- Final batch JSON is written only after every assigned ID is terminal. Its presence makes the batch immutable.
- Terminal metrics are journaled before checkpoint writes. Summaries then filter them through completed checkpoint IDs to avoid metric records left behind by a crash.
