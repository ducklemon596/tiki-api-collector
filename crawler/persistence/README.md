# Persistence

## Responsibility

Provides portable run-path derivation and crash-safe persistence for checkpoint journals, immutable final batches, active elapsed time, manifests, and terminal latency journals.

## Where It Fits

Execution workers write through this package. Benchmark summaries and monitoring read its durable files after or during a run.

## Inputs

- Caller-provided `run_dir`, browser number, batch number, and terminal results.
- Active elapsed time and immutable run configuration.

## Outputs

- Isolated `workers/browser-XX` paths.
- Append-only success/not-found JSONL journals, resumable error JSONL, `state.json`, final batch JSON, `progress.json`, and terminal metrics JSONL.

## Important Files

- `paths.py` - run and checkpoint path dataclasses; preserves legacy on-disk names.
- `checkpoint.py` - append-only checkpoints, partial-final-line repair, finalization, manifests, and atomic JSON writing.
- `progress.py` - active elapsed persistence plus durable terminal and browser-error journals.

## Design Notes

- Durable checkpoint journals are the source of truth after restart; `state.json` is informational.
- Final batch JSON is written only when all assigned IDs are terminal. Its existence makes the batch immutable.
- Terminal metrics are journaled before checkpoint writes, then summaries filter them through completed checkpoint IDs to avoid crash-orphan metric drift.
