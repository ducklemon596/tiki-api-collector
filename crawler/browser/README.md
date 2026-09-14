# Browser

## Responsibility

Owns Selenium Chrome transport, bounded in-page JavaScript fetching, raw response normalization, and response classification.

## Where It Fits

`execution.worker` owns one `SeleniumTikiClient` per persistent Chrome session and passes each Selenium-call-sized ID chunk to this package.

## Inputs

- Ordered product IDs and bounded per-browser concurrency.
- Selenium timeout from stable application configuration.

## Outputs

- `BrowserFetchResponse` with status, body, timestamps, error, and latency.
- `ProductFetchResult` classified as success, not-found, WAF, or browser error.

## Important Files

- `client.py` - WebDriver lifecycle, script execution, raw result normalization, and session counters.
- `scripts.py` - bounded JavaScript worker-pool source.
- `classification.py` - result types, classification policy, and per-product logging.

## Design Notes

- JavaScript creates at most `min(concurrency, ID count)` workers; it never creates one promise per ID without a bound.
- Indexed result slots preserve input order, while every result also carries a product ID.
- HTTP 200 plus valid JSON and 404/410 are terminal. Challenges and browser/network errors remain resumable.
- Aggregate statistics are deferred to worker/run boundaries rather than calculated for every product.
