# Selenium Collector Benchmark Results

This file keeps the benchmark history and the final stable 20,000-ID
comparison in one place. All tests use persistent Chrome sessions,
browser-side JavaScript `fetch()`, zero artificial delay, and bounded browser
concurrency. `C<N>` means `<N>` concurrent in-page fetch workers per Chrome.

## Benchmark History and Stable Comparison

| Stage | Configuration | Sample | Aggregate fetches | IDs/hour | Mean / median / P95 latency | WAF / errors | Notes |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| Starting point | 1 Chrome x C1 | 500 | 1 | 28,061 | 113.8 / 82.0 / 285.9 ms | 0 / 0 | Sequential browser fetches |
| Bounded browser concurrency | 1 Chrome x C4 | 500 | 4 | 70,297 | 121.1 / 106.8 / 228.5 ms | 0 / 0 | 2.51x vs C1 on the same sample |
| Stable single-browser baseline | 1 Chrome x C4 | 10,000 | 4 | 113,234 | 105.8 / 93.6 / 175.7 ms | 0 / 0 | Stable 10k baseline |
| Higher single-browser concurrency | 1 Chrome x C8 | 10,000 | 8 | 152,620 | 137.6 / 132.5 / 276.9 ms | 0 / 0 | 1.35x vs 1 Chrome x C4 |
| Two-browser baseline | 2 Chrome x C4 | 10,000 | 8 | 192,140 | 134.6 / 122.6 / 286.5 ms | 0 / 0 | Maintained default baseline |
| Historical scale comparison | 2 Chrome x C8 | 10,000 | 16 | 199,410 | 236.4 / not retained / 487.8 ms | 0 / 0 | +3.78%; one classification mismatch |
| Historical scale comparison | 4 Chrome x C4 | 10,000 | 16 | 202,856 | approximately doubled | 0 / 0 | +5.58%; about 3.46-4.08 GB Chrome working set |
| **Stable comparison (default)** | **2 Chrome x C4** | **20,000** | **8** | **193,457** | **136.1 / 126.7 / 280.5 ms** | **0 / 0** | **Completed; 20k baseline** |
| Stable comparison | 2 Chrome x C8 | 20,000 | 16 | 200,086 | 245.7 / 236.6 / 484.3 ms | 0 / 0 | Completed; +3.4% vs 2 Chrome x C4 |
| Stable comparison | 4 Chrome x C4 | 20,000 | 16 | 199,951 | 265.7 / 240.9 / 577.1 ms | 0 / 0 | Completed; +3.4% vs 2 Chrome x C4 |

## Conclusion

- C1 to C4 in one Chrome improved the same 500-ID sample from 28,061 to
  70,297 IDs/hour (**2.51x**).
- One Chrome x C8 reached 152,620 IDs/hour, then two Chrome x C4 reached
  192,140 IDs/hour while holding aggregate concurrency at eight.
- In the stable 20,000-ID comparison, 2 Chrome x C8 and 4 Chrome x C4 each
  gained about **3.4%** over 2 Chrome x C4 but substantially increased latency.
- **2 Chrome x C4 remains the default** because it has the clearest rate,
  latency, memory, and operational-complexity trade-off.

The four-browser validation includes corrected handling of challenge-skipped
and transient browser-network results. These remain resumable unless they
exhaust the bounded retry policy; no terminal checkpoint format changed.

## Reproducibility Notes

- The stable comparison uses the first 20 deterministic input batches
  (20,000 IDs). Earlier rows retain their original 500-ID or 10,000-ID samples.
- IDs are split into contiguous deterministic partitions. With two browsers,
  each receives 10,000 IDs; with four browsers, each receives 5,000 IDs.
- Each worker owns separate checkpoints, logs, progress, and terminal metrics.
- A manifest prevents a run directory from being resumed with incompatible
  batch range, browser concurrency, browser count, or Selenium call size.
- Active elapsed time excludes idle time between resumed attempts.
- Throughput varies with the host, network, and upstream service. These numbers
  are measured observations, not guaranteed production rates.
