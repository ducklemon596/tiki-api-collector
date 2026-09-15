"""Focused retry-policy tests without starting Selenium."""

import logging
import unittest
from unittest.mock import ANY, patch

from browser.classification import BrowserFetchResponse
from browser.client import EMPTY_SCRIPT_RESULT_ERROR, SKIPPED_AFTER_CHALLENGE_ERROR
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
        with patch("execution.worker.wait_for_retry_delay", return_value=False) as wait:
            results = fetch_with_retries(
                client, [1, 2], 4, logging.getLogger("retry-test"), StopState()
            )

        self.assertEqual(client.calls, [[1, 2], [1]])
        self.assertEqual([result.classification for result in results], ["success", "not-found"])
        wait.assert_called_once_with(ANY, 1.0)

    def test_waf_uses_exponential_backoff(self) -> None:
        """A persistent WAF receives the configured 5/10/20-minute cooldowns."""
        waf = response(1, status=503, content_type="text/html", body="challenge")
        client = FakeClient([[waf], [waf], [waf], [waf]])
        with patch("execution.worker.wait_for_retry_delay", return_value=False) as wait:
            results = fetch_with_retries(
                client, [1], 4, logging.getLogger("retry-test"), StopState()
            )

        self.assertEqual(client.calls, [[1], [1], [1], [1]])
        self.assertEqual(results[0].classification, "waf")
        self.assertEqual(
            [call.args[1] for call in wait.call_args_list], [300.0, 600.0, 1200.0]
        )

    def test_missing_script_result_retries_the_affected_call(self) -> None:
        """A Selenium null result is transient and does not become terminal."""
        client = FakeClient(
            [
                [response(1, status=None, error=f"{EMPTY_SCRIPT_RESULT_ERROR}: NoneType")],
                [response(1, status=200, content_type="application/json", body="{}")],
            ]
        )
        with patch("execution.worker.wait_for_retry_delay", return_value=False) as wait:
            results = fetch_with_retries(
                client, [1], 4, logging.getLogger("retry-test"), StopState()
            )

        self.assertEqual(client.calls, [[1], [1]])
        self.assertEqual(results[0].classification, "success")
        wait.assert_called_once_with(ANY, 1.0)

    def test_ids_skipped_after_a_challenge_retry_without_becoming_terminal(self) -> None:
        """Sparse slots stopped by a challenge are safe to fetch after backoff."""
        client = FakeClient(
            [
                [
                    response(
                        1,
                        status=None,
                        error=SKIPPED_AFTER_CHALLENGE_ERROR,
                    )
                ],
                [response(1, status=200, content_type="application/json", body="{}")],
            ]
        )
        with patch("execution.worker.wait_for_retry_delay", return_value=False):
            results = fetch_with_retries(
                client, [1], 4, logging.getLogger("retry-test"), StopState()
            )

        self.assertEqual(client.calls, [[1], [1]])
        self.assertEqual(results[0].classification, "success")

    def test_failed_to_fetch_retries_without_retrying_not_found(self) -> None:
        """A browser-network rejection is transient, unlike a 404 response."""
        client = FakeClient(
            [
                [
                    response(1, status=None, error="TypeError: Failed to fetch"),
                    response(2, status=404),
                ],
                [response(1, status=200, content_type="application/json", body="{}")],
            ]
        )
        with patch("execution.worker.wait_for_retry_delay", return_value=False):
            results = fetch_with_retries(
                client, [1, 2], 4, logging.getLogger("retry-test"), StopState()
            )

        self.assertEqual(client.calls, [[1, 2], [1]])
        self.assertEqual([result.classification for result in results], ["success", "not-found"])
