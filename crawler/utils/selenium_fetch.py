"""Minimal single-browser Selenium transport for the Tiki product API."""

from dataclasses import dataclass
from datetime import datetime
import logging
import math
import statistics
import time
from typing import Optional

import ujson as json
from selenium import webdriver
from selenium.common.exceptions import WebDriverException

from .utils import extract_product_info


@dataclass
class BrowserFetchResponse:
    """The complete result of one JavaScript fetch executed in Chrome."""

    status: Optional[int]
    content_type: str
    body: str
    error: Optional[str]
    elapsed_seconds: float
    started_at: str
    start_interval_seconds: Optional[float]
    request_number: int


_FETCH_SCRIPT = """
const targetUrl = arguments[0];
const done = arguments[arguments.length - 1];
fetch(targetUrl, {
  method: 'GET',
  credentials: 'include',
  headers: { 'Accept': 'application/json, text/plain, */*' },
})
  .then(async (response) => {
    const body = await response.text();
    done({status: response.status, contentType: response.headers.get('content-type') || '', body, error: null});
  })
  .catch((error) => done({status: null, contentType: '', body: '', error: String(error)}));
"""


class SeleniumTikiClient:
    """One reusable, visible Chrome browser that fetches through page JavaScript."""

    def __init__(self, timeout: float) -> None:
        options = webdriver.ChromeOptions()
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(timeout)
        self.driver.set_script_timeout(timeout)
        self.session_started = time.perf_counter()
        self._previous_request_started: Optional[float] = None
        self._fetch_latencies: list[float] = []
        self._start_intervals: list[float] = []
        self._total_id_times: list[float] = []
        self.counts = {"success": 0, "not_found": 0, "waf": 0, "error": 0}

    def open_tiki(self) -> None:
        """Establish an ordinary Tiki browsing context once at crawler startup."""
        self.driver.get("https://tiki.vn/")

    def fetch(self, product_id: int) -> BrowserFetchResponse:
        target_url = f"https://api.tiki.vn/product-detail/api/v1/products/{product_id}"
        started = time.perf_counter()
        start_interval = (
            None
            if self._previous_request_started is None
            else started - self._previous_request_started
        )
        self._previous_request_started = started
        request_number = sum(self.counts.values()) + 1
        started_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
        try:
            result = self.driver.execute_async_script(_FETCH_SCRIPT, target_url)
            elapsed = time.perf_counter() - started
        except WebDriverException as error:
            return BrowserFetchResponse(
                None, "", "", f"{type(error).__name__}: {error.msg}",
                time.perf_counter() - started, started_at, start_interval, request_number,
            )

        if not isinstance(result, dict):
            return BrowserFetchResponse(
                None, "", "", f"unexpected JavaScript result: {type(result).__name__}",
                elapsed, started_at, start_interval, request_number,
            )
        status = result.get("status")
        return BrowserFetchResponse(
            status if isinstance(status, int) else None,
            str(result.get("contentType") or ""),
            str(result.get("body") or ""),
            str(result["error"]) if result.get("error") else None,
            elapsed,
            started_at,
            start_interval,
            request_number,
        )

    def record_result(
        self,
        classification: str,
        response: BrowserFetchResponse,
        total_id_elapsed: float,
    ) -> dict[str, object]:
        """Record one terminal browser fetch for request-level and session metrics."""
        self.counts[classification.replace("-", "_")] += 1
        self._fetch_latencies.append(response.elapsed_seconds)
        if response.start_interval_seconds is not None:
            self._start_intervals.append(response.start_interval_seconds)
        self._total_id_times.append(total_id_elapsed)
        return self.summary()

    def summary(self) -> dict[str, object]:
        """Return compact, serializable metrics for the current Chrome session."""
        request_count = sum(self.counts.values())
        elapsed = time.perf_counter() - self.session_started
        return {
            "requests": request_count,
            "counts": self.counts.copy(),
            "elapsed_seconds": round(elapsed, 3),
            "ids_per_hour": round(request_count * 3600 / elapsed, 2) if elapsed else 0.0,
            "mean_fetch_latency": self._metric(self._fetch_latencies, "mean"),
            "median_fetch_latency": self._metric(self._fetch_latencies, "median"),
            "p95_fetch_latency": self._p95(self._fetch_latencies),
            "mean_start_interval": self._metric(self._start_intervals, "mean"),
        }

    @staticmethod
    def _metric(values: list[float], method: str) -> Optional[float]:
        if not values:
            return None
        value = statistics.mean(values) if method == "mean" else statistics.median(values)
        return round(value, 4)

    @staticmethod
    def _p95(values: list[float]) -> Optional[float]:
        if not values:
            return None
        return round(sorted(values)[math.ceil(len(values) * 0.95) - 1], 4)

    def close(self) -> None:
        self.driver.quit()


def fetch_product_data(
    client: SeleniumTikiClient,
    product_id: int,
    batch_num: int,
    event_logger: logging.Logger,
    not_found_logger: logging.Logger,
) -> tuple[Optional[dict], Optional[int]]:
    """Fetch and classify one product; retryable results are not checkpointed."""
    total_started = time.perf_counter()
    response = client.fetch(product_id)
    content_type = response.content_type.lower()

    if response.error:
        result, detail = "error", f" error={response.error}"
    elif response.status in (404, 410):
        result, detail = "not-found", ""
    elif response.status == 200 and "json" in content_type:
        try:
            payload = json.loads(response.body)
            if not isinstance(payload, dict):
                raise ValueError("JSON response is not an object")
            product = extract_product_info(payload)
        except ValueError as error:
            result, detail = "waf", f" error={error}"
        else:
            result, detail = "success", ""
    else:
        result, detail = "waf", ""

    total_id_elapsed = time.perf_counter() - total_started
    metrics = client.record_result(result, response, total_id_elapsed)
    log_method = event_logger.info if result in {"success", "not-found"} else event_logger.warning
    log_method(
        "product_id=%s request_number=%s started_at=%s start_interval=%s fetch_latency=%.3fs total_id_elapsed=%.3fs status=%s content_type=%r result=%s counts=%s%s",
        product_id, response.request_number, response.started_at,
        None if response.start_interval_seconds is None else round(response.start_interval_seconds, 3),
        response.elapsed_seconds, total_id_elapsed, response.status,
        response.content_type, result, metrics["counts"], detail,
    )

    if result == "success":
        print(f"Batch {batch_num:04d} | ID {product_id} -> OK ({product.get('name', '')[:25]}...)")
        return product, None
    if result == "not-found":
        not_found_logger.info("%s", product_id)
        print(f"Batch {batch_num:04d} | ID {product_id} -> {response.status} NOT FOUND")
        return None, response.status
    if result == "error":
        print(f"Batch {batch_num:04d} | ID {product_id} -> ERROR ({response.error})")
    else:
        body_prefix = response.body[:200].replace("\r", " ").replace("\n", " ")
        event_logger.warning(
            "WAF/challenge product_id=%s status=%s content_type=%r body_prefix=%r",
            product_id, response.status, response.content_type, body_prefix,
        )
        print(f"Batch {batch_num:04d} | ID {product_id} -> WAF/UNEXPECTED (HTTP {response.status}, {response.content_type or 'no content type'})")
    return None, None
