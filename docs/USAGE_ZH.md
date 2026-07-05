# TradingAgents A股版使用手册

## 1. 环境准备

```bash
cd "/Users/bakii/tradingagents 汇报/tradingagents_bundle"
printf "DEEPSEEK_API_KEY=你的key\n" > .env
```

推荐解释器：

```bash
/Users/bakii/miniforge3/envs/tradingagents-cn/bin/python
```

## 2. 常用命令

### 2.1 单日信号

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python run_signal.py \
  --ticker 600036 \
  --date 2026-06-30 \
  --analysts market fundamentals news social \
  --max-debate-rounds 1 \
  --max-risk-rounds 1 \
  --provider deepseek \
  --quick-model deepseek-v4-flash \
  --deep-model deepseek-v4-pro \
  --run-name demo_single
```

### 2.2 批量日频信号

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python collect_daily_signals.py \
  --ticker 600036 \
  --start 2026-06-01 \
  --end 2026-06-30 \
  --frequency daily \
  --analysts market fundamentals news social \
  --max-debate-rounds 1 \
  --provider deepseek \
  --quick-model deepseek-v4-flash \
  --deep-model deepseek-v4-pro \
  --run-name with_memory \
  --output-file outputs/runs/with_memory/signals/signals_600036_2026-06-01_2026-06-30_daily_position.csv
```

### 2.3 批量周频信号

周频模式只在每周最后一个工作日生成一次信号，适合降低 LLM 调用成本，也更接近“每周调仓”的实验设定。
启用 `--frequency weekly` 后，系统会把决策周期注入 agent prompt：看多/看空研究、交易员、风险辩论和风险经理都会围绕“未来5个交易日/直到下一次周频再平衡前”的持仓判断生成建议，而不是预测明天单日涨跌。

长周期实验建议先预取行情。预取文件可以覆盖完整实验期，但每个信号日进入 agent 的行情都会在工具层强制截断到 `<= 当前信号日期`，避免未来信息泄漏：

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python prefetch_market_data.py \
  --ticker 300269 \
  --start 2026-06-01 \
  --end 2026-06-30 \
  --lookback-days 320 \
  --source auto
```

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python collect_daily_signals.py \
  --ticker 300269 \
  --start 2026-06-01 \
  --end 2026-06-30 \
  --frequency weekly \
  --analysts market fundamentals news social \
  --max-debate-rounds 1 \
  --provider deepseek \
  --quick-model deepseek-v4-flash \
  --deep-model deepseek-v4-pro \
  --run-name weekly_test \
  --resume
```

默认输出：

```text
outputs/runs/weekly_test/signals/signals_300269_2026-06-01_2026-06-30_weekly_position.csv
```

新实验默认输出带 `_position.csv` 后缀。该文件包含 `target_position`，是正式回测入口；旧的 `_weekly.csv` 只用于历史结果补齐，不再作为默认输出。

长任务建议加 `--resume`。每个日期完成后会立即写入 CSV；如果中断，重跑同一命令会跳过已有 `status=ok` 的日期，只补跑缺失或失败日期。

### 2.4 构建 Qlib 数据

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python build_minimal_qlib_provider.py \
  --ticker 600036 \
  --start 2026-06-01 \
  --end 2026-06-30 \
  --provider-uri data/qlib_cn_test
```

### 2.5 Qlib 回测

当前回测优先读取信号 CSV 中的 `target_position` 列，并按目标仓位在下一交易日调仓。  
如果 CSV 没有 `target_position`，才使用旧版 `score` 阈值规则：

- `score >= buy_threshold`：买入或加仓
- `score <= sell_threshold`：卖出至现金
- 其他：保持当前仓位

因此，新版本里 `action=持有` 不是“不交易”的同义词。真正的交易指令是 `target_position`，例如：

| action | target_position | 回测含义 |
|:---|---:|:---|
| 持有 | 0.45 | 调整到 45% 仓位 |
| 卖出 | 0.30 | 降到 30% 仓位，而不是裸卖空 |
| 买入 | 0.80 | 调整到 80% 仓位 |

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python backtest_existing_signals_qlib.py \
  --signals outputs/signals/signals_600036_2026-06-01_2026-06-30_daily_position.csv \
  --ticker 600036 \
  --start 2026-06-01 \
  --end 2026-06-30 \
  --provider-uri data/qlib_cn_test \
  --output-dir outputs/backtests/qlib
```

周频 CSV 是稀疏信号，Qlib 回测入口不用改：

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python backtest_existing_signals_qlib.py \
  --signals outputs/runs/weekly_test/signals/signals_300269_2026-06-01_2026-06-30_weekly_position.csv \
  --ticker 300269 \
  --provider-uri data/qlib_cn_300269 \
  --output-dir outputs/backtests/qlib_weekly_test
```

如果是高价股，`--init-cash` 不宜太小。A 股一手为 100 股，若初始资金不足以按目标仓位买入一手，Qlib 会因为交易单位取整而无法下单。单股高价回测可先用：

```bash
--init-cash 1000000
```

### 2.6 信号评估汇总

用于快速回答“这批信号后续表现如何”，会输出逐条 forward return、benchmark return、alpha、decision alpha 和方向命中率。

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python evaluate_signals.py \
  --signals outputs/signals/signals_300269_2026-06-30_2026-07-03_with_memory.csv \
  --holding-days 1 \
  --benchmark SH000905 \
  --output-dir outputs/evaluations/300269_with_memory
```

输出：

- `outputs/evaluations/.../*_evaluated.csv`：逐条信号评估明细
- `outputs/evaluations/.../signal_evaluation_summary.md`：汇总表

### 2.7 固定实验配置

如果希望把股票池、模型、日期区间和评估方式固定下来，推荐使用 `run_experiment.py`：

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python run_experiment.py \
  --config config/experiment_example.json
```

样例配置文件：

```text
config/experiment_example.json
config/experiment_minimax_example.json
```

运行后会自动：

- 生成指定股票池的 signal CSV
- 在同一 `run_name` 目录下保存报告、轨迹、审计和 signals
- 可选输出 `evaluated.csv` 与 `experiment_summary.md`
- 写出 `experiment_manifest.json` 记录本次实验参数和产物路径

如果要切到 MiniMax：

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python run_signal.py \
  --ticker 300269 \
  --date 2026-07-03 \
  --provider minimax \
  --quick-model MiniMax-M2.7-highspeed \
  --deep-model MiniMax-M2.7-highspeed
```

当前默认兼容地址：

```text
https://api.minimax.io/v1
```

需要的环境变量：

```text
MINIMAX_API_KEY
```

## 3. 参数说明

- `--ticker`：A 股六位代码，例如 `600036`、`000001`
- `--date`：单日信号日期，格式 `YYYY-MM-DD`
- `--start --end`：批量信号或回测区间
- `--analysts`：
  - `market`：市场技术分析师
  - `fundamentals`：基本面分析师
  - `news`：新闻分析师
  - `social`：社交媒体分析师
- `--max-debate-rounds`：多空辩论轮数，建议先用 `1`
- `--max-risk-rounds`：风险讨论轮数，建议先用 `1`
- `--provider`：模型供应商，DeepSeek 用 `deepseek`
- `--model`：模型名称，DeepSeek 可用 `deepseek-v4-flash` 或 `deepseek-v4-pro`
- `--quick-model`：快速模型，适合用 `deepseek-v4-flash`
- `--deep-model`：深度模型，适合用 `deepseek-v4-pro`
- `--output-file`：批量信号 CSV 输出路径，避免覆盖旧结果
- `--run-name`：实验运行名；设置后报告、轨迹、审计和默认信号会写到 `outputs/runs/{run-name}/`

如果想让 quick think 用 flash、deep think 用 pro：

```bash
--provider deepseek --quick-model deepseek-v4-flash --deep-model deepseek-v4-pro
```

## 4. 推荐用法

### 4.1 先验证链路

```bash
--analysts market fundamentals
```

### 4.2 做完整展示

```bash
--analysts market fundamentals news social
```

### 4.3 控制耗时

- 初次测试先跑单日
- 批量信号先跑 3 到 5 个交易日
- 辩论和风险轮数先固定为 `1`

## 5. 输出目录

所有运行产物统一保存在 `outputs/` 下：

- `outputs/signals/`：单日 JSON 与批量 CSV 信号
- `outputs/reports/`：Markdown 可读复盘报告
- `outputs/trajectories/`：过程轨迹 JSON
- `outputs/audit_reports/`：完整审计 JSON
- `outputs/memory/decision_memory.md`：reflection 记忆日志
- `outputs/evaluations/`：信号评估汇总
- `outputs/runs/{run_name}/manifests/`：实验 manifest
- `outputs/backtests/qlib/`：Qlib 回测结果
- `outputs/backtests/simple/`：简单回测结果
- `outputs/backtests/baostock/`：Baostock 回测结果

注意：批量 CSV 可以用 `--output-file` 避免覆盖；报告、轨迹、审计文件当前仍按 `ticker + date` 固定命名，重跑同一天会覆盖。

### 5.1 信号 CSV 字段

新生成的批量信号 CSV 会包含以下关键列：

| 字段 | 含义 |
|:---|:---|
| `date` | 信号日期 |
| `ticker` | 股票代码 |
| `action` | LLM 原始离散判断：买入/持有/卖出 |
| `confidence` | 置信度 |
| `risk_score` | 风险得分 |
| `target_price` | 目标价 |
| `score` | 旧版 long/cash 回测兼容分数 |
| `target_position` | 新版可执行目标仓位，Qlib 回测优先使用 |
| `reasoning` | 最终摘要 |

`target_position` 来自最终决策文本中的仓位表达，例如“持有40%-50%仓位”“减持至30%以下”“试探建仓5%-8%”。如果文本没有明确仓位，则使用保守默认值：买入约 80%，持有约 50%，卖出 0%。

### 5.2 Markdown 报告口径

新生成的 `report_*.md` 顶部会包含：

```text
## 最终信号
- 原始操作: 持有
- 执行目标仓位: 45.0%
- 执行说明: 回测按目标仓位在下一交易日调仓
```

报告中的 agent 辩论正文保留原始过程，不强行改写；真正与回测交易对应的是顶部的“执行目标仓位”和 `signals.csv` 的 `target_position`。

### 5.3 旧结果补齐目标仓位

已有旧版 `signals.csv` 可以不重新调用 LLM，直接从现有 `reasoning` 和 `audit_reports` 解析目标仓位：

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python add_target_positions_to_signals.py \
  --signals path/to/legacy_signals.csv
```

已有旧版报告可以用补齐后的 `_position.csv` 更新顶部说明：

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python update_reports_with_positions.py \
  --signals outputs/runs/weekly_test/signals/signals_300269_2026-06-01_2026-06-30_weekly_position.csv
```

如果希望同一天重复实验不覆盖，推荐使用 `--run-name`：

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python collect_daily_signals.py \
  --ticker 300269 \
  --start 2026-06-30 \
  --end 2026-07-03 \
  --analysts market fundamentals news social \
  --quick-model deepseek-v4-flash \
  --deep-model deepseek-v4-pro \
  --run-name with_memory \
  --output-file outputs/runs/with_memory/signals/signals_300269_2026-06-30_2026-07-03.csv
```

对应产物会进入：

```text
outputs/runs/with_memory/signals/
outputs/runs/with_memory/reports/
outputs/runs/with_memory/trajectories/
outputs/runs/with_memory/audit_reports/
```

## 6. Reflection Memory

当前默认启用不依赖 embedding 的 markdown 记忆机制：

```bash
cat outputs/memory/decision_memory.md
```

运行逻辑：

```text
第1天生成信号 -> 写入 pending
第2天同股票运行 -> 用后续行情计算收益和 alpha -> 生成 reflection
第2天及之后 -> 将已完成 reflection 注入 Portfolio Manager
```

查看是否已经生成 reflection：

```bash
rg -n "^\[|^REFLECTION:|^DECISION:" outputs/memory/decision_memory.md
```

更推荐使用表格化检查工具：

```bash
PYTHONPATH="$(pwd)" /Users/bakii/miniforge3/envs/tradingagents-cn/bin/python inspect_memory_log.py \
  --ticker 300269 \
  --limit 10
```

## 7. 复盘时重点看什么

优先阅读：

- `outputs/reports/*.md`

需要机器可追溯时再看：

- `outputs/trajectories/*.json`
- `outputs/audit_reports/*.json`
