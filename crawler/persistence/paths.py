"""Portable derivation of all persisted benchmark and checkpoint locations."""

from dataclasses import dataclass
from pathlib import Path

# Persisted names are compatibility-sensitive: existing run directories use them.
WORKERS_DIRECTORY_NAME = "workers"
WORKER_DIRECTORY_PREFIX = "browser-"
CHECKPOINTS_DIRECTORY_NAME = "checkpoints"
LOGS_DIRECTORY_NAME = "logs"
METRICS_DIRECTORY_NAME = "metrics"
SUCCESS_DIRECTORY_NAME = "success"
NOT_FOUND_DIRECTORY_NAME = "not_found"
FINAL_DIRECTORY_NAME = "final"
TERMINAL_METRICS_FILE_NAME = "terminal.jsonl"
PROGRESS_FILE_NAME = "progress.json"
STATE_FILE_NAME = "state.json"
MANIFEST_FILE_NAME = "benchmark_manifest.json"
SUMMARY_FILE_NAME = "benchmark_summary.json"
MILESTONES_FILE_NAME = "throughput_milestones.jsonl"
BENCHMARK_LOG_FILE_NAME = "benchmark.log"
EVENTS_LOG_FILE_NAME = "events.log"
NOT_FOUND_LOG_FILE_NAME = "not_found.log"


@dataclass(frozen=True)
class WorkerRunPaths:
    """Locations exclusively owned by one browser inside a benchmark run."""

    root: Path
    checkpoints: Path
    logs: Path
    terminal_metrics: Path
    progress: Path


@dataclass(frozen=True)
class BatchCheckpointPaths:
    """Persistent success, not-found, and final paths for one logical batch."""

    success_dir: Path
    not_found_dir: Path
    final_dir: Path
    success_file: Path
    not_found_file: Path
    final_file: Path


@dataclass(frozen=True)
class RunPaths:
    """Derive run-scoped files from one caller-provided ``run_dir``."""

    root: Path

    @property
    def manifest(self) -> Path:
        """Return the immutable benchmark configuration manifest path."""
        return self.root / MANIFEST_FILE_NAME

    @property
    def summary(self) -> Path:
        """Return the aggregate benchmark-summary path."""
        return self.root / SUMMARY_FILE_NAME

    @property
    def milestones(self) -> Path:
        """Return the monitor's append-only milestone journal path."""
        return self.root / MILESTONES_FILE_NAME

    @property
    def aggregate_log(self) -> Path:
        """Return the aggregate benchmark log path."""
        return self.root / BENCHMARK_LOG_FILE_NAME

    def worker(self, browser: int) -> WorkerRunPaths:
        """Return all persisted paths owned by one numbered Chrome worker."""
        worker_root = (
            self.root
            / WORKERS_DIRECTORY_NAME
            / f"{WORKER_DIRECTORY_PREFIX}{browser:02d}"
        )
        metrics = worker_root / METRICS_DIRECTORY_NAME
        return WorkerRunPaths(
            root=worker_root,
            checkpoints=worker_root / CHECKPOINTS_DIRECTORY_NAME,
            logs=worker_root / LOGS_DIRECTORY_NAME,
            terminal_metrics=metrics / TERMINAL_METRICS_FILE_NAME,
            progress=metrics / PROGRESS_FILE_NAME,
        )

    def worker_terminal_metrics(self) -> list[Path]:
        """Return existing terminal metric journals for read-only monitoring."""
        return list(
            (self.root / WORKERS_DIRECTORY_NAME).glob(
                f"{WORKER_DIRECTORY_PREFIX}*/{METRICS_DIRECTORY_NAME}/"
                f"{TERMINAL_METRICS_FILE_NAME}"
            )
        )

    def worker_progress_files(self) -> list[Path]:
        """Return existing active-elapsed progress files for read-only monitoring."""
        return list(
            (self.root / WORKERS_DIRECTORY_NAME).glob(
                f"{WORKER_DIRECTORY_PREFIX}*/{METRICS_DIRECTORY_NAME}/"
                f"{PROGRESS_FILE_NAME}"
            )
        )


def batch_checkpoint_paths(
    checkpoints_dir: Path, batch_number: int
) -> BatchCheckpointPaths:
    """Derive legacy-compatible checkpoint file names for one batch."""
    success_dir = checkpoints_dir / SUCCESS_DIRECTORY_NAME
    not_found_dir = checkpoints_dir / NOT_FOUND_DIRECTORY_NAME
    final_dir = checkpoints_dir / FINAL_DIRECTORY_NAME
    batch_label = f"{batch_number:04d}"
    return BatchCheckpointPaths(
        success_dir=success_dir,
        not_found_dir=not_found_dir,
        final_dir=final_dir,
        success_file=success_dir / f"success_batch_{batch_label}.jsonl",
        not_found_file=not_found_dir / f"not_found_batch_{batch_label}.jsonl",
        final_file=final_dir / f"tiki_batch_{batch_label}.json",
    )
