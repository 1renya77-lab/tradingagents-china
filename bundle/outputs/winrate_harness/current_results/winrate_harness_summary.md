# Win-Rate Harness Current Results

Scope: current runs with both signals and agent Qlib backtests.

- runs: `4`
- signal windows: `52`
- overall stock-direction win rate: `55.77%`
- high exposure precision (target_position >= 50%): `0.00%` over `3` cases
- missed upside cases (position < 30%, stock_return > 0): `19`
- strong missed upside cases (position < 30%, stock_return >= 5%): `1`
- high-confidence wrong cases (confidence >= 0.70, stock_return < 0): `18`

## By Position Bucket

| position_bucket   |   signals |   win_rate |   avg_stock_return |   avg_position |   avg_confidence |
|:------------------|----------:|-----------:|-------------------:|---------------:|-----------------:|
| 0%-20%            |        31 |   0.516129 |        -0.00720587 |      0.0579032 |         0.729032 |
| 20%-40%           |        11 |   0.818182 |         0.0530697  |      0.290909  |         0.661818 |
| 40%-60%           |         7 |   0.571429 |         0.0409679  |      0.424286  |         0.672857 |
| 60%-80%           |         3 |   0        |        -0.0385518  |      0.65      |         0.666667 |
| 80%-95%           |         0 | nan        |       nan          |    nan         |       nan        |

## By Confidence Bucket

| confidence_bucket   |   signals |   win_rate |   avg_stock_return |   avg_position |   avg_confidence |
|:--------------------|----------:|-----------:|-------------------:|---------------:|-----------------:|
| 0-0.5               |         0 |    nan     |       nan          |    nan         |       nan        |
| 0.5-0.6             |         4 |      0.5   |         0.00225448 |      0.1625    |         0.5575   |
| 0.6-0.7             |        12 |      0.75  |         0.0455462  |      0.376667  |         0.645    |
| 0.7-0.8             |        24 |      0.625 |         0.00784575 |      0.1675    |         0.700833 |
| 0.8-1.0             |        12 |      0.25  |        -0.0176971  |      0.0604167 |         0.816667 |

## By Debate Agreement

| debate_agreement                          |   signals |   win_rate |   avg_stock_return |   avg_position |   avg_confidence |
|:------------------------------------------|----------:|-----------:|-------------------:|---------------:|-----------------:|
| bullish_or_hold_consensus                 |        47 |   0.553191 |         0.00918295 |       0.180106 |         0.708085 |
| direction_agreement_position_disagreement |         3 |   0.666667 |         0.058105   |       0.183333 |         0.653333 |
| direction_disagreement                    |         2 |   0.5      |        -0.0372047  |       0.45     |         0.675    |

## By Run

| run_name                    |   ticker |   signals |   win_rate |   avg_stock_return |   avg_position |   high_exposure_cases |   high_exposure_win_rate |
|:----------------------------|---------:|----------:|-----------:|-------------------:|---------------:|----------------------:|-------------------------:|
| 300308_weekly_2026q2        |   300308 |        13 |   0.769231 |         0.0618833  |      0.39      |                     2 |                        0 |
| gree_weekly_2025q4_range    |   000651 |        13 |   0.692308 |         0.00100091 |      0.153077  |                     0 |                      nan |
| iflytek_weekly_2025q4_range |   002230 |        13 |   0.384615 |        -0.00823524 |      0.0846154 |                     0 |                      nan |
| moutai_weekly_2026q2        |   600519 |        13 |   0.384615 |        -0.013764   |      0.135     |                     1 |                        0 |

## Missed Strong Upside Cases

| run_name                    |   ticker | signal_date   | execution_date   |   target_position |   confidence |   stock_return | action   | debate_agreement          |
|:----------------------------|---------:|:--------------|:-----------------|------------------:|-------------:|---------------:|:---------|:--------------------------|
| iflytek_weekly_2025q4_range |   002230 | 2025-10-24    | 2025-10-27       |               0.2 |          0.6 |      0.0578947 | 买入     | bullish_or_hold_consensus |

## High Confidence Wrong Cases

| run_name                    |   ticker | signal_date   | execution_date   |   target_position |   confidence |   stock_return | action   | debate_agreement                          |
|:----------------------------|---------:|:--------------|:-----------------|------------------:|-------------:|---------------:|:---------|:------------------------------------------|
| iflytek_weekly_2025q4_range |   002230 | 2025-10-31    | 2025-11-03       |             0.1   |         0.7  |    -0.0643213  | 卖出     | bullish_or_hold_consensus                 |
| moutai_weekly_2026q2        |   600519 | 2026-06-12    | 2026-06-15       |             0     |         0.7  |    -0.0606405  | 卖出     | bullish_or_hold_consensus                 |
| iflytek_weekly_2025q4_range |   002230 | 2025-11-07    | 2025-11-10       |             0     |         0.85 |    -0.0524117  | 卖出     | bullish_or_hold_consensus                 |
| iflytek_weekly_2025q4_range |   002230 | 2025-10-03    | 2025-10-09       |             0.25  |         0.85 |    -0.0466312  | 卖出     | bullish_or_hold_consensus                 |
| moutai_weekly_2026q2        |   600519 | 2026-05-29    | 2026-06-01       |             0     |         0.7  |    -0.0414469  | 卖出     | direction_agreement_position_disagreement |
| moutai_weekly_2026q2        |   600519 | 2026-04-24    | 2026-04-27       |             0.025 |         0.8  |    -0.038662   | 卖出     | bullish_or_hold_consensus                 |
| moutai_weekly_2026q2        |   600519 | 2026-05-15    | 2026-05-18       |             0     |         0.8  |    -0.0366766  | 卖出     | bullish_or_hold_consensus                 |
| iflytek_weekly_2025q4_range |   002230 | 2025-10-10    | 2025-10-13       |             0.1   |         0.8  |    -0.0297564  | 卖出     | bullish_or_hold_consensus                 |
| moutai_weekly_2026q2        |   600519 | 2026-04-10    | 2026-04-13       |             0     |         0.7  |    -0.0283934  | 持有     | bullish_or_hold_consensus                 |
| gree_weekly_2025q4_range    |   000651 | 2025-10-24    | 2025-10-27       |             0     |         0.8  |    -0.0217123  | 卖出     | bullish_or_hold_consensus                 |
| iflytek_weekly_2025q4_range |   002230 | 2025-11-28    | 2025-12-01       |             0.05  |         0.7  |    -0.0152549  | 持有     | bullish_or_hold_consensus                 |
| moutai_weekly_2026q2        |   600519 | 2026-06-19    | 2026-06-22       |             0.15  |         0.8  |    -0.0145325  | 卖出     | bullish_or_hold_consensus                 |
| gree_weekly_2025q4_range    |   000651 | 2025-12-26    | 2025-12-29       |             0.4   |         0.7  |    -0.0132483  | 持有     | bullish_or_hold_consensus                 |
| iflytek_weekly_2025q4_range |   002230 | 2025-12-12    | 2025-12-15       |             0.05  |         0.8  |    -0.0113131  | 卖出     | bullish_or_hold_consensus                 |
| moutai_weekly_2026q2        |   600519 | 2026-04-03    | 2026-04-07       |             0.7   |         0.7  |    -0.0109928  | 卖出     | bullish_or_hold_consensus                 |
| gree_weekly_2025q4_range    |   000651 | 2025-12-19    | 2025-12-22       |             0.45  |         0.7  |    -0.00923675 | 卖出     | bullish_or_hold_consensus                 |
| gree_weekly_2025q4_range    |   000651 | 2025-11-14    | 2025-11-17       |             0.08  |         0.7  |    -0.00886263 | 买入     | bullish_or_hold_consensus                 |
| iflytek_weekly_2025q4_range |   002230 | 2025-12-19    | 2025-12-22       |             0     |         0.8  |    -0.00143032 | 卖出     | bullish_or_hold_consensus                 |
