# TradingAgents-Bundle 落地化项目方案

## 1. 项目定位

`tradingagents_bundle` 的目标不是做一个“LLM 写股票报告”的 demo，而是构建一个面向 A 股单股日频预测的多智能体投研原型系统。系统应当覆盖数据获取、Agent 分工分析、交易信号生成、过程审计、结果复盘和回测验证，形成可运行、可追溯、可评估的闭环。

一句话定位：

```text
面向 A 股市场的多智能体投研与交易信号生成系统，支持单股日频预测、reflection 复盘记忆和 Qlib 回测验证。
```

## 2. 当前已经完成的能力

| 模块 | 当前状态 | 说明 |
|:---|:---|:---|
| 单日信号 | 已完成 | `run_signal.py` 支持单股单日 Buy/Hold/Sell 类信号 |
| 批量日频信号 | 已完成 | `collect_daily_signals.py` 支持日期区间批量运行 |
| A 股 Agent prompt | 已完成初版 | 已从美股/做空语境改成更贴近 A 股投研口径 |
| 数据质量门控 | 已完成初版 | 对空数据、数据截止日期、数据源进行显式提示 |
| Reflection memory | 已完成初版 | 使用 markdown decision log，不依赖 embedding |
| 输出归档 | 已完成初版 | 支持 `--run-name` 将信号、报告、轨迹、审计隔离到 `outputs/runs/{run-name}/` |
| 信号评估汇总 | 已完成初版 | `evaluate_signals.py` 输出 forward return、alpha、decision alpha 和方向命中率 |
| 固定实验配置 | 已完成初版 | `run_experiment.py` 支持 JSON 配置驱动实验并输出 manifest |
| Qlib 回测 | 已完成初版 | 支持已有信号 CSV 的 long/cash 回测 |
| 过程审计 | 已完成初版 | 生成 trajectory 和 audit report |

## 3. 为什么目前容易被认为 toy

当前系统能跑通，但还缺少证明“它是一个落地项目”的三类证据：

1. 缺少固定实验协议。  
   现在更多是跑若干 case，还没有固定股票池、固定日期区间、固定 baseline 和统一指标。

2. 缺少可量化评估。  
   报告质量、信号分布、收益、alpha、最大回撤、交易次数等指标还没有汇总成一张结果表。

3. 缺少信息链路审计。  
   多智能体框架已经存在，但还需要证明分析师证据如何传递到 Trader 和 Portfolio Manager，中间有没有失真、幻觉或过度保守。

因此下一阶段重点不是继续堆 Agent，而是把系统做成“可复现、可对比、可审计”的实验项目。

## 4. 落地化验收标准

一个更完整的落地版本至少应满足以下标准：

| 验收项 | 标准 |
|:---|:---|
| 可运行 | 新环境下按文档配置 `.env` 后，可以跑单日和批量信号 |
| 可复现 | 固定股票池、日期区间、模型配置和输出路径 |
| 可追溯 | 每次信号有报告、轨迹、audit、memory 记录 |
| 可评估 | 至少输出信号统计、收益统计、alpha、最大回撤、交易次数 |
| 可对比 | 有 baseline，例如 without memory、with memory、单 LLM |
| 可解释 | 能展示某个 case 中证据如何从分析师传到最终决策 |
| 安全合规 | API key 只放 `.env`，不写入代码、配置、报告或提交文件 |

## 5. 推荐实验协议

### 5.1 固定样本

先不要一上来跑全市场，建议采用小规模但可解释的股票池：

```text
300269 联建光电：高波动小盘/题材案例
600036 招商银行：大盘金融蓝筹
000001 平安银行：金融蓝筹对照
688525 佰维存储：科创成长/半导体
603986 兆易创新：半导体龙头
```

时间区间建议先用 5-20 个交易日，保证能跑完、能人工复盘。

### 5.2 对照实验

至少做三组：

| 组别 | 目的 |
|:---|:---|
| Baseline: no memory | 看原始多智能体信号表现 |
| With reflection memory | 验证复盘记忆是否改变信号 |
| Ablation: market only 或 no news/social | 验证不同分析师模块贡献 |

### 5.3 指标

信号层指标：

- Buy/Hold/Sell 分布
- 平均 confidence
- 平均 risk_score
- 平均 score
- 信号变化率

交易层指标：

- 累计收益
- 相对基准 alpha
- action-aware decision alpha
- 方向命中率
- 最大回撤
- 交易次数
- 胜率
- 平均持仓天数

报告层指标：

- 是否引用有效数据源
- 是否出现数据为空却强行推断
- 是否符合 A 股约束
- 是否能解释最终信号

## 6. 下一步代码任务

优先级从高到低：

1. 扩展实验汇总脚本。  
   当前 `evaluate_signals.py` 已支持单个或多个 signal CSV 的收益、alpha 和方向命中率汇总；下一步可扩展到多实验组自动对比。

2. 增强 memory inspection 脚本。  
   当前 `inspect_memory_log.py` 已支持表格化查看 pending/resolved、收益、alpha 和 reflection；下一步可输出为 CSV 方便汇报。

3. 扩展报告归档参数。  
   当前 `--run-name` 已支持实验级产物隔离；下一步可增加自动时间戳 run name 和实验 manifest。

4. 扩展固定实验配置。  
   当前 `run_experiment.py` 已支持 JSON 描述股票池、日期、模型、评估和 run_name；下一步可扩展为多实验组对比，例如 `without_memory` vs `with_memory`。

5. 增加 case audit 文档。  
   选一个股票日期，追踪四个分析师报告、Bull/Bear、Trader、Risk/Portfolio Manager 的证据传递。

## 7. 导师汇报口径

可以这样解释项目下一阶段：

```text
目前系统已经从原始 TradingAgents 改成了一个 A 股单股日频预测原型，具备数据获取、多智能体分析、交易信号、reflection 复盘和 Qlib 回测链路。但我也认为它现在还偏工程原型，所以后续重点不是继续增加 Agent，而是做落地化验证：固定股票池和时间窗，建立 without memory / with memory / ablation 的对照实验，并用信号分布、收益、alpha、回撤和 case 审计来证明多智能体结构是否真的带来增益。
```

## 8. 当前结论

当前版本已经不是纯 demo，因为它有完整运行链路和真实输出文件；但要成为“完整落地项目”，还需要补齐实验协议、结果汇总、可复现配置和 case-level 信息链路审计。下一阶段的核心目标是把“能跑”推进到“能证明、能复盘、能比较”。
