"""One-browser worker lifecycle, shared stop state, and terminal persistence."""

from dataclasses import dataclass, field
import logging
from pathlib import Path
import threading
import time

from browser.classification import (
    ClassifiedResults,
    ProductFetchResult,
    classify_product_response,
    log_product_result,
)
from browser.client import BrowserSessionSummary, SeleniumTikiClient
from config import (
    CHECKPOINT_SYNC_INTERVAL,
    MAX_RETRY_ATTEMPTS,
    MAX_CONSECUTIVE_BROWSER_ERRORS,
    REQUEST_TIMEOUT_SECONDS,
    RETRY_BACKOFF_SECONDS,
)
from execution.partitioning import BrowserAssignment, ProductId, chunks
from logger import setup_logger
from persistence.checkpoint import BatchCheckpoint
from persistence.paths import (
    EVENTS_LOG_FILE_NAME,
    NOT_FOUND_LOG_FILE_NAME,
    RunPaths,
    WorkerRunPaths,
)
from persistence.progress import (
    append_error_journal,
    append_terminal_metrics,
    load_active_elapsed,
    save_active_elapsed,
)
from utils.product import ProductRecord


@dataclass
class StopState:
    """First shared stop decision and earliest WAF cutoff across browser workers."""

    event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    reason: str | None = None
    source_browser: int | None = None
    cutoff: str | None = None

    def stop(self, reason: str, browser: int, cutoff: str | None = None) -> None:
        """Record the first reason and preserve the earliest supplied cutoff."""
        with self.lock:
            if self.reason is None:
                self.reason, self.source_browser, self.cutoff = reason, browser, cutoff
            elif cutoff and (self.cutoff is None or cutoff < self.cutoff):
                self.cutoff = cutoff
            self.event.set()


@dataclass
class ResumableBatch:
    """A shard, its checkpoint, and only the IDs still missing terminal state."""

    number: int
    checkpoint: BatchCheckpoint
    pending_ids: list[ProductId]
    success_count: int
    not_found_count: int
    complete: bool = True


@dataclass(frozen=True)
class WorkerRunResult:
    """Worker-boundary data consumed later by benchmark summary construction."""

    browser: int
    assignments: BrowserAssignment
    paths: WorkerRunPaths
    active_elapsed: float
    session_summary: BrowserSessionSummary | None


def terminal_before_cutoff(result: ProductFetchResult, cutoff: str | None) -> bool:
    """Return whether a terminal result is safe to persist under the WAF cutoff."""
    return result.classification in {"success", "not-found"} and (
        cutoff is None or result.response.ended_at <= cutoff
    )


def prepare_batch(
    paths: WorkerRunPaths, batch_number: int, assigned_ids: list[ProductId]
) -> ResumableBatch | None:
    """Load a checkpoint and return its uncompleted IDs, or skip a final batch."""
    checkpoint = BatchCheckpoint(
        paths.checkpoints, batch_number, sync_interval=CHECKPOINT_SYNC_INTERVAL
    )
    if checkpoint.finalized:
        return None
    products, completed_ids = checkpoint.load_completed()
    return ResumableBatch(
        batch_number,
        checkpoint,
        [product_id for product_id in assigned_ids if product_id not in completed_ids],
        len(products),
        len(completed_ids) - len(products),
    )


def persist_terminal_results(
    batch: ResumableBatch,
    metric_path: Path,
    results: ClassifiedResults,
    cutoff: str | None,
) -> None:
    """Journal then checkpoint only terminal responses safe under shared stop state."""
    safe_results: ClassifiedResults = [
        result for result in results if terminal_before_cutoff(result, cutoff)
    ]
    append_terminal_metrics(metric_path, safe_results)
    for result in safe_results:
        if result.classification == "success":
            product: ProductRecord | None = result.product
            if product is None:
                raise ValueError("Success result must contain product data")
            batch.success_count += 1
            batch.checkpoint.record_success(product)
        elif result.classification == "not-found":
            status = result.response.status
            if status is None:
                raise ValueError("Not-found result must contain an HTTP status")
            batch.not_found_count += 1
            batch.checkpoint.record_not_found(result.response.product_id, status)
        else:
            raise ValueError("Only terminal results may be persisted")


def should_retry(result: ProductFetchResult) -> bool:
    """Return whether a result is a WAF or explicit timeout eligible for retry."""
    return result.classification == "waf" or (
        result.classification == "error"
        and "timeout" in (result.response.error or "").lower()
    )


def fetch_with_retries(
    client: SeleniumTikiClient,
    product_ids: list[ProductId],
    concurrency: int,
    event_logger: logging.Logger,
    state: StopState,
) -> ClassifiedResults:
    """Fetch IDs, retrying only WAF/timeout results with bounded backoff."""
    results: ClassifiedResults = [
        classify_product_response(response)
        for response in client.fetch_many(product_ids, concurrency)
    ]
    for attempt in range(MAX_RETRY_ATTEMPTS):
        retry_ids = [
            result.response.product_id for result in results if should_retry(result)
        ]
        if not retry_ids or state.event.is_set():
            break
        delay = RETRY_BACKOFF_SECONDS * (2**attempt)
        event_logger.warning(
            "Retrying %d WAF/timeout IDs after %.1fs (attempt %d/%d)",
            len(retry_ids), delay, attempt + 1, MAX_RETRY_ATTEMPTS,
        )
        time.sleep(delay)
        if state.event.is_set():
            break
        retried = {
            response.product_id: classify_product_response(response)
            for response in client.fetch_many(retry_ids, concurrency)
        }
        results = [
            retried.get(result.response.product_id, result) if should_retry(result) else result
            for result in results
        ]
    return results


def process_fetch_chunk(
    client: SeleniumTikiClient,
    product_ids: list[ProductId],
    batch_number: int,
    browser: int,
    concurrency: int,
    event_logger: logging.Logger,
    not_found_logger: logging.Logger,
    state: StopState,
    browser_errors: int,
) -> tuple[ClassifiedResults, int]:
    """Fetch, classify, log, and make shared stop decisions for one Selenium call."""
    results = fetch_with_retries(client, product_ids, concurrency, event_logger, state)
    challenges = [result for result in results if result.classification == "waf"]
    if challenges:
        first_challenge = min(challenges, key=lambda result: result.response.ended_at)
        state.stop("waf", browser, first_challenge.response.ended_at)
    for result in results:
        client.record_result(result)
        log_product_result(result, batch_number, event_logger, not_found_logger)
        browser_errors += int(result.classification == "error")
    if browser_errors >= MAX_CONSECUTIVE_BROWSER_ERRORS:
        state.stop("repeated_browser_errors", browser)
    return results, browser_errors


def finalize_batch(
    batch: ResumableBatch, worker_id: str, event_logger: logging.Logger
) -> None:
    """Write informational state and finalize only an entirely terminal batch."""
    batch.checkpoint.write_state(worker_id, batch.success_count, batch.not_found_count)
    if batch.complete:
        batch.checkpoint.finalize()
    else:
        event_logger.warning("Shard batch %04d remains resumable", batch.number)


def run_browser(
    browser: int,
    assignments: BrowserAssignment,
    run_dir: Path,
    call_size: int,
    concurrency_per_browser: int,
    state: StopState,
) -> WorkerRunResult:
    """Run one persistent Chrome and return durable-state inputs for later summary work."""
    paths = RunPaths(run_dir).worker(browser)
    paths.logs.mkdir(parents=True, exist_ok=True)
    event_logger = setup_logger(
        f"two_browser_events_{browser}", paths.logs / EVENTS_LOG_FILE_NAME
    )
    not_found_logger = setup_logger(
        f"two_browser_not_found_{browser}", paths.logs / NOT_FOUND_LOG_FILE_NAME
    )
    previous_elapsed = load_active_elapsed(paths.progress)
    attempt_started = time.perf_counter()
    browser_errors = 0

    def save_elapsed() -> float:
        return save_active_elapsed(
            paths.progress, previous_elapsed + time.perf_counter() - attempt_started
        )

    client: SeleniumTikiClient | None = None
    try:
        client = SeleniumTikiClient(timeout=REQUEST_TIMEOUT_SECONDS)
        event_logger.info(
            "Opening Chrome %02d with browser concurrency %d", browser, concurrency_per_browser
        )
        client.open_tiki()
        for batch_number, assigned_ids in assignments:
            if state.event.is_set():
                break
            batch = prepare_batch(paths, batch_number, assigned_ids)
            if batch is None:
                event_logger.info("Shard batch %04d already finalized; skipping", batch_number)
                continue
            batch.checkpoint.open()
            try:
                for product_ids in chunks(batch.pending_ids, call_size):
                    if state.event.is_set():
                        batch.complete = False
                        break
                    results, browser_errors = process_fetch_chunk(
                        client, product_ids, batch.number, browser, concurrency_per_browser,
                        event_logger, not_found_logger, state, browser_errors,
                    )
                    append_error_journal(paths.error_journal, results)
                    with state.lock:
                        cutoff = state.cutoff
                    persist_terminal_results(batch, paths.terminal_metrics, results, cutoff)
                    save_elapsed()
                    if state.event.is_set():
                        batch.complete = False
                        break
                finalize_batch(batch, f"browser-{browser:02d}", event_logger)
            finally:
                batch.checkpoint.close()
    except Exception as error:
        state.stop("browser_exception", browser)
        event_logger.exception("Chrome %02d failed: %s", browser, error)
    finally:
        active_elapsed = save_elapsed()
        session_summary = client.summary() if client is not None else None
        if client is not None:
            client.close()
    return WorkerRunResult(browser, assignments, paths, active_elapsed, session_summary)
