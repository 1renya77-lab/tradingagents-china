# TradingAgents A股系统 Phase 1 改进说明

本阶段先完成 4 件事：数据源 provenance、时间戳审计、统一 Qlib provider、仓位校准结构化。

## 1. 数据源 Provenance

新增：

- `tradingagents/utils/provenance.py`
- `collect_daily_signals.py` 自动写入 provenance
- `run_experiment.py` 自动写入 provenance

每次 run 会生成：

- `outputs/runs/<run_name>/provenance/market_sources.json`
- `outputs/runs/<run_name>/provenance/news_sources.json`
- `outputs/runs/<run_name>/provenance/fundamentals_sources.json`
- `outputs/runs/<run_name>/provenance/social_sources.json`
- `outputs/runs/<run_name>/provenance/provenance_summary.md`
- `outputs/runs/<run_name>/provenance/provenance_details.csv`

证据等级：

- `tool_header`：来自机器可读 `DATA_*` 头，可信度最高。
- `timestamp_line`：来自明确的 `Published` / `Disclosure Date` 等时间戳行。
- `artifact_text_mention`：旧报告文本里的来源字面线索，只能作为弱证据。

## 2. 时间戳审计

增强：

- `tradingagents/utils/temporal_audit.py`

现在除了检查未来时间戳，还会统计：

- `missing_timestamp_mentions`
- `temporal_rule_mentions`

审计规则：

- 行情：`date <= signal_date`
- 新闻：`publish_time <= signal_date`
- 公告：`disclosure_date <= signal_date`
- 财报：必须有明确披露/公告时间，或有公告验证对应报告期

输出：

- `outputs/runs/<run_name>/temporal_audit/temporal_audit.md`
- `outputs/runs/<run_name>/temporal_audit/temporal_audit_summary.csv`
- `outputs/runs/<run_name>/temporal_audit/temporal_audit_details.csv`

## 3. 统一 Qlib Provider

增强：

- `build_minimal_qlib_provider.py`

现在支持多股票、多基准：

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python build_minimal_qlib_provider.py \
  --tickers 300308,300750,601138,601899 \
  --benchmarks SH000300,SH000905 \
  --start 2025-07-01 \
  --end 2026-06-30 \
  --source baostock \
  --provider-uri data/qlib_cn_research \
  --force
```

输出：

- `data/qlib_cn_research/provider_manifest.json`

manifest 会记录：

- 创建时间
- 数据源
- 复权口径
- 股票列表
- 基准列表
- calendar 起止日期
- 每个 instrument 的行数

## 4. 仓位校准结构化

增强：

- `signal_positioning.py`
- `tradingagents/graph/trading_graph.py`

新增结构化字段：

- `position_constraints`
- `position_calibration`

旧字段仍保留：

- `target_position`
- `position_gate_notes`

`position_calibration` 示例：

```json
{
  "raw_position": 0.9,
  "target_position": 0.7,
  "constraints": [
    {
      "rule": "fundamentals_missing",
      "cap": 0.7,
      "from_position": 0.9,
      "to_position": 0.7,
      "note": "基本面数据缺失仓位上限触发..."
    }
  ],
  "evidence_flags": {
    "macd_weak": false,
    "ma_bearish": false,
    "rsi_weak": false,
    "fundamentals_missing": true,
    "news_missing": false,
    "strong_uptrend_or_rr": false
  }
}
```

这一步是历史实验口径，目标是让仓位为什么被压低、为什么应该提高都可以被审计。当前主流程默认 `none`，直接使用 agent 输出的 `target_position`；如需复现实验旧口径，可以显式指定 `evidence_weighted`，它会优先读取 Portfolio Manager 的结构化 evidence scores：

- `trend_strength`
- `reward_risk_score`
- `catalyst_strength`
- `drawdown_risk`
- `data_quality`
- `recommended_position_floor`
- `position_invalid_if`

如果强趋势、高赔率、催化剂、低回撤风险和高数据质量共同成立，系统允许提高 `target_position`，目标是改善超额收益、alpha 和 IR；如果 `drawdown_risk` 高或 `data_quality` 差，则阻止因为文本中出现“趋势向上”而盲目加仓。

补充实验模式：

- `alpha_participation`

它位于 `evidence_weighted` 和 `return_seeking` 之间：

- 比 `evidence_weighted` 更强调参与强趋势窗口的 alpha；
- 比 `return_seeking` 更克制，不会只因为叙述偏多就大幅提仓；
- 当结构化 evidence 缺失，但文本里已经出现较强的趋势、催化和赔率线索时，允许把过低仓位抬到中等参与水平。

当前它仍是实验模式，不是默认模式。是否替换默认，必须看跨股票结果，而不是只看单一强趋势样本。

## 5. Alpha Gap 诊断

增强：

- `alpha_gap_diagnostics.py`

现在不仅统计“低仓后股票上涨”的 missed upside，还会统计相对基准的 `underallocated_alpha_cases`：

- `underallocated_alpha_cases`：低仓位、个股窗口收益跑赢基准、但 agent 没有捕捉到这段主动收益的次数。
- `underallocated_alpha_sum`：这些窗口中，个股相对基准收益减去 agent 相对基准收益的累计差。
- `strong_evidence_underallocation_cases`：如果当时 `position_calibration.return_evidence.score` 已经很高，但仍低仓，说明不是“没证据”，而是仓位/风险 gate 或进攻型 agent 没把证据转成仓位。

示例：

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python alpha_gap_diagnostics.py \
  --signals outputs/runs/<run_name>/signals/signals_<ticker>_<start>_<end>_weekly_position.csv \
  --report outputs/baseline_comparisons/<run_name>/backtests/agent/report_normal_1day.csv \
  --provider-uri data/qlib_cn_research \
  --ticker <ticker> \
  --start <start> \
  --end <end> \
  --output-dir outputs/baseline_comparisons/<run_name>/alpha_gap
```

这个诊断是后续优化的主要证据入口：如果 underallocated alpha 集中出现在强趋势/高 evidence 分数窗口，就说明下一步应该继续解决“强趋势仓位不足”和“进攻型 agent 失效”，而不是继续强化保守 gate。

## 验证

已通过：

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python -m unittest discover -s tests -p 'test_provenance.py'
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python -m unittest discover -s tests -p 'test_temporal_audit.py'
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python -m unittest discover -s tests -p 'test_signal_positioning.py'
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python -m unittest discover -s tests -p 'test_alpha_gap_diagnostics.py'
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python -m unittest discover -s tests -p 'test_qlib_provider_builder.py'
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python -m unittest discover -s tests -p 'test_collect_daily_signals.py'
```

也通过了相关文件的 `py_compile`。
