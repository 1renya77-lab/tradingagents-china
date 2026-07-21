# Results Guide

这个目录目前混合了正式季度实验、压缩 prompt 变体、单 LLM 基线尝试、以及大量中途修复/调试 run。为了避免后续继续混乱，先按下面的口径使用。

## 1. 当前主结果

以下 run 可以作为“当前最应该看的结果”：

### A. `300308_weekly_2026q2`

- 类型：正式 Q2 周频 run
- 用途：多 Agent 完整流程的主参考结果
- 关键文件：
  - `outputs/runs/300308_weekly_2026q2/signals/`
  - `outputs/runs/300308_weekly_2026q2/reports/`
  - `outputs/runs/300308_weekly_2026q2/audit_reports/`
  - `outputs/runs/300308_weekly_2026q2/feedback_windows.csv`
  - `outputs/runs/300308_weekly_2026q2/mechanism_attribution.csv`
  - `outputs/runs/300308_weekly_2026q2/case_studies.md`
  - `outputs/baseline_comparisons/300308_weekly_2026q2/`

### B. `zijin_mining_weekly_2026q2`

- 类型：正式 Q2 周频 run
- 用途：和 `300308` 风格差异明显的第二只主股票
- 关键文件：
  - `outputs/runs/zijin_mining_weekly_2026q2/signals/`
  - `outputs/runs/zijin_mining_weekly_2026q2/reports/`
  - `outputs/runs/zijin_mining_weekly_2026q2/audit_reports/`
  - `outputs/runs/zijin_mining_weekly_2026q2/feedback_windows.csv`
  - `outputs/runs/zijin_mining_weekly_2026q2/mechanism_attribution.csv`
  - `outputs/runs/zijin_mining_weekly_2026q2/case_studies.md`
  - `outputs/baseline_comparisons/zijin_mining_weekly_2026q2/`

### C. `300308_weekly_2026q2_new_alpha`

- 类型：压缩 prompt / 新 alpha 版本
- 用途：和 `300308_weekly_2026q2` 做同股对比，观察 prompt 压缩后的行为变化
- 关键文件：
  - `outputs/runs/300308_weekly_2026q2_new_alpha/signals/`
  - `outputs/runs/300308_weekly_2026q2_new_alpha/reports/`
  - `outputs/runs/300308_weekly_2026q2_new_alpha/audit_reports/`
  - `outputs/runs/300308_weekly_2026q2_new_alpha/feedback_windows.csv`
  - `outputs/runs/300308_weekly_2026q2_new_alpha/mechanism_attribution.csv`
  - `outputs/runs/300308_weekly_2026q2_new_alpha/case_studies.md`
  - `outputs/baseline_comparisons/300308_weekly_2026q2_new_alpha/`

### D. `300308_weekly_2026q2_single_llm_direct`

- 类型：单 LLM 基线尝试
- 用途：后续和多 Agent 做机制对比
- 当前状态：只有信号 run，还没有补完整回测/feedback/mechanism 产物

## 2. 当前总表

如果只想快速看“主结果摘要”，优先看：

- `outputs/mechanism_study_existing/summary.csv`
- `outputs/mechanism_study_existing/summary.md`

说明：

- 这个总表目前只覆盖已经补过后处理的 run。
- 它不是自动涵盖所有历史目录，缺失的 run 需要补回测或补回填。

## 3. 其他季度实验

以下 run 有一定参考价值，但目前不作为第一汇报优先级：

- `catl_weekly_2026q2`
- `foxconn_industrial_weekly_2026q2`
- `hikvision_weekly_2026q2`
- `hikvision_weekly_2026q2_after_astock_fix`
- `zijin_mining_weekly_2026q2_compressed_after_astock_fix`
- `300308_weekly_1y`

这些目录更适合：

- 看不同股票风格
- 看不同校准模式或压缩策略的影响
- 后续再补统一机制研究口径

## 4. 调试 / 修复 / 中途检查目录

以下目录默认不进入正式结果汇报：

- `300308_promptcheck_*`
- `300308_replay_*`
- `300308_recheck_*`
- `alpha_replay_300308_202509`
- `hikvision_weekly_2026q2_compressed_smoke`
- `ab_full_002415_20260424`
- `minimax_fixed_300269_20260101_final`

这些 run 的定位是：

- prompt 结构测试
- 单日期/少日期修复验证
- upstream position contract 修复验证
- collector / parser / structured output 局部排障

如果不是在追查 bug，平时可以忽略它们。

## 5. 建议使用口径

以后默认按下面顺序看结果：

1. `outputs/mechanism_study_existing/summary.md`
2. 对应 run 的 `case_studies.md`
3. 对应 run 的 `comparison_*.md`
4. 对应 run 的 `reports/`
5. 需要深挖时再看 `audit_reports/` 和 `trajectories/`

## 6. 后续整理原则

后续新增 run，建议命名时显式区分这三类：

- 正式实验：`{ticker_or_alias}_{period}_{mode}`
- 对照组：`{ticker_or_alias}_{period}_{mode}_{variant}`
- 调试验证：`debug_*` 或 `promptcheck_*`

这样后面就可以把正式实验和调试 run 物理拆开，而不需要每次再人工辨认。
