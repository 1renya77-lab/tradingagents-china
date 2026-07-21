# Execution Gap Analysis - 300308

## Summary

- signals: `11`
- weekend/holiday execution cases: `11`
- positive gap cases: `6`
- negative gap cases: `5`
- mean target position: `38.36%`
- mean signal-close to execution-open gap: `-0.08%`
- mean post-execution stock return: `8.16%`
- estimated gap not captured by T+1 execution: `1.02%`
- estimated post-execution position capture: `32.77%`

## Signal Windows

| signal_date | execution_date | window_end | target_position | gap_return | post_execution_return | signal_to_window_return | gap_not_captured | post_execution_capture |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-04-03 | 2026-04-07 | 2026-04-13 | 35.00% | 0.24% | 21.51% | 21.81% | 0.09% | 7.53% |
| 2026-04-10 | 2026-04-13 | 2026-04-20 | 45.00% | 0.56% | 14.92% | 15.57% | 0.25% | 6.71% |
| 2026-04-17 | 2026-04-20 | 2026-04-27 | 42.00% | -0.24% | 5.89% | 5.64% | -0.10% | 2.47% |
| 2026-04-24 | 2026-04-27 | 2026-05-06 | 60.00% | 1.35% | -1.05% | 0.29% | 0.81% | -0.63% |
| 2026-05-08 | 2026-05-11 | 2026-05-18 | 35.00% | 0.35% | 15.86% | 16.26% | 0.12% | 5.55% |
| 2026-05-15 | 2026-05-18 | 2026-05-25 | 35.00% | -1.89% | 2.42% | 0.49% | -0.66% | 0.85% |
| 2026-05-22 | 2026-05-25 | 2026-06-01 | 40.00% | 1.64% | 10.05% | 11.85% | 0.66% | 4.02% |
| 2026-05-29 | 2026-06-01 | 2026-06-08 | 40.00% | -0.01% | -2.43% | -2.44% | -0.01% | -0.97% |
| 2026-06-05 | 2026-06-08 | 2026-06-15 | 10.00% | -4.00% | 3.73% | -0.42% | -0.40% | 0.37% |
| 2026-06-12 | 2026-06-15 | 2026-06-22 | 35.00% | 2.26% | 16.41% | 19.04% | 0.79% | 5.74% |
| 2026-06-26 | 2026-06-29 | 2026-06-30 | 45.00% | -1.19% | 2.50% | 1.28% | -0.53% | 1.13% |

## Reading

- `gap_return`: signal-day close to next-trading-day open. This is the part a strict after-close T+1-open policy cannot capture.
- `post_execution_return`: execution open to next execution open, or final end-date close for the last window.
- `gap_not_captured` is `target_position * gap_return`; it is an exposure-adjusted estimate, not an executed PnL.
