# Data Source Audit

- Run directory: `/Users/bakii/tradingagents 汇报/tradingagents_bundle/outputs/runs/gree_weekly_2025q4_range`
- Files checked: 28
- Structured source records: 14
- Inferred source records: 126
- Unstructured artifacts: 0
- Inference rule: inferred records are text mentions in old artifacts, not authoritative tool-call logs.

## Configured Source Stack
- **market**: local_prefetch_cache; AkShare A-share OHLCV; BaoStock A-share OHLCV; Qlib provider for backtest execution
- **news**: a-stock-data / EastMoney stock news; a-stock-data / CNInfo announcements; AkShare stock_news_em; AkShare news_cctv for market-wide news
- **fundamentals**: a-stock-data / EastMoney company profile; a-stock-data / CNInfo announcements; a-stock-data / Sina financial statements gated by audited announcements; AkShare financial abstract/statements; BaoStock profit snapshot with pubDate cutoff
- **social**: Unified sentiment/news tools when available; Data-quality header marks unavailable feeds as unusable

## Extracted Source Summary

| component   |   structured_records |   inferred_records |   ok_records | sources                            | vendors                                | cutoff_dates                                                                                                                                                           | warnings                                                                 |
|:------------|---------------------:|-------------------:|-------------:|:-----------------------------------|:---------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|:-------------------------------------------------------------------------|
| market      |                    0 |                 56 |            0 | AkShare; BaoStock; EastMoney; Sina | AkShare; BaoStock; 东方财富; 新浪|Sina |                                                                                                                                                                        | Inferred from natural-language artifact text; not a structured tool log. |
| news        |                   14 |                 28 |            0 | BaoStock; CNInfo                   | BaoStock; 巨潮资讯|CNInfo              | 2025-10-03; 2025-10-10; 2025-10-17; 2025-10-24; 2025-10-31; 2025-11-07; 2025-11-14; 2025-11-21; 2025-11-28; 2025-12-05; 2025-12-12; 2025-12-19; 2025-12-26; 2025-12-31 | Inferred from natural-language artifact text; not a structured tool log. |
| social      |                    0 |                 42 |            0 | EastMoney                          | 东方财富                               |                                                                                                                                                                        | Inferred from natural-language artifact text; not a structured tool log. |