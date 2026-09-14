import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crawler"))

from browser.client import (
    BrowserFetchResponse,
    ProductFetchResult,
    SeleniumTikiClient,
)


class SeleniumMetricTests(unittest.TestCase):
    def test_record_result_does_not_build_a_summary(self) -> None:
        """The per-product hot path must not recalculate aggregate statistics."""
        client = object.__new__(SeleniumTikiClient)
        client.counts = {"success": 0, "not_found": 0, "waf": 0, "error": 0}
        client._fetch_latencies = []

        def unexpected_summary() -> None:
            raise AssertionError("record_result must not call summary")

        client.summary = unexpected_summary
        response = BrowserFetchResponse(
            product_id=1,
            status=200,
            content_type="application/json",
            body="{}",
            error=None,
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:00:00Z",
            elapsed_seconds=0.125,
        )

        self.assertIsNone(client.record_result(ProductFetchResult(response, "success", {})))
        self.assertEqual(client.counts["success"], 1)
        self.assertEqual(client._fetch_latencies, [0.125])


if __name__ == "__main__":
    unittest.main()
