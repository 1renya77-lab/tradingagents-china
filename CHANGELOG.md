# tradingagents_bundle 改动文档

基于原版 TradingAgents-Main 打包，包含信号生成 + Qlib 回测。

> **2026-06-30 修复**：原 bundle 漏掉了 `tradingagents/utils/`（含 logging_init、stock_utils 等模块），现已补上。
> **2026-06-30 修复**：补全 `tradingagents/config/`、`tradingagents/constants/`、`tradingagents/models/`、`tradingagents/tools/`、`tradingagents/llm_adapters/`、`tradingagents/api/`（全部来自 CN 版本）。
> **2026-07-05 修复**：批量信号与报告新增 `target_position` 执行口径。Qlib 回测优先按目标仓位调仓，解决 `action=持有` 被旧阈值回测解释成“不建仓”的问题。
> **2026-07-05 口径收敛**：新生成的批量信号默认输出 `_position.csv`，例如 `_weekly_position.csv`；普通 `_weekly.csv` 不再作为新实验默认产物。
> **2026-07-05 性能优化**：新增 A 股行情预取缓存。长周期实验可先预取完整行情，agent 调用时按信号日强制切片，避免重复拉取且不暴露未来数据。
> **2026-07-05 稳定性优化**：`collect_daily_signals.py` 新增 `--resume`，每个日期完成后立即保存，断网后可跳过已有成功信号继续跑。

---

## 1. 新增文件

| 文件 | 说明 |
|------|------|
| `run_signal.py` | 单股信号生成脚本，支持自定义股票/日期/分析师/辩论轮数 |
| `collect_daily_signals.py` | 批量采集一个日期范围内每日信号（工作日），输出 CSV |
| `backtest_existing_signals_qlib.py` | Qlib 标准回测（从 backtest_project 引入） |
| `build_minimal_qlib_provider.py` | 用 baostock 构建 Qlib 数据（从 backtest_project 引入） |
| `simple_backtest.py` | 简单回测，不依赖 Qlib（从 backtest_project 引入） |
| `run_baostock_backtest.py` | Baostock 价格回测（从 backtest_project 引入） |
| `signal_positioning.py` | 从最终决策文本中解析目标仓位 |
| `add_target_positions_to_signals.py` | 给已有 signals CSV 离线补齐 `target_position` |
| `update_reports_with_positions.py` | 给已有 Markdown 报告补齐执行目标仓位说明 |
| `prefetch_market_data.py` | 预取 A 股行情到本地缓存，后续按信号日无泄漏切片 |
| `tradingagents/dataflows/local_prefetch_cache.py` | 本地预取缓存读写与日期截断 |

---

## 2. 原文件改动

### signal_generator.py
- **改动前**：硬编码路径 `sys.path.insert(0, "/gpudata/coding/malong/Tradingagents/TradingAgents-CN")`
- **改动后**：使用相对路径 `sys.path.insert(0, str(Path(__file__).parent))`

### collect_daily_signals.py
- **改动前**：依赖 CN 版本的 `.env`、硬编码 CN 路径、`load_dotenv`
- **改动后**：直接读取 `.env` / 环境变量，使用 bundle 相对路径；批量 CSV 新增 `target_position`，默认文件名带 `_position.csv`
- **断点续跑**：支持 `--resume`，已有 `status=ok` 的日期不会重复调用 LLM

### backtest_existing_signals_qlib.py
- **改动前**：只按 `score` 阈值交易，`score=0.5` 的“持有”不会触发建仓
- **改动后**：若信号 CSV 含 `target_position`，优先按目标仓位调仓；没有该列时才退回旧版 `score` 阈值规则

### tradingagents/graph/trading_graph.py
- Markdown 报告顶部新增“原始操作 / 执行目标仓位 / 回测执行口径”
- trajectory 与 audit report 中的 `final_decision.parsed_decision` 会保留 `target_position`

---

## 3. 核心包（tradingagents/）无改动

```
tradingagents/
├── graph/          ← TradingAgentsGraph 主入口
├── agents/         ← market/fundamentals/news/social 分析师
├── dataflows/      ← BaoStock/AKShare 数据源
└── llm_clients/    ← DeepSeek 支持（factory.py 已内置）
```

---

## 4. 未包含的内容

- `china_market_analyst.py` 已复制到 Main 但**未注册到 graph**，暂不可用
- CN 版本的 `.env` 配置（MongoDB/Tushare 等）未包含
- 必须设置 `DEEPSEEK_API_KEY` 环境变量

---

## 5. 调用关系

```
run_signal.py / collect_daily_signals.py
    ↓ (相对路径 import)
tradingagents/
    ├── graph/trading_graph.py       ← TradingAgentsGraph
    ├── dataflows/                   ← BaoStock/AKShare 数据
    ├── llm_clients/                 ← DeepSeek API
    └── agents/                      ← market/fundamentals/news/social 分析师
```

---

## 6. 可选分析师（已注册到 graph）

| key | 分析师 |
|-----|--------|
| `market` | 市场技术分析师 |
| `fundamentals` | 基本面分析师 |
| `news` | 新闻事件分析师 |
| `social` | 社交媒体分析师 |

---

## 7. 快速使用

```bash
# 设置 API Key
export DEEPSEEK_API_KEY="sk-..."

# 单股单日信号
python run_signal.py --ticker 000001 --date 2025-07-04

# 批量采集信号
python collect_daily_signals.py --ticker 000001 --start 2025-07-01 --end 2025-07-31

# 构建 Qlib 数据
python build_minimal_qlib_provider.py --ticker 000001 --start 2025-07-01 --end 2025-07-31 --provider-uri data/qlib_cn

# Qlib 回测
python backtest_existing_signals_qlib.py --signals results/signals.csv --ticker 000001 --start 2025-07-01 --end 2025-07-31 --provider-uri data/qlib_cn --output-dir results/
```

## 8. 当前信号执行口径

新版本不是只看 `买入/持有/卖出`，而是使用：

```text
action + reasoning -> target_position -> Qlib 调仓
```

示例：

| 文本 | target_position | 含义 |
|------|---:|------|
| 持有40%-50%仓位 | 0.45 | 调整到约45%仓位 |
| 减持至30%以下 | 0.30 | 降到30%仓位 |
| 试探建仓5%-8% | 0.065 | 建立小底仓 |

后续新生成的 `signals.csv` 和 `report_*.md` 都会自动带这个目标仓位口径。旧结果可用 `add_target_positions_to_signals.py` 和 `update_reports_with_positions.py` 离线补齐，不需要重新调用 LLM。
