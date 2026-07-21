# Provenance Summary

- Run directory: `/Users/bakii/tradingagents 汇报/tradingagents_bundle/outputs/runs/300308_weekly_2026q2`
- Artifacts checked: 28
- Provenance records: 197

## Component Summary

| component    |   records |   structured_records |   inferred_records |   time_evidence_records | sources                                    | vendors                                                 |
|:-------------|----------:|---------------------:|-------------------:|------------------------:|:-------------------------------------------|:--------------------------------------------------------|
| fundamentals |         3 |                    0 |                  3 |                       0 | BaoStock                                   | BaoStock                                                |
| market       |        92 |                    0 |                 92 |                       0 | AkShare; BaoStock; CNInfo; EastMoney; Sina | AkShare; BaoStock; 东方财富; 巨潮资讯|CNInfo; 新浪|Sina |
| news         |       101 |                   14 |                 87 |                       0 | BaoStock; CNInfo; EastMoney                | BaoStock; 东方财富; 巨潮资讯|CNInfo                     |
| unknown      |         1 |                    0 |                  1 |                       0 | EastMoney                                  | 东方财富                                                |

## Reading Rule

- `structured_records` come from machine-readable DATA_* headers in agent input artifacts.
- `inferred_records` are only text mentions in existing artifacts; they are weaker than tool headers.
- `time_evidence_records` count explicit publish/disclosure timestamp lines found in the same artifacts.
- This file records evidence availability; future-information violations are judged by temporal_audit.
