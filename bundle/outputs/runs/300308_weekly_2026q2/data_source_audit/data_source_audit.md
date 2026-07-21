# Data Source Audit

- Run directory: `/Users/bakii/tradingagents 汇报/tradingagents_bundle/outputs/runs/300308_weekly_2026q2`
- Files checked: 28
- Structured source records: 14
- Inferred source records: 183
- Unstructured artifacts: 0
- Inference rule: inferred records are text mentions in old artifacts, not authoritative tool-call logs.

## Configured Source Stack
- **market**: local_prefetch_cache; AkShare A-share OHLCV; BaoStock A-share OHLCV; Qlib provider for backtest execution
- **news**: a-stock-data / EastMoney stock news; a-stock-data / CNInfo announcements; AkShare stock_news_em; AkShare news_cctv for market-wide news
- **fundamentals**: a-stock-data / EastMoney company profile; a-stock-data / CNInfo announcements; a-stock-data / Sina financial statements gated by audited announcements; AkShare financial abstract/statements; BaoStock profit snapshot with pubDate cutoff
- **social**: Unified sentiment/news tools when available; Data-quality header marks unavailable feeds as unusable

## Extracted Source Summary

| component    |   structured_records |   inferred_records |   ok_records | sources                            | vendors                                | cutoff_dates                                                                                                                                                           | warnings                                                                 |
|:-------------|---------------------:|-------------------:|-------------:|:-----------------------------------|:---------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|:-------------------------------------------------------------------------|
| fundamentals |                    0 |                  9 |            0 | BaoStock; EastMoney                | BaoStock; 东方财富                     |                                                                                                                                                                        | Inferred from natural-language artifact text; not a structured tool log. |
| market       |                    0 |                 62 |            0 | AkShare; BaoStock; EastMoney; Sina | AkShare; BaoStock; 东方财富; 新浪|Sina |                                                                                                                                                                        | Inferred from natural-language artifact text; not a structured tool log. |
| news         |                   14 |                 68 |            0 | BaoStock; CNInfo; EastMoney        | BaoStock; 东方财富; 巨潮资讯|CNInfo    | 2026-04-03; 2026-04-10; 2026-04-17; 2026-04-24; 2026-05-01; 2026-05-08; 2026-05-15; 2026-05-22; 2026-05-29; 2026-06-05; 2026-06-12; 2026-06-19; 2026-06-26; 2026-06-30 | Inferred from natural-language artifact text; not a structured tool log. |
| social       |                    0 |                 44 |            0 | CNInfo; EastMoney                  | 东方财富; 巨潮资讯|CNInfo              |                                                                                                                                                                        | Inferred from natural-language artifact text; not a structured tool log. |