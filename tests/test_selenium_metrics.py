import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

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

    def test_explicit_existing_chromedriver_path_uses_service(self) -> None:
        """An existing configured driver path is passed to Selenium as a service."""
        driver = Mock()
        driver.set_page_load_timeout = Mock()
        driver.set_script_timeout = Mock()
        configured_path = Path("C:/tools/chromedriver.exe")
        with (
            patch("browser.client.CHROMEDRIVER_PATH", configured_path),
            patch.object(Path, "is_file", return_value=True),
            patch("browser.client.Service") as service,
            patch("browser.client.webdriver.Chrome", return_value=driver) as chrome,
        ):
            SeleniumTikiClient(timeout=10)

        service.assert_called_once_with(executable_path=str(configured_path))
        chrome.assert_called_once()
        self.assertIs(chrome.call_args.kwargs["service"], service.return_value)

    def test_missing_or_unconfigured_driver_uses_selenium_default(self) -> None:
        """No usable configured path leaves driver resolution to Selenium."""
        for configured_path in (None, Path("C:/missing/chromedriver.exe")):
            with self.subTest(configured_path=configured_path):
                driver = Mock()
                driver.set_page_load_timeout = Mock()
                driver.set_script_timeout = Mock()
                with (
                    patch("browser.client.CHROMEDRIVER_PATH", configured_path),
                    patch.object(Path, "is_file", return_value=False),
                    patch("browser.client.Service") as service,
                    patch(
                        "browser.client.webdriver.Chrome", return_value=driver
                    ) as chrome,
                ):
                    SeleniumTikiClient(timeout=10)

                service.assert_not_called()
                chrome.assert_called_once()
                self.assertNotIn("service", chrome.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
