# Selenium Crawler Benchmark Results

This file keeps the useful results from the controlled browser-fetch tests.
All tests used a persistent Chrome session, browser-side JavaScript `fetch()`,
zero artificial delay, and bounded concurrency. Success is HTTP 200 with valid
JSON; 404/410 is not-found. WAF and browser failures were not checkpointed as
complete.

`C<N>` means `<N>` concurrent browser-side fetch workers per Chrome.

## Improvement Path

| Step | Configuration | Sample | IDs/hour | Mean / median / P95 latency | WAF / errors |
| --- | --- | ---: | ---: | --- | --- |
| Starting point | 1 Chrome x C1 | 500 | 28,061 | 113.8 / 82.0 / 285.9 ms | 0 / 0 |
| Bounded browser concurrency | 1 Chrome x C4 | 500 | 70,297 | 121.1 / 106.8 / 228.5 ms | 0 / 0 |
| Stable single-browser baseline | 1 Chrome x C4 | 10,000 | 113,234 | 105.8 / 93.6 / 175.7 ms | 0 / 0 |
| Higher single-browser concurrency | 1 Chrome x C8 | 10,000 | 152,620 | 137.6 / 132.5 / 276.9 ms | 0 / 0 |
| Maintained default | 2 Chrome x C4 | 10,000 | 192,140 | 134.6 / 122.6 / 286.5 ms | 0 / 0 |

## Measured Gains

- **C1 to C4 in one Chrome:** 28,061 to 70,297 IDs/hour, a **2.51x** gain on
  the same 500-ID sample.
- **One Chrome C4 to C8:** 113,234 to 152,620 IDs/hour, a **1.35x** gain
  (+34.8%) on the same 10,000-ID sample. Mean latency rose 30.1% and P95 rose
  57.6%.
- **One Chrome C8 to two Chrome C4:** 152,620 to 192,140 IDs/hour, a **1.25x**
  gain (+23.5%) while holding aggregate fetch concurrency at 8. The final
  success/not-found split remained exactly 6,699 / 3,301.
- The maintained 2 Chrome x C4 configuration measured **6.61x** the throughput
  of the earliest 1 Chrome x C1 trial. This is a useful direction-of-travel
  figure, not a strict like-for-like comparison because the samples differ.

## Why the Default Stops at 2 Chrome x C4

More concurrency was tested, but it was not a good default:

| Configuration | IDs/hour | Change vs 2 Chrome x C4 | Trade-off |
| --- | ---: | ---: | --- |
| 2 Chrome x C4 | 192,140 | baseline | About 2.0 GB combined Chrome working set |
| 2 Chrome x C8 | 192,187 | +0.02% | Mean latency 236.4 ms; P95 487.8 ms; one classification mismatch |
| 4 Chrome x C4 | 193,856 | +0.9% | About 3.46-4.08 GB Chrome working set; latency roughly doubled |

The extra rate from C8 or four browsers was small compared with the increased
memory use, tail latency, and operational complexity. Therefore the maintained
configuration is **2 Chrome x C4**.

## Reproducibility Notes

- The 10,000-ID tests use the first ten deterministic input batches.
- With two browsers, the first browser receives positions 1-5,000 and the
  second receives positions 5,001-10,000.
- Each worker owns separate checkpoints, logs, progress, and terminal metrics.
- A manifest prevents a run directory from being resumed with incompatible
  batch range, browser concurrency, browser count, or Selenium call size.
- Throughput varies with the host, network, and upstream service. These numbers
  are measured observations, not guaranteed production rates.
