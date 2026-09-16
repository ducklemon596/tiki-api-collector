"""Durable per-browser and aggregate benchmark summary construction."""

from dataclasses import dataclass
from typing import TypedDict

from browser.client import BrowserSessionSummary
from benchmark.metrics import latency_metric
from execution.worker import StopState, WorkerRunResult
from persistence.checkpoint import BatchCheckpoint
from persistence.progress import load_terminal_metrics
from utils.product import ProductRecord


class AggregateSummary(TypedDict):
    """JSON-compatible final summary written at the end of a collection attempt."""

    configuration: str
    total_elapsed_seconds: float
    current_attempt_elapsed_seconds: float
    metric_scope: str
    effective_ids_per_hour: float
    total_ids: int
    success_count: int
    not_found_count: int
    waf_count: int
    browser_error_count: int
    mean_fetch_latency: float | None
    median_fetch_latency: float | None
    p95_fetch_latency: float | None
    stop_reason: str | None
    stop_browser: int | None
    waf_cutoff: str | None
    per_browser: list[dict[str, object]]


@dataclass
class BrowserRun:
    """Durable metrics and latency samples for one completed browser worker."""

    browser: int
    summary: BrowserSessionSummary
    latencies: list[float]


def build_browser_summary(worker_run: WorkerRunResult) -> BrowserRun:
    """Rebuild one browser's metrics from checkpointed terminal state."""
    successes: list[ProductRecord] = []
    completed_ids: set[int] = set()
    for batch_number, _ in worker_run.assignments:
        products, completed = BatchCheckpoint(
            worker_run.paths.checkpoints, batch_number
        ).load_completed()
        successes.extend(products)
        completed_ids.update(completed)
    latencies = load_terminal_metrics(worker_run.paths.terminal_metrics, completed_ids)
    session = worker_run.session_summary
    summary: BrowserSessionSummary = {
        "total_ids": sum(len(ids) for _, ids in worker_run.assignments),
        "total_requests": len(completed_ids),
        "success_count": len(successes),
        "not_found_count": len(completed_ids) - len(successes),
        "waf_count": session["waf_count"] if session is not None else 0,
        "browser_error_count": (
            session["browser_error_count"] if session is not None else 1
        ),
        "summary_call_count": session["summary_call_count"] if session is not None else 0,
        "mean_fetch_latency": latency_metric(latencies, "mean"),
        "median_fetch_latency": latency_metric(latencies, "median"),
        "p95_fetch_latency": latency_metric(latencies, "p95"),
        "total_elapsed_seconds": worker_run.active_elapsed,
        "effective_ids_per_hour": (
            round(len(completed_ids) * 3600 / worker_run.active_elapsed, 2)
            if worker_run.active_elapsed
            else 0.0
        ),
    }
    return BrowserRun(worker_run.browser, summary, latencies)


def build_aggregate_summary(
    browser_runs: list[BrowserRun],
    configuration: str,
    attempt_elapsed: float,
    state: StopState,
) -> AggregateSummary:
    """Combine durable browser summaries into the run's final JSON payload."""
    elapsed = max(
        (run.summary["total_elapsed_seconds"] for run in browser_runs), default=0.0
    )
    latencies = [latency for run in browser_runs for latency in run.latencies]
    total_requests = sum(run.summary["total_requests"] for run in browser_runs)
    return {
        "configuration": configuration,
        "total_elapsed_seconds": round(elapsed, 3),
        "current_attempt_elapsed_seconds": round(attempt_elapsed, 3),
        "metric_scope": (
            "Terminal classifications, latencies, and active elapsed time include prior "
            "resumed work. Idle time between process attempts is excluded."
        ),
        "effective_ids_per_hour": round(total_requests * 3600 / elapsed, 2) if elapsed else 0.0,
        "total_ids": sum(run.summary["total_ids"] for run in browser_runs),
        "success_count": sum(run.summary["success_count"] for run in browser_runs),
        "not_found_count": sum(run.summary["not_found_count"] for run in browser_runs),
        "waf_count": sum(run.summary["waf_count"] for run in browser_runs),
        "browser_error_count": sum(
            run.summary["browser_error_count"] for run in browser_runs
        ),
        "mean_fetch_latency": latency_metric(latencies, "mean"),
        "median_fetch_latency": latency_metric(latencies, "median"),
        "p95_fetch_latency": latency_metric(latencies, "p95"),
        "stop_reason": state.reason,
        "stop_browser": state.source_browser,
        "waf_cutoff": state.cutoff,
        "per_browser": [
            {"browser": run.browser, **run.summary} for run in browser_runs
        ],
    }
