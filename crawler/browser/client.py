"""Persistent Selenium transport and raw browser-result normalization."""

from datetime import datetime
import math
import statistics
import time
from typing import Literal, TypeAlias, TypeGuard, TypedDict

from selenium import webdriver
from selenium.common.exceptions import WebDriverException

from browser.classification import BrowserFetchResponse, ProductFetchResult
from browser.scripts import BOUNDED_FETCH_SCRIPT
from utils.product import ProductRecord

RawBrowserResults: TypeAlias = list[object]


class BrowserSessionSummary(TypedDict):
    """Metrics collected in memory by one persistent Chrome session."""

    total_ids: int
    total_requests: int
    success_count: int
    not_found_count: int
    waf_count: int
    browser_error_count: int
    mean_fetch_latency: float | None
    median_fetch_latency: float | None
    p95_fetch_latency: float | None
    total_elapsed_seconds: float
    effective_ids_per_hour: float
    summary_call_count: int


def _fallback_results(
    product_ids: list[int], timestamp: str, error: str
) -> RawBrowserResults:
    """Create retryable browser-error slots for every requested ID."""
    results: RawBrowserResults = []
    for product_id in product_ids:
        results.append(
            {
            "productId": product_id,
            "status": None,
            "contentType": "",
            "body": "",
            "error": error,
            "startedAt": timestamp,
            "endedAt": timestamp,
            "elapsedSeconds": 0,
            }
        )
    return results


def _normalise_script_results(
    raw_results: object, product_ids: list[int], timestamp: str
) -> RawBrowserResults:
    """Guarantee one raw result slot for each requested product ID."""
    if not isinstance(raw_results, list):
        message = (
            str(raw_results.get("error"))
            if isinstance(raw_results, dict) and raw_results.get("error")
            else f"unexpected JavaScript result: {type(raw_results).__name__}"
        )
        return _fallback_results(product_ids, timestamp, message)
    return [
        *raw_results[: len(product_ids)],
        *([None] * max(0, len(product_ids) - len(raw_results))),
    ]


def _is_product_record(value: object) -> TypeGuard[ProductRecord]:
    """Return whether an untyped browser result is a string-keyed record."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _response_from_raw(
    product_id: int, raw: object, timestamp: str, request_number: int
) -> BrowserFetchResponse:
    """Convert one JavaScript result slot into a typed browser response."""
    raw_result = raw if _is_product_record(raw) else {
        "error": f"unexpected result entry: {type(raw).__name__}"
    }
    status = raw_result.get("status")
    elapsed_value = raw_result.get("elapsedSeconds")
    elapsed_seconds = (
        float(elapsed_value)
        if isinstance(elapsed_value, (int, float, str))
        else 0.0
    )
    return BrowserFetchResponse(
        product_id=product_id,
        status=status if isinstance(status, int) else None,
        content_type=str(raw_result.get("contentType") or ""),
        body=str(raw_result.get("body") or ""),
        error=str(raw_result["error"]) if raw_result.get("error") else None,
        started_at=str(raw_result.get("startedAt") or timestamp),
        ended_at=str(raw_result.get("endedAt") or timestamp),
        elapsed_seconds=elapsed_seconds,
        request_number=request_number,
    )


class SeleniumTikiClient:
    """One reusable Chrome with a bounded in-page product-fetch worker pool."""

    def __init__(self, timeout: float) -> None:
        options = webdriver.ChromeOptions()
        self.driver = webdriver.Chrome(options=options)
        self.request_timeout = timeout
        self.driver.set_page_load_timeout(timeout)
        self.driver.set_script_timeout(timeout)
        self.session_started = time.perf_counter()
        self._fetch_latencies: list[float] = []
        self.counts = {"success": 0, "not_found": 0, "waf": 0, "error": 0}
        self._product_ids: set[int] = set()
        self._request_number = 0
        self._summary_call_count = 0

    def open_tiki(self) -> None:
        """Establish the browser context once at crawler startup."""
        self.driver.get("https://tiki.vn/")

    def fetch_many(
        self, product_ids: list[int], concurrency: int
    ) -> list[BrowserFetchResponse]:
        """Fetch ordered IDs with no more than ``concurrency`` in-page requests."""
        if not product_ids:
            return []
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        fallback_timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        self._product_ids.update(product_ids)
        worker_count = min(concurrency, len(product_ids))
        self.driver.set_script_timeout(
            self.request_timeout * math.ceil(len(product_ids) / worker_count) + 5
        )
        try:
            raw_results: object = self.driver.execute_async_script(
                BOUNDED_FETCH_SCRIPT, product_ids, concurrency, self.request_timeout * 1000
            )
        except WebDriverException as error:
            raw_results = _fallback_results(
                product_ids, fallback_timestamp, f"{type(error).__name__}: {error.msg}"
            )
        normalized = _normalise_script_results(raw_results, product_ids, fallback_timestamp)
        responses: list[BrowserFetchResponse] = []
        for product_id, raw in zip(product_ids, normalized):
            self._request_number += 1
            responses.append(
                _response_from_raw(product_id, raw, fallback_timestamp, self._request_number)
            )
        return responses

    def record_result(self, result: ProductFetchResult) -> None:
        """Record one classified response in O(1); summary work is deferred."""
        self.counts[result.classification.replace("-", "_")] += 1
        self._fetch_latencies.append(result.response.elapsed_seconds)

    def summary(self) -> BrowserSessionSummary:
        """Return in-memory session metrics at a worker boundary."""
        self._summary_call_count += 1
        total_requests = sum(self.counts.values())
        elapsed = time.perf_counter() - self.session_started
        return {
            "total_ids": len(self._product_ids),
            "total_requests": total_requests,
            "success_count": self.counts["success"],
            "not_found_count": self.counts["not_found"],
            "waf_count": self.counts["waf"],
            "browser_error_count": self.counts["error"],
            "mean_fetch_latency": self._metric(self._fetch_latencies, "mean"),
            "median_fetch_latency": self._metric(self._fetch_latencies, "median"),
            "p95_fetch_latency": self._p95(self._fetch_latencies),
            "total_elapsed_seconds": round(elapsed, 3),
            "effective_ids_per_hour": round(total_requests * 3600 / elapsed, 2) if elapsed else 0.0,
            "summary_call_count": self._summary_call_count,
        }

    @staticmethod
    def _metric(values: list[float], method: Literal["mean", "median"]) -> float | None:
        """Calculate a compact in-memory latency statistic."""
        if not values:
            return None
        value = statistics.mean(values) if method == "mean" else statistics.median(values)
        return round(value, 4)

    @staticmethod
    def _p95(values: list[float]) -> float | None:
        """Calculate the nearest-rank P95 for in-memory fetch latencies."""
        if not values:
            return None
        return round(sorted(values)[math.ceil(len(values) * 0.95) - 1], 4)

    def close(self) -> None:
        """Close this worker's WebDriver session."""
        self.driver.quit()
