# TradingAgents Agent 信息流转

## 一、架构总览

基于 LangGraph StateGraph 的多 Agent 量化研究系统，4 类角色通过共享状态传递信息。

| 组件 | 说明 |
|:---|:---|
| Analysts | 4 个串行 ReAct Agent，负责市场/基本面/新闻/情绪数据采集 |
| Researchers | Bull/Bear 多空辩论，Research Manager 出投资决策 |
| Trader | 基于辩论结果生成交易计划 |
| Risk Team | Risky/Safe/Neutral 三方风险辩论，Risk Judge 出最终裁决 |

## 二、信息流转图

```
START
  │
  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 第一阶段：分析师串行                                                          │
│                                                                             │
│  Market Analyst ──→ Fundamentals Analyst ──→ News Analyst ──→ Social Analyst │
│       │                      │                    │                │        │
│    ToolNode              ToolNode             ToolNode            ToolNode   │
│       │                      │                    │                │        │
│  market_report      fundamentals_report      news_report      sentiment_report│
│                                                                             │
│  分析师顺序由 --analysts 参数决定                                              │
│  每个分析师是 ReAct Loop：LLM 思考 → 调用工具 → 生成报告                       │
└─────────────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 第二阶段：投资辩论（多空辩论）                                                  │
│                                                                             │
│      Bull Researcher  ←──→  Bear Researcher                                  │
│           │                    │                                            │
│      读取: analyst reports  读取: analyst reports                            │
│      + bull_history         + bear_history                                  │
│           │                    │                                            │
│      写入: bull_history    写入: bear_history                              │
│                                                                             │
│  轮次: 2 × max_debate_rounds 后 → Research Manager                         │
│  Research Manager 使用 deep_think_llm                                        │
│  输出: judge_decision（买入 / 持有 / 卖出）                                  │
└─────────────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 第三阶段：Trader                                                             │
│                                                                             │
│  Trader（quick_think_llm）                                                   │
│    读取: analyst reports（全部 4 个）+ investment_debate_state              │
│    写入: trader_investment_plan                                            │
└─────────────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 第四阶段：风险辩论（三方辩论）                                                 │
│                                                                             │
│      Risky Analyst ──→ Safe Analyst ──→ Neutral Analyst                   │
│           │                │                │                               │
│      读取:              读取:            读取:                             │
│      analyst reports    analyst reports  analyst reports                    │
│      + risky_history    + safe_history   + neutral_history                 │
│           │                │                │                               │
│      写入:              写入:            写入:                            │
│      risky_history      safe_history      neutral_history                   │
│                                                                             │
│  轮次: 3 × max_risk_discuss_rounds 后 → Risk Judge                       │
│  Risk Judge 使用 deep_think_llm                                             │
│  输出: judge_decision（最终风险裁决）                                         │
└─────────────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 最终输出                                                                     │
│                                                                             │
│  final_trade_decision（Risk Judge 原始文本）                                 │
│       ↓                                                                    │
│  SignalProcessor.process_signal()                                           │
│       ↓                                                                    │
│  { action, confidence, target_price, risk_score, reasoning }                │
│       ↓                                                                    │
│  signal_positioning.derive_target_position()                                │
│       ↓                                                                    │
│  { ..., target_position }                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 三、LangGraph State 结构

### 分析师报告字段

| 字段 | 说明 |
|:---|:---|
| `market_report` | 市场技术分析报告（MA、MACD、RSI、布林带等） |
| `fundamentals_report` | 基本面分析报告（ROE、负债率、PE/PB 等） |
| `news_report` | 新闻事件分析报告 |
| `sentiment_report` | 社交媒体情绪分析报告 |

### 投资辩论状态

| 字段 | 说明 |
|:---|:---|
| `bull_history` | 多头研究员发言历史 |
| `bear_history` | 空头研究员发言历史 |
| `history` | 完整辩论历史 |
| `current_response` | 当前发言者标识 |
| `judge_decision` | Research Manager 裁决结果 |
| `count` | 当前辩论轮次计数 |

### 风险辩论状态

| 字段 | 说明 |
|:---|:---|
| `risky_history` | 激进风险分析师发言历史 |
| `safe_history` | 保守风险分析师发言历史 |
| `neutral_history` | 中性风险分析师发言历史 |
| `history` | 完整辩论历史 |
| `latest_speaker` | 最后发言的分析师 |
| `judge_decision` | Risk Judge 最终裁决 |
| `count` | 当前辩论轮次计数 |

### 其他字段

| 字段 | 说明 |
|:---|:---|
| `messages` | 分析师 ReAct 对话历史 |
| `company_of_interest` | 股票代码 |
| `trade_date` | 交易日期 |
| `trader_investment_plan` | Trader 生成的交易计划 |
| `final_trade_decision` | 最终交易决策（Risk Judge 原始输出） |

### 最终信号字段

| 字段 | 说明 |
|:---|:---|
| `action` | LLM 原始离散判断：买入/持有/卖出 |
| `confidence` | 决策置信度 |
| `target_price` | 目标价 |
| `risk_score` | 风险得分 |
| `reasoning` | 最终摘要 |
| `target_position` | 可执行目标仓位，Qlib 回测优先使用 |

注意：`action=持有` 不等价于“不交易”。如果最终文本写“持有40%-50%仓位”，系统会解析为约 `target_position=0.45`，回测按该目标仓位在下一交易日调仓。

## 四、轮次控制

### 投资辩论

```
条件函数: should_continue_debate()
最大轮次: 2 × max_debate_rounds

Bull 发言 → count+1
Bear 发言 → count+1
达到上限 → 进入 Research Manager
```

### 风险辩论

```
条件函数: should_continue_risk_analysis()
最大轮次: 3 × max_risk_discuss_rounds

三角循环: Risky → Safe → Neutral → Risky → ...
每次发言 count+1，达到上限后进入 Risk Judge
```

### 配置建议

| 场景 | max_debate_rounds | max_risk_discuss_rounds |
|:---|:---:|:---:|
| 快速测试 | 1 | 1 |
| 标准回测 | 1 | 1 |
| 深度分析 | 2 | 2 |

## 五、模型分工

| 模型类型 | 使用 Agent | 推荐模型 |
|:---|:---|:---|
| quick_think_llm | 4 个分析师 + Bull/Bear + Risky/Safe/Neutral + Trader | `deepseek-v4-flash` |
| deep_think_llm | Research Manager + Risk Judge | `deepseek-v4-pro` |

## 六、输出产物

| 产物 | 文件路径 |
|:---|:---|
| 复盘报告 | `outputs/reports/report_{ticker}_{date}.md` |
| 审计报告 | `outputs/audit_reports/audit_{ticker}_{date}.json` |
| 轨迹数据 | `outputs/trajectories/trajectory_{ticker}_{date}.json` |
| 信号结果 | `outputs/signals/signal_{ticker}_{date}_{ts}.json` |

复盘报告顶部会显示“原始操作”和“执行目标仓位”。正文中的多 agent 辩论保留原始过程；与回测交易严格对应的是 `target_position`。
