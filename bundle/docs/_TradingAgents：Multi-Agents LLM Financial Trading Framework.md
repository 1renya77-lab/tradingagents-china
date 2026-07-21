# TradingAgents：Multi\-Agents LLM Financial Trading Framework

### Agent设计：

### 1\.Fundamentals Analyst, 

### 2\.Sentiment （情绪）Analyst, equipped with tools like web search engines, Reddit search APIs, X/Twitter search tools, and sentiment score calculation algorithms

### 3\.News Analyst,

### 4\.Technical Analyst,  can execute code, calculate technical indicators, and analyze trading patterns

### 5\.Researcher, 

### 6\.Trader, 

### 7\.Risk Manager\. 

### Each agent is assigned a specific name, role, goal, and set of constraints, alongside predefined context, skills, and tools tailored to their function



![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MWNhMzJkYWViNGE3ODUxODI3YTU0ZTcxMTI3NGUxNzVfNTRiYzgyOGI5OWQzY2VlNTRmNDQ2NjJlMWEyZDU4YzNfSUQ6NzY1NDkxMjM3Njk3NDU3NjgyNl8xNzgzNDc2ODg2OjE3ODM1NjMyODZfVjM)

在代码里是这样，系统先把 analyst 生成的报告放进共享状态，比如：

```Plain Text
market_report
sentiment_report
news_report
fundamentals_report
```

Bullish Agent = LLM \+ 看涨角色 prompt \+ 当前共享状态

Bearish Agent = LLM \+ 看跌角色 prompt \+ 当前共享状态

然后调用 `Bull Researcher` 时，prompt ：

**你是一位看涨分析师，负责为股票建立强有力的论证。**

**你的任务是强调增长潜力、竞争优势、积极指标，并反驳看跌观点。**

工程上把一个**通用推理器**切成**两个立场视角**。这个设计的好处是便宜、可控、容易复现；弱点是正反方并不真正独立，容易受到同一个模型偏见



![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=ODllMTJkZjMxYWViYjFhOGNjNzJiMTZmZDc2ODYwMjRfZGZlZDc2ZWVkYzQ5OTc3NWNhNjc3OWY0NGQyNTc1ZjBfSUQ6NzY1NDkxMjQ1OTY1MTk3NjEyMV8xNzgzNDc2ODg2OjE3ODM1NjMyODZfVjM)



实验结论也应限制在证据边界内。回测窗口是 2024\-1\-1 到2024\-3\-29，资产主要是少数大型科技股，baseline 是 Buy and Hold 、MACD \(Moving Average Convergence Divergence\)，KDJ and RSI \(Relative Strength Index\)，SMA \(Simple Moving Average\)。



![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MjNhODQyZWM5OGNiNGQ1ZmI3YmYzYjE2MWQ1MzI2OTFfMTdhZjZhZTk1YTJlZWViMzA3MjJmNWI1Y2IxZmNhY2NfSUQ6NzY1NDkxMjUzNzM5Nzc0MjgwOF8xNzgzNDc2ODg2OjE3ODM1NjMyODZfVjM)



![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MjcwNDhmYWE3ZGNiZDc0ZDQ0NDBiMGZhYTMwMWNhMGFfOTkzM2E3NjM1OTc0YjE2ZjM3OTQzZTJjOTY4Mjk5YmRfSUQ6NzY1NDkxMjU4NjAzMjA1NzI3M18xNzgzNDc2ODg2OjE3ODM1NjMyODZfVjM)



实验：000001 平安银行 0625

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=YTA2OTY3Y2ZkZWRhZjI2MjQzZGU0MmQwM2Q5YzM3ZjNfMzg3OWI3YjczZjBhNGMwM2E1ZWQwNzUwNmM5MjU2MmJfSUQ6NzY1NTMxOTI4NjkzMTU1NzYyMV8xNzgzNDc2ODg2OjE3ODM1NjMyODZfVjM)

agent 把“普遍市场经验”说成了“我们自己的既往决策历史”，这属于不该有的伪记忆，不是严格的数据支持结论。

原因分析：prompt 设计 

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MTRjNTUzYTMyYmFhZWViZGIxYWE4NmE3Mzc5Y2VhYzNfMjcxMThlYWJkY2ZkYzkwZTBiMzQwZGRjZDJhMTEzNjhfSUQ6NzY1NTMyMDE2MDcyNzE1Nzc0MF8xNzgzNDc2ODg2OjE3ODM1NjMyODZfVjM)

这句话会直接诱导模型：

- 默认自己“有过往决策历史”

- 默认可以把“市场上常见案例”写成“我们曾经犯过的错”

- 即使memory里没有真实可核验记录，也会自己补 narrative

可审计性探究：

对于大模型获取的数据怎么核实其准确性

# 7\-2

目前完成的：

* [x] 复现tradingagents 在A股，输出交易信号

我们是在 TradingAgents 的基础上，做了一个面向 A 股市场的多智能体投研与交易信号生成版本。原版更偏通用股票分析和美股语境，我们的版本重点解决 A 股场景下 “能不能输入股票代码和日期，自动生成可复盘的 Buy/Hold/Sell 信号，并接入回测验证” 的问题。

## 主要工作

1. 搭建了 A 股单股单日信号生成链路
现在可以通过 脚本输入 A 股代码和日期，系统会基于 langgraph 调用多智能体完成市场、基本面、新闻、社交情绪分析，最后输出交易建议、置信度、目标价、风险得分和理由。

2. 搭建了日频批量信号采集链路
可以对某只股票在一段日期内逐日生成信号，输出 CSV，包括 date、ticker、action、confidence、risk\_score、target\_price、score、reasoning 等字段，搭建了 Qlib 回测闭环，我们新增了基于已有信号 CSV 的 Qlib 回测脚本可以把 TradingAgents 生成的信号转成交易行为，输出收益、回撤、夏普、交易记录和持仓记录。

3. 接入 DeepSeek 模型，并支持快慢模型分工
目前支持 deepseek\-v4\-flash 作为 quick thinking model，deepseek\-v4\-pro 作为 deep thinking model。这样可以让简单分析和结构化提取用较快模型，复杂推理和辩论环节用更强模型。

4. 对 prompt 做了 A 股本土化改造
原版里有做空、short、空头仓位等美股 / 通用市场表述。我们针对 A 股 long\-only 场景做了修改：禁止裸做空，卖出解释为减仓、止盈、止损或空仓观望；同时加入 T\+1、涨跌停、流动性、交易成本、政策事件、题材轮动等 A 股约束。

5. 处理了时间对齐和未来函数问题
回测中不是用当天信号买当天收盘，而是把 T 日信号顺延到 T\+1 执行，避免同日收盘价泄漏。同时在数据源和 Qlib provider 构建中考虑了交易日、回测结束日和日频执行区间的问题。

6. 改进了信号强度映射
原来只是 买入 = 1，持有 = 0\.5，卖出 = 0，信息损失比较大。我们现在把 confidence 和 risk\_score 纳入 score 计算，并在回测里让买入仓位随 score 连续变化，而不是一买入就固定 95% 仓位。

## 目前结果

这个项目现在还不能说已经证明了能稳定盈利，更准确地说是完成了从 “多智能体投研报告” 到 “A 股结构化交易信号” 再到 “Qlib 回测评估” 的完整实验框架。现在观察到的问题是模型偏保守，卖出 / 观望较多，买入较少，后续需要通过更多股票、更多日期和消融实验来验证多智能体结构是否真的优于单模型或简化流程。

## 后续计划

下一步我准备重点研究 agent 之间的信息传递机制：检查分析师报告、辩论、trader、风险团队之间是否存在信息失真、遗漏或幻觉；同时考虑引入 “结构化证据表 \+ 自然语言报告” 的双轨通信方式，让每个 agent 的判断都有可追踪证据，方便复盘和减少 hallucination，考虑加入记忆反馈机制。

复盘报告示例：

行情和技术指标：主要来自 AkShare 行情数据，

基本面： AkShare 与 BaoStock，

新闻：证券时报、证券时报网、央广财经等财经媒体，

情绪：主要基于新闻情绪，本次没有抓到有效的雪球/东方财富股吧社区讨论数据。

\[report\_300269\_2026\-06\-26\.md\]

\[report\_300269\_2026\-06\-29\.md\]

\[report\_300269\_2026\-06\-30\.md\]

\[report\_300269\_2026\-07\-01\.md\]

\[report\_300269\_2026\-07\-02\.md\]

\[report\_300269\_2026\-07\-03\.md\]

# 7\-3 

# **Reflection Memory 设计与实现**



为了让多智能体投研流程不只停留在“一次性生成报告”，加入了面向 A 股日频预测的 reflection memory 机制。设计目标是把每天的交易信号与后续市场结果绑定起来，使系统能够根据过去决策的实际表现进行复盘，并将经过验证的经验反馈给后续决策。



具体流程是：



第 t 日生成信号

→ 写入 pending 决策日志

→ 第 t\+1 日获取后续行情

→ 计算收益和 alpha

→ 生成短 reflection

→ 注入下一次 Portfolio Manager



针对 A 股交易场景做了几个约束：

- 用后续行情验证前一日信号，而不是只保存模型输出。

- 用相对SH000905 的 alpha 衡量判断质量，避免只看绝对涨跌。

- 将 reflection 限制为 2\-4 句，避免 prompt 随运行次数无限膨胀。

- 只注入 Portfolio Manager，而不是让所有 Agent 读取历史文本，减少噪声传播。

因此，该模块把原有多智能体流程扩展成了一个轻量的“决策\-验证\-复盘\-再决策”闭环。当前它主要提升的是系统的可复盘性和经验积累能力，后续还需要通过固定股票池和日期区间做消融实验，对比启用 memory 前后的信号分布、alpha 表现和报告质量。

模型涨跌的分布，和倾向卖出的原因，预测准确率，qlib回测，通达信

# 7\-6

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=OTUxN2QwYzU2NTBhMWNlNjEwZTZlY2I5ZDM5ZTcyYTdfMTU3Y2M5NDhlN2VmYzc1MWFiNTUwYTg3Y2E1NWMwNWZfSUQ6NzY1OTM0MjY5NjkwOTI5NDU3MF8xNzgzNDc2ODg2OjE3ODM1NjMyODZfVjM)

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=NWIxNjcyYzYzZmQ3MTY2YmE1NzU3YTI0MjQ0ZjQ1OGJfOTVlMWUxZTM5MjIwZmE5MTNmMmM4MGRiYzUyYzg4MzZfSUQ6NzY1OTM0Mjc5NjAwMDM5ODI2N18xNzgzNDc2ODg2OjE3ODM1NjMyODZfVjM)

\[comparison\_300308\_2026\-04\-01\_2026\-06\-30\.md\]

\[comparison\_300750\_2026\-04\-01\_2026\-06\-30\.md\]

\[comparison\_601138\_2026\-04\-01\_2026\-06\-30\.md\]



\[comparison\_601899\_2026\-04\-01\_2026\-06\-30\.md\]

\[comparison\_300308\_2025\-07\-01\_2026\-06\-30\.md\]

结果整理成一个总表 精简完整过程。

AGENT运行时间  和 中间文档 搭一个网站展示。亏额较大和涨额较大的case的报告。大盘跌 agent选空仓，踏空 盈亏比，统计一下。

\[decision\_attribution\_300308\_2025\-07\-01\_2026\-06\-30\.md\]

