"""Focused retry-policy tests without starting Selenium."""

import logging
import unittest
from unittest.mock import patch

from browser.classification import BrowserFetchResponse
from execution.worker import StopState, fetch_with_retries


def response(product_id: int, *, status: int | None, content_type: str = "", body: str = "", error: str | None = None) -> BrowserFetchResponse:
    """Build a minimal browser response for retry-policy assertions."""
    return BrowserFetchResponse(
        product_id=product_id,
        status=status,
        content_type=content_type,
        body=body,
        error=error,
        started_at="2026-09-15T00:00:00Z",
        ended_at="2026-09-15T00:00:00Z",
        elapsed_seconds=0.1,
    )


class FakeClient:
    """Return prepared browser responses and retain retry call arguments."""

    def __init__(self, responses: list[list[BrowserFetchResponse]]) -> None:
        self.responses = responses
        self.calls: list[list[int]] = []

    def fetch_many(self, product_ids: list[int], concurrency: int) -> list[BrowserFetchResponse]:
        self.calls.append(product_ids)
        return self.responses.pop(0)


class RetryTests(unittest.TestCase):
    """WAF/timeout retry behavior must exclude terminal not-found responses."""

    def test_timeout_retries_but_not_found_does_not(self) -> None:
        """A resolved timeout replaces only its result in the original order."""
        client = FakeClient(
            [
                [
                    response(1, status=None, error="timeout"),
                    response(2, status=404),
                ],
                [response(1, status=200, content_type="application/json", body="{}")],
            ]
        )
        with patch("execution.worker.time.sleep") as sleep:
            results = fetch_with_retries(
                client, [1, 2], 4, logging.getLogger("retry-test"), StopState()
            )

        self.assertEqual(client.calls, [[1, 2], [1]])
        self.assertEqual([result.classification for result in results], ["success", "not-found"])
        sleep.assert_called_once_with(1.0)

    def test_waf_uses_exponential_backoff(self) -> None:
        """A persistent WAF receives exactly the configured 1s then 2s retries."""
        waf = response(1, status=503, content_type="text/html", body="challenge")
        client = FakeClient([[waf], [waf], [waf]])
        with patch("execution.worker.time.sleep") as sleep:
            results = fetch_with_retries(
                client, [1], 4, logging.getLogger("retry-test"), StopState()
            )

        self.assertEqual(client.calls, [[1], [1], [1]])
        self.assertEqual(results[0].classification, "waf")
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1.0, 2.0])
