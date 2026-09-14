"""Friendly command-line entry point for the supported two-browser crawler."""

import argparse
import sys
from typing import Sequence

import ujson as json

from benchmark.monitor import main as monitor_main
from benchmark.summary import build_aggregate_summary, build_browser_summary
from execution.orchestration import main as crawl_main
from logger import setup_logger
from persistence.checkpoint import write_json_atomically
from persistence.paths import EVENTS_LOG_FILE_NAME, RunPaths


def run_crawl_command(argv: Sequence[str]) -> None:
    """Run crawl execution, then create durable benchmark summaries.

    Args:
        argv: Crawl-specific command-line arguments after ``crawl``.

    Side Effects:
        Starts the two Chrome workers through ``execution`` and writes the
        unchanged per-browser event summaries plus aggregate
        ``benchmark_summary.json``.
    """
    execution = crawl_main(argv)
    browser_runs = [
        build_browser_summary(worker_run) for worker_run in execution.worker_runs
    ]
    for worker_run, browser_run in zip(execution.worker_runs, browser_runs):
        setup_logger(
            f"two_browser_events_{browser_run.browser}",
            worker_run.paths.logs / EVENTS_LOG_FILE_NAME,
        ).info(
            "Chrome %02d benchmark summary: %s",
            browser_run.browser,
            browser_run.summary,
        )
    aggregate = build_aggregate_summary(
        browser_runs,
        execution.configuration,
        execution.current_attempt_elapsed,
        execution.state,
    )
    run_paths = RunPaths(execution.run_dir)
    write_json_atomically(run_paths.summary, aggregate)
    setup_logger("multi_browser_aggregate", run_paths.aggregate_log).info(
        "Aggregate benchmark summary: %s", aggregate
    )
    print(json.dumps(aggregate, indent=2))


def main(argv: Sequence[str] | None = None) -> None:
    """Dispatch to the crawler or its read-only throughput monitor.

    Input: ``crawl`` or ``monitor`` followed by that command's options. Output: the
    selected command's normal console output and durable files in its run directory.
    """
    parser = argparse.ArgumentParser(description="Two-browser resumable Tiki crawler")
    parser.add_argument("command", choices=("crawl", "monitor"))
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        parser.print_help()
        return
    command = parser.parse_args(arguments[:1]).command
    if command == "crawl":
        run_crawl_command(arguments[1:])
    else:
        monitor_main(arguments[1:])


if __name__ == "__main__":
    main()
