# Tests

## Responsibility

Contains focused regression tests for behavior that is easy to break during crawler maintenance.

## Where It Fits

Tests validate small, deterministic units without starting a Chrome browser or contacting the target API.

## Inputs

- The crawler source modules and the configured Python environment.

## Outputs

- Pass/fail results from Python's built-in `unittest` runner.

## Important Files

- `test_description_cleaning.py` — verifies product-description whitespace normalization.
- `test_selenium_metrics.py` — verifies `record_result()` does not rebuild expensive summary statistics for every product.

## Design Notes

- Run focused checks with `uv run python -m unittest discover -s tests -v`.
- There is intentionally no live API or Chrome integration test in this folder; benchmark runs exercise that integration separately.
