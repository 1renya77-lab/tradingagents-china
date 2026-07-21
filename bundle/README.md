# TradingAgents A股 Bundle

面向 A 股市场的多智能体投研与交易信号生成原型，支持单股日频预测、A 股投研 prompt、reflection 复盘记忆、过程审计与 Qlib 回测。

## 快速开始

```bash
cd "/Users/bakii/tradingagents 汇报/tradingagents_bundle"
printf "DEEPSEEK_API_KEY=你的key\n" > .env
```

推荐解释器：

```bash
/Users/bakii/miniforge3/envs/tradingagents-cn/bin/python
```

更多说明：

- [docs/USAGE_ZH.md](/Users/bakii/tradingagents%20汇报/tradingagents_bundle/docs/USAGE_ZH.md)
- [docs/PROJECT_LANDING_PLAN.md](/Users/bakii/tradingagents%20汇报/tradingagents_bundle/docs/PROJECT_LANDING_PLAN.md)
- [docs/REFLECTION_MEMORY_SECTION.md](/Users/bakii/tradingagents%20汇报/tradingagents_bundle/docs/REFLECTION_MEMORY_SECTION.md)

## 常用命令

```bash
# 单日信号
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python run_signal.py \
  --ticker 600036 \
  --date 2026-06-30 \
  --quick-model deepseek-v4-flash \
  --deep-model deepseek-v4-pro

# 四分析师完整版本
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python run_signal.py \
  --ticker 600036 \
  --date 2026-06-30 \
  --analysts market fundamentals news social \
  --max-debate-rounds 1 \
  --max-risk-rounds 1 \
  --quick-model deepseek-v4-flash \
  --deep-model deepseek-v4-pro

# 批量日频信号
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python collect_daily_signals.py \
  --ticker 600036 \
  --start 2026-06-01 \
  --end 2026-06-30 \
  --frequency daily \
  --analysts market fundamentals news social \
  --quick-model deepseek-v4-flash \
  --deep-model deepseek-v4-pro \
  --run-name with_memory \
  --output-file outputs/runs/with_memory/signals/signals_600036_2026-06-01_2026-06-30_daily_position.csv

# 批量周频信号：每周最后一个工作日生成一次信号
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python prefetch_market_data.py \
  --ticker 300269 \
  --start 2026-06-01 \
  --end 2026-06-30 \
  --lookback-days 320 \
  --source auto

PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python collect_daily_signals.py \
  --ticker 300269 \
  --start 2026-06-01 \
  --end 2026-06-30 \
  --frequency weekly \
  --analysts market fundamentals news social \
  --quick-model deepseek-v4-flash \
  --deep-model deepseek-v4-pro \
  --run-name weekly_test \
  --resume

# Qlib 可直接回测稀疏 weekly position CSV
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python backtest_existing_signals_qlib.py \
  --signals outputs/runs/weekly_test/signals/signals_300269_2026-06-01_2026-06-30_weekly_position.csv \
  --ticker 300269 \
  --provider-uri data/qlib_cn_300269 \
  --output-dir outputs/backtests/qlib_weekly_test

# 配置驱动实验
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python run_experiment.py \
  --config config/experiment_example.json

# MiniMax 配置驱动实验
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python run_experiment.py \
  --config config/experiment_minimax_example.json
```

周频模式不只是少跑几天。启用 `--frequency weekly` 后，系统会把决策周期注入 agent prompt：看多/看空研究、交易员、风险辩论和风险经理都会围绕“未来5个交易日/直到下一次周频再平衡前”的持仓判断生成建议，而不是预测明天单日涨跌。

长周期实验建议先运行 `prefetch_market_data.py`。它会一次性预取 `start - lookback_days` 到 `end` 的 A 股行情，后续每个 agent 信号仍然只会读取 `<= 当前信号日期` 的切片。也就是说，缓存文件可以包含未来月份的数据，但工具层会在进入 LLM 前截断，避免未来信息泄漏。

## 信号与回测口径

当前版本采用“离散操作 + 目标仓位”的信号口径：

- `action`：LLM 的原始离散判断，只表示 `买入 / 持有 / 卖出`。
- `score`：兼容旧版 long/cash 阈值回测的连续分数。
- `target_position`：新的可执行目标仓位，取值 `0.0-1.0`，例如 `0.3` 表示目标持仓 30%。

默认生成的信号文件会带 `_position.csv` 后缀，例如 `signals_300269_2026-06-01_2026-06-30_weekly_position.csv`。这是正式回测文件；旧的 `_weekly.csv` 只用于历史结果补齐，不再作为新实验的默认输出。

长任务建议加 `--resume`。脚本会在每个日期完成后立即写入 CSV；如果断网或中断，重跑同一命令会跳过已有 `status=ok` 的日期，只补跑缺失或失败日期。

Qlib 回测会优先使用 `target_position` 调仓；只有 CSV 不含 `target_position` 时，才退回旧的 `score >= buy_threshold` / `score <= sell_threshold` 规则。  
因此，“持有”不再等价于“不交易”：如果报告写“持有 40%-50% 仓位”，回测会按约 45% 的目标仓位执行。

Markdown 报告顶部也会同步写出：

- 原始操作
- 执行目标仓位
- 回测执行口径说明

如果已有旧信号需要补齐目标仓位，可离线执行：

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python add_target_positions_to_signals.py \
  --signals path/to/legacy_signals.csv
```

如果已有旧报告需要把顶部文字对齐到目标仓位口径，可执行：

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python update_reports_with_positions.py \
  --signals outputs/runs/weekly_test/signals/signals_300269_2026-06-01_2026-06-30_weekly_position.csv
```

## 输出目录

所有运行产物统一保存在 `outputs/`：

- `outputs/signals/`
- `outputs/reports/`
- `outputs/trajectories/`
- `outputs/audit_reports/`
- `outputs/backtests/qlib/`
- `outputs/backtests/simple/`
- `outputs/backtests/baostock/`
- `outputs/memory/decision_memory.md`

## 核心脚本

- `run_signal.py`：单日信号
- `collect_daily_signals.py`：批量日频/周频信号
- `run_experiment.py`：按 JSON 配置跑固定实验
- `build_minimal_qlib_provider.py`：构建最小 Qlib 数据
- `backtest_existing_signals_qlib.py`：Qlib 回测
- `run_baostock_backtest.py`：Baostock 回测

## Reflection Memory

默认启用 markdown decision log：

```bash
cat outputs/memory/decision_memory.md
```

运行逻辑：

```text
第 t 日生成信号 -> 写入 pending
第 t+1 日同股票运行 -> 计算后续收益和 alpha -> 生成 reflection -> 注入 Portfolio Manager
```

这套机制不依赖 embedding，适配 DeepSeek-only 环境。

## 实验产物隔离

重复跑同一股票和日期时，建议使用 `--run-name`，避免覆盖旧报告、轨迹和审计文件：

```bash
--run-name with_memory
```

对应产物会写到：

```text
outputs/runs/with_memory/signals/
outputs/runs/with_memory/reports/
outputs/runs/with_memory/trajectories/
outputs/runs/with_memory/audit_reports/
```

## MiniMax

当前已支持 `--provider minimax`，默认走官方 OpenAI-compatible 端点：

```text
https://api.minimax.io/v1
```

环境变量：

```text
MINIMAX_API_KEY
```

## 可选分析师

- `market`：市场技术分析师
- `fundamentals`：基本面分析师
- `news`：新闻分析师
- `social`：社交媒体分析师
