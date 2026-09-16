"""Write durable throughput snapshots for a two-browser benchmark."""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence, TypedDict

from config import (
    DEFAULT_MONITOR_INTERVAL_SECONDS,
    DEFAULT_MONITOR_MILESTONE,
)
from persistence.paths import RunPaths

class ProgressSnapshot(TypedDict):
    """One durable throughput observation written by the monitor."""

    completed_ids: int
    active_elapsed_seconds: float
    effective_ids_per_hour: float
    observed_at: str


class TerminalCounter:
    """Count appended terminal records incrementally, without rereading prior results."""

    def __init__(self) -> None:
        self._offsets: dict[Path, int] = {}
        self.completed = 0

    def update(self, metric_paths: list[Path]) -> int:
        """Read only bytes appended since the prior poll and return total records."""
        for path in metric_paths:
            offset = self._offsets.get(path, 0)
            with path.open("rb") as source:
                source.seek(offset)
                self.completed += source.read().count(b"\n")
                self._offsets[path] = source.tell()
        return self.completed


def snapshot(run_dir: Path, counter: TerminalCounter) -> ProgressSnapshot | None:
    """Read new terminal records and cumulative active time from one run directory."""
    paths = RunPaths(run_dir)
    metric_paths = paths.worker_terminal_metrics()
    progress_paths = paths.worker_progress_files()
    if not metric_paths or not progress_paths:
        return None
    completed = counter.update(metric_paths)
    elapsed_values: list[float] = []
    for path in progress_paths:
        for attempt in range(4):
            try:
                elapsed_values.append(
                    float(
                        json.loads(path.read_text(encoding="utf-8"))[
                            "active_elapsed_seconds"
                        ]
                    )
                )
                break
            except (FileNotFoundError, PermissionError, json.JSONDecodeError):
                time.sleep(0.05 * (attempt + 1))
        else:
            return None
    elapsed = max(elapsed_values)
    return {
        "completed_ids": completed,
        "active_elapsed_seconds": round(elapsed, 3),
        "effective_ids_per_hour": (
            round(completed * 3600 / elapsed, 2) if elapsed else 0.0
        ),
        "observed_at": datetime.now(UTC).isoformat(),
    }


def benchmark_finished(summary_path: Path) -> bool:
    """Return whether a durable summary records completion or a terminal stop.

    A missing summary remains resumable because the collector may restart after a crash.
    A summary with a stop reason ends monitoring; otherwise every assigned ID must have
    reached a success or not-found checkpoint.
    """
    if not summary_path.exists():
        return False
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    success_count = summary.get("success_count")
    not_found_count = summary.get("not_found_count")
    total_ids = summary.get("total_ids")
    if (
        not isinstance(success_count, int)
        or not isinstance(not_found_count, int)
        or not isinstance(total_ids, int)
    ):
        return False
    return summary.get("stop_reason") is not None or success_count + not_found_count == total_ids


def main(argv: Sequence[str] | None = None) -> None:
    """Append one snapshot whenever a new configured completion milestone is reached."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--milestone", type=int, default=DEFAULT_MONITOR_MILESTONE)
    parser.add_argument(
        "--interval", type=float, default=DEFAULT_MONITOR_INTERVAL_SECONDS
    )
    args = parser.parse_args(argv)
    run_paths = RunPaths(args.run_dir)
    output = run_paths.milestones

    recorded = (
        {
            int(json.loads(line)["completed_ids"])
            for line in output.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        if output.exists()
        else set()
    )
    next_milestone = max(recorded, default=0) + args.milestone
    counter = TerminalCounter()

    while True:
        current = snapshot(args.run_dir, counter)
        if current and current["completed_ids"] >= next_milestone:
            with output.open("a", encoding="utf-8") as destination:
                json.dump(current, destination)
                destination.write("\n")
                destination.flush()
            next_milestone += args.milestone

        if benchmark_finished(run_paths.summary):
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
