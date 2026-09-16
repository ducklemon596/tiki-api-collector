"""CLI collection composition for the configured browser-worker count."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time
from pathlib import Path
from typing import Sequence

from config import (
    ALLOWED_BROWSER_COUNTS,
    ALLOWED_BROWSER_CONCURRENCY,
    BROWSER_COUNT,
    DEFAULT_BROWSER_CONCURRENCY,
    DEFAULT_END_BATCH,
    DEFAULT_INPUT_FILE,
    DEFAULT_RUN_DIR,
    DEFAULT_SELENIUM_CALL_SIZE,
    DEFAULT_START_BATCH,
    INPUT_BATCH_SIZE,
)
from execution.partitioning import BatchAssignment, contiguous_assignments
from execution.worker import StopState, WorkerRunResult, run_browser
from logger import setup_logger
from persistence.checkpoint import prepare_manifest
from persistence.paths import RunPaths
from utils.input import load_and_batch_ids


@dataclass(frozen=True)
class CollectionExecution:
    """Completed worker execution supplied to the benchmark reporting layer.

    The execution package produces this boundary object without calculating
    metrics. The top-level CLI passes it to ``benchmark.summary`` after the
    Chrome workers have stopped.
    """

    worker_runs: list[WorkerRunResult]
    state: StopState
    run_dir: Path
    current_attempt_elapsed: float
    configuration: str


def main(argv: Sequence[str] | None = None) -> CollectionExecution:
    """Parse collection options, run configured workers, and return their result.

    Benchmark aggregation intentionally happens outside this module. That
    keeps workload selection, manifest preparation, and Chrome lifecycle
    coordination independent from reporting and throughput calculations.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-batch", type=int, default=DEFAULT_START_BATCH)
    parser.add_argument("--end-batch", type=int, default=DEFAULT_END_BATCH)
    parser.add_argument(
        "--selenium-call-size", type=int, default=DEFAULT_SELENIUM_CALL_SIZE
    )
    parser.add_argument(
        "--concurrency-per-browser",
        choices=ALLOWED_BROWSER_CONCURRENCY,
        type=int,
        default=DEFAULT_BROWSER_CONCURRENCY,
    )
    parser.add_argument("--browser-count", choices=ALLOWED_BROWSER_COUNTS, type=int, default=BROWSER_COUNT)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    args = parser.parse_args(argv)
    if args.selenium_call_size < 1:
        parser.error("Require --selenium-call-size to be at least 1")

    batches, total_ids = load_and_batch_ids(DEFAULT_INPUT_FILE, INPUT_BATCH_SIZE)
    end_batch = min(args.end_batch, len(batches))
    selected: list[BatchAssignment] = [
        (batch_number, batches[batch_number - 1])
        for batch_number in range(max(1, args.start_batch), end_batch + 1)
    ]
    if not selected:
        parser.error("No input batches selected")

    assignments = contiguous_assignments(selected, args.browser_count)
    run_paths = RunPaths(args.run_dir)
    run_paths.root.mkdir(parents=True, exist_ok=True)
    prepare_manifest(
        run_paths,
        {
            "input_file": str(DEFAULT_INPUT_FILE),
            "start_batch": selected[0][0],
            "end_batch": selected[-1][0],
            "browser_count": args.browser_count,
            "concurrency_per_browser": args.concurrency_per_browser,
            "selenium_call_size": args.selenium_call_size,
            "selected_id_count": sum(len(ids) for _, ids in selected),
            "partition_strategy": "contiguous_input_ranges",
        },
    )

    aggregate_logger = setup_logger("multi_browser_aggregate", run_paths.aggregate_log)
    aggregate_logger.info(
        "Starting/resuming %d Chrome x %d fetches; input total=%d selected_batches=%d-%d; partitions=contiguous",
        args.browser_count, args.concurrency_per_browser, total_ids,
        selected[0][0], selected[-1][0],
    )
    state = StopState()
    started = time.perf_counter()
    with ThreadPoolExecutor(
        max_workers=args.browser_count, thread_name_prefix="chrome"
    ) as executor:
        futures = [
            executor.submit(
                run_browser,
                index + 1,
                assignments[index],
                args.run_dir,
                args.selenium_call_size,
                args.concurrency_per_browser,
                state,
            )
            for index in range(args.browser_count)
        ]
        worker_runs = [future.result() for future in futures]

    return CollectionExecution(
        worker_runs=worker_runs,
        state=state,
        run_dir=args.run_dir,
        current_attempt_elapsed=time.perf_counter() - started,
        configuration=(
            f"{args.browser_count} Chrome x {args.concurrency_per_browser} browser fetches"
        ),
    )
