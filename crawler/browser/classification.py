"""Typed response models and crawler response-classification policy."""

from dataclasses import dataclass
import logging
from typing import Literal, TypeAlias, TypeGuard

import ujson as json

from utils.product import ProductRecord, extract_product_info

ProductClassification: TypeAlias = Literal["success", "not-found", "waf", "error"]


@dataclass
class BrowserFetchResponse:
    """One raw browser-side API response for a requested product ID."""

    product_id: int
    status: int | None
    content_type: str
    body: str
    error: str | None
    started_at: str
    ended_at: str
    elapsed_seconds: float
    request_number: int = 0


@dataclass
class ProductFetchResult:
    """A normalized browser response and its terminal or resumable classification."""

    response: BrowserFetchResponse
    classification: ProductClassification
    product: ProductRecord | None = None
    detail: str = ""


ClassifiedResults: TypeAlias = list[ProductFetchResult]


def _is_product_record(value: object) -> TypeGuard[ProductRecord]:
    """Return whether decoded JSON is a string-keyed product record."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def classify_product_response(response: BrowserFetchResponse) -> ProductFetchResult:
    """Apply the crawler's terminal/retryable classification policy to one response."""
    content_type = response.content_type.lower()
    if response.error:
        return ProductFetchResult(response, "error", detail=f" error={response.error}")
    if response.status in (404, 410):
        return ProductFetchResult(response, "not-found")
    if response.status == 200 and "json" in content_type:
        try:
            payload: object = json.loads(response.body)
            if not _is_product_record(payload):
                raise ValueError("JSON response is not an object")
            return ProductFetchResult(response, "success", extract_product_info(payload))
        except ValueError as error:
            return ProductFetchResult(response, "waf", detail=f" error={error}")
    return ProductFetchResult(response, "waf")


def log_product_result(
    result: ProductFetchResult,
    batch_num: int,
    event_logger: logging.Logger,
    not_found_logger: logging.Logger,
) -> None:
    """Log one product result without calculating aggregate metrics."""
    response = result.response
    log_method = (
        event_logger.info
        if result.classification in {"success", "not-found"}
        else event_logger.warning
    )
    log_method(
        "product_id=%s request_number=%s started_at=%s ended_at=%s fetch_latency=%.3fs status=%s content_type=%r result=%s%s",
        response.product_id, response.request_number, response.started_at,
        response.ended_at, response.elapsed_seconds, response.status,
        response.content_type, result.classification, result.detail,
    )
    if result.classification == "success":
        print(f"Batch {batch_num:04d} | ID {response.product_id} -> OK")
    elif result.classification == "not-found":
        not_found_logger.info("%s", response.product_id)
        print(f"Batch {batch_num:04d} | ID {response.product_id} -> {response.status} NOT FOUND")
    elif result.classification == "error":
        print(f"Batch {batch_num:04d} | ID {response.product_id} -> ERROR ({response.error})")
    else:
        body_prefix = response.body[:200].replace("\r", " ").replace("\n", " ")
        event_logger.warning(
            "WAF/challenge product_id=%s status=%s content_type=%r body_prefix=%r",
            response.product_id, response.status, response.content_type, body_prefix,
        )
        print(
            f"Batch {batch_num:04d} | ID {response.product_id} -> WAF/UNEXPECTED "
            f"(HTTP {response.status}, {response.content_type or 'no content type'})"
        )
