# Provenance Summary

- Run directory: `/Users/bakii/tradingagents 汇报/tradingagents_bundle/outputs/runs/hengrui_weekly_2026q2_forecast`
- Artifacts checked: 28
- Provenance records: 212

## Component Summary

| component    |   records |   structured_records |   inferred_records |   time_evidence_records | sources                                    | vendors                                                 |
|:-------------|----------:|---------------------:|-------------------:|------------------------:|:-------------------------------------------|:--------------------------------------------------------|
| fundamentals |         6 |                    0 |                  6 |                       0 | BaoStock                                   | BaoStock                                                |
| market       |        77 |                    0 |                 77 |                       0 | AkShare; BaoStock; CNInfo; EastMoney; Sina | AkShare; BaoStock; 东方财富; 巨潮资讯|CNInfo; 新浪|Sina |
| news         |       129 |                   14 |                115 |                       0 | BaoStock; CNInfo; EastMoney                | BaoStock; 东方财富; 巨潮资讯|CNInfo                     |

## Reading Rule

- `structured_records` come from machine-readable DATA_* headers in agent input artifacts.
- `inferred_records` are only text mentions in existing artifacts; they are weaker than tool headers.
- `time_evidence_records` count explicit publish/disclosure timestamp lines found in the same artifacts.
- This file records evidence availability; future-information violations are judged by temporal_audit.
