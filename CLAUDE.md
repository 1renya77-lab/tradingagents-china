# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

```bash
# Recommended conda environment
conda activate tradingagents  # or tradingagents-cn

# Or use the interpreter directly
/Users/bakii/miniforge3/envs/tradingagents-cn/bin/python
```

Set API key before running:
```bash
export DEEPSEEK_API_KEY="sk-..."
```

## Common Commands

```bash
cd "/Users/bakii/tradingagents 汇报/tradingagents_bundle"
export DEEPSEEK_API_KEY="sk-..."

# Single-day signal generation (4-analyst full version)
PYTHONPATH="$(pwd)" python run_signal.py \
  --ticker 300269 \
  --date 2026-06-30 \
  --analysts market fundamentals news social \
  --max-debate-rounds 1 \
  --max-risk-rounds 1 \
  --provider deepseek \
  --model deepseek-v4-flash

# Quick 2-analyst test
PYTHONPATH="$(pwd)" python run_signal.py \
  --ticker 600036 \
  --date 2026-06-30 \
  --analysts market fundamentals

# Batch daily signals
PYTHONPATH="$(pwd)" python collect_daily_signals.py \
  --ticker 600036 \
  --start 2026-06-01 \
  --end 2026-06-30 \
  --frequency daily \
  --analysts market fundamentals news social \
  --provider deepseek \
  --model deepseek-v4-flash

# Batch weekly signals
PYTHONPATH="$(pwd)" python collect_daily_signals.py \
  --ticker 300269 \
  --start 2026-06-01 \
  --end 2026-06-30 \
  --frequency weekly \
  --analysts market fundamentals news social \
  --provider deepseek \
  --model deepseek-v4-flash

# Qlib backtest
PYTHONPATH="$(pwd)" python backtest_existing_signals_qlib.py \
  --signals outputs/signals/signals_600036_2026-06-01_2026-06-30_daily.csv \
  --ticker 600036 \
  --start 2026-06-01 \
  --end 2026-06-30 \
  --provider-uri data/qlib_cn_test \
  --output-dir outputs/backtests/qlib
```

## Architecture

### Agent Graph (LangGraph)

The system is a LangGraph `StateGraph` orchestrated by `TradingAgentsGraph` in `tradingagents/graph/trading_graph.py`.

**Node flow (sequential phases):**

1. **Analysts phase** — selected analysts run in sequence (market → fundamentals → news → social):
   - Each analyst is a ReAct agent that calls tools via `ToolNode` → produces a report stored in state
   - Loop control: `ConditionalLogic.should_continue_{analyst}` checks for tool calls vs. finished report
   - Tool nodes: `tradingagents/tools/` — unified data access (Chinese market data via akshare/tushare/baostock, news, sentiment)

2. **Investment debate phase** — after all analysts complete:
   - `Bull Researcher` ↔ `Bear Researcher` — `max_debate_rounds` cycles
   - `ConditionalLogic.should_continue_debate` alternates speakers, ends at `2 * max_debate_rounds` turns
   - `Research Manager` (deep thinking) → produces investment judgment

3. **Risk debate phase**:
   - `Risky Analyst` → `Safe Analyst` → `Neutral Analyst` — cycle 3× per round
   - `ConditionalLogic.should_continue_risk_analysis` controls cycling, ends at `3 * max_risk_discuss_rounds`
   - `Risk Judge` (deep thinking) → final risk assessment

4. **Trader** — receives analyst reports + debate outputs → generates final trading signal

**Key files:**
- `tradingagents/graph/trading_graph.py` — `TradingAgentsGraph` class, `propagate()`, report saving
- `tradingagents/graph/setup.py` — `GraphSetup.build_graph()` assembles all nodes and edges
- `tradingagents/graph/conditional_logic.py` — `ConditionalLogic` controls all routing decisions
- `tradingagents/graph/signal_processing.py` — parses LLM text output into structured `{action, confidence, target_price, risk_score}`

### Agent Types

| Agent | File | Role |
|-------|------|------|
| Market Analyst | `agents/analysts/market_analyst.py` | Technical indicators, price trends |
| Fundamentals Analyst | `agents/analysts/fundamentals_analyst.py` | Financial metrics, valuation |
| News Analyst | `agents/analysts/news_analyst.py` | News events, market news |
| Social Media Analyst | `agents/analysts/social_media_analyst.py` | Investor sentiment from social platforms |
| Bull/Bear Researcher | `agents/researchers/bull_researcher.py`, `bear_researcher.py` | bull/bear investment arguments |
| Research Manager | `agents/managers/research_manager.py` | Deep-thinking judge → investment decision |
| Trader | `agents/trader/trader.py` | Final signal generation |
| Risky/Safe/Neutral Analyst | `agents/risk_mgmt/` | Risk perspective debate |
| Risk Manager | `agents/managers/risk_manager.py` | Deep-thinking risk judge |

### Data Layer

`tradingagents/dataflows/` — unified data interface for Chinese A-shares:
- `china_akshare.py`, `china_tushare.py`, `baostock_provider.py` — data providers
- `interface.py` — `set_config()` + data entry point used by toolkit
- `optimized_china_data.py` — main unified data service
- `config.py` — data source configuration

### Toolkit (Tool Binding)

`tradingagents/agents/utils/agent_utils.py` — `Toolkit` class exposes all tools as methods (e.g., `get_stock_market_data_unified`, `get_stock_fundamentals_unified`). Each analyst gets a `Toolkit` instance. Tools are wired to `ToolNode` in `trading_graph.py`.

### Output Artifacts

All outputs under `outputs/`:
- `signals/` — JSON signal results + batch CSV
- `reports/` — Markdown readable review reports (generated by `_save_markdown_report()`)
- `trajectories/` — JSON process traces for GRPO training
- `audit_reports/` — complete JSON audit with all reports and debates
- `backtests/qlib/`, `backtests/simple/`, `backtests/baostock/` — backtest results
