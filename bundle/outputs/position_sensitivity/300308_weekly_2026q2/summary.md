# 300308 Q2 Position Sensitivity

This is a post-hoc diagnostic. It does not overwrite the original TradingAgents run.

| variant | total_return | excess_return | max_drawdown | Sharpe | win_rate | turnover_sum | cost_sum | trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| original_agent | 26.13% | 16.56% | -7.37% | 4.06 | 68.97% | 2.07 | 0.20% | 11 |
| buy_hold_100 | 100.55% | 90.98% | -12.14% | 5.14 | 67.24% | 0.99 | 0.05% | 1 |
| scaled_1.25 | 33.58% | 24.02% | -9.03% | 4.05 | 68.97% | 2.71 | 0.26% | 12 |
| scaled_1.50 | 41.77% | 32.21% | -10.69% | 4.11 | 68.97% | 3.30 | 0.31% | 13 |
| floor_40 | 32.03% | 22.46% | -7.41% | 4.42 | 68.97% | 1.18 | 0.11% | 9 |

## Reading

- `scaled_1.25` and `scaled_1.50` multiply the original target_position and cap it at 95%.
- `floor_40` raises every positive target_position below 40% to 40%, capped at 95%.
- These variants are diagnostics for position sizing only, not standard TradingAgents results.
