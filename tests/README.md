# Tests

## Responsibility

This folder contains focused regression tests for collector behavior that is
easy to break during maintenance.

## Where It Fits

The tests check small, deterministic units. They do not start Chrome or call
the target API.

## Inputs

- The collector source modules and configured Python environment.

## Outputs

- Pass/fail results from Python's built-in `unittest` runner.

## Important Files

- `test_description_cleaning.py` — checks product-description whitespace normalization.
- `test_selenium_metrics.py` — checks that `record_result()` does not rebuild expensive summary statistics for every product.
- `test_retries.py` — checks WAF cooldowns and short retry behavior without Selenium.
- `test_rerun.py` — checks deterministic structured rerun selection and summaries.

## Design Notes

- Run focused checks with `uv run python -m unittest discover -s tests -v`.
- This folder intentionally has no live API or Chrome integration test. Benchmark runs cover that integration separately.
