# Provenance Summary

- Run directory: `/Users/bakii/tradingagents 汇报/tradingagents_bundle/outputs/runs/iflytek_weekly_2025q4_range`
- Artifacts checked: 28
- Provenance records: 145

## Component Summary

| component   |   records |   structured_records |   inferred_records |   time_evidence_records | sources                                    | vendors                                                 |
|:------------|----------:|---------------------:|-------------------:|------------------------:|:-------------------------------------------|:--------------------------------------------------------|
| market      |        75 |                    0 |                 75 |                       0 | AkShare; BaoStock; CNInfo; EastMoney; Sina | AkShare; BaoStock; 东方财富; 巨潮资讯|CNInfo; 新浪|Sina |
| news        |        28 |                   14 |                 14 |                       0 | BaoStock                                   | BaoStock                                                |
| social      |        42 |                    0 |                 42 |                       0 | EastMoney                                  | 东方财富                                                |

## Reading Rule

- `structured_records` come from machine-readable DATA_* headers in agent input artifacts.
- `inferred_records` are only text mentions in existing artifacts; they are weaker than tool headers.
- `time_evidence_records` count explicit publish/disclosure timestamp lines found in the same artifacts.
- This file records evidence availability; future-information violations are judged by temporal_audit.
