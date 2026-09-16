# Browser

## Responsibility

This package manages Selenium Chrome transport, bounded in-page JavaScript
fetching, raw response normalization, and response classification.

## Where It Fits

`execution.worker` owns one `SeleniumTikiClient` for each persistent Chrome
session. It passes this package each Selenium-call-sized ID chunk.

## Inputs

- Ordered product IDs and bounded per-browser concurrency.
- Selenium timeout from stable application configuration.

## Outputs

- `BrowserFetchResponse` with status, body, timestamps, error, and latency.
- `ProductFetchResult` classified as success, not-found, WAF, or browser error.

## Important Files

- `client.py` - WebDriver lifecycle, script execution, raw result normalization, and session counters.
- `scripts.py` - source for the bounded JavaScript worker pool.
- `classification.py` - result types, classification policy, and per-product logging.

## Design Notes

- JavaScript creates at most `min(concurrency, ID count)` workers. It never creates one unbounded promise per ID.
- Indexed result slots keep input order, and each result also includes its product ID.
- A challenge stops new in-page requests. IDs that did not start get an explicit transient result, so execution can retry them instead of treating sparse JavaScript-array slots as terminal browser failures.
- HTTP 200 with valid JSON and HTTP 404/410 are terminal. Challenges and browser/network errors remain resumable.
- Aggregate statistics are calculated at worker and run boundaries, not for every product.
