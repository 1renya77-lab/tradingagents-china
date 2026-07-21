import functools
import time
import json

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
from tradingagents.agents.utils.instrument_utils import build_instrument_context
logger = get_logger("default")


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name)
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        horizon_instruction = state.get(
            "horizon_instruction",
            "本次信号是日频信号，请判断下一交易日的可执行操作。",
        )

        # 使用统一的股票类型检测
        from tradingagents.utils.stock_utils import StockUtils
        market_info = StockUtils.get_market_info(company_name)
        is_china = market_info['is_china']
        is_hk = market_info['is_hk']
        is_us = market_info['is_us']

        # 根据股票类型确定货币单位
        currency = market_info['currency_name']
        currency_symbol = market_info['currency_symbol']

        logger.debug(f"💰 [DEBUG] ===== 交易员节点开始 =====")
        logger.debug(f"💰 [DEBUG] 交易员检测股票类型: {company_name} -> {market_info['market_name']}, 货币: {currency}")
        logger.debug(f"💰 [DEBUG] 货币符号: {currency_symbol}")
        logger.debug(f"💰 [DEBUG] 市场详情: 中国A股={is_china}, 港股={is_hk}, 美股={is_us}")
        logger.debug(f"💰 [DEBUG] 基本面报告长度: {len(fundamentals_report)}")
        logger.debug(f"💰 [DEBUG] 基本面报告前200字符: {fundamentals_report[:200]}...")

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # 检查memory是否可用
        if memory is not None:
            logger.warning(f"⚠️ [DEBUG] memory可用，获取历史记忆")
            past_memories = memory.get_memories(curr_situation, n_matches=2)
            past_memory_str = ""
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            logger.warning(f"⚠️ [DEBUG] memory为None，跳过历史记忆检索")
            past_memories = []
            past_memory_str = "暂无历史记忆数据可参考。"

        context = {
            "role": "user",
            "content": f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for {company_name}. This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. Use this plan as a foundation for evaluating your next trading decision.\n\nProposed Investment Plan: {investment_plan}\n\nLeverage these insights to make an informed and strategic decision.",
        }

        messages = [
            {
                "role": "system",
                "content": f"""您是一位证据驱动的A股交易执行建议官。您的目标不是强行交易，而是根据投研报告中的依据强弱，给出可执行、可复核、符合A股交易约束的操作建议。

⚠️ 重要提醒：当前分析的股票代码是 {company_name}，请使用正确的货币单位：{currency}（{currency_symbol}）
{instrument_context}

🔴 严格要求：
- 股票代码 {company_name} 的公司名称必须严格按照基本面报告中的真实数据
- 绝对禁止使用错误的公司名称或混淆不同的股票
- 所有分析必须基于提供的真实数据，不允许假设或编造
- 如依据不足以支持精确目标价，可以给出合理价格区间、关键支撑/压力位或说明目标价可信度较低，但不能编造不存在的数据

请在您的分析中包含以下关键信息：
1. **投资建议**: 买入 / 持有 / 卖出。若当前更适合等待，请在持有建议中明确写出“观望/等待更好买点”
2. **依据强度**: 强 / 中 / 弱，并说明哪些证据支持、哪些证据冲突
3. **决策周期**: 必须明确写出本次建议适用的时间范围。{horizon_instruction}
   - 如果是周频信号，请判断未来5个交易日或直到下一次周频再平衡前是否应该买入、持有或卖出
   - 不要把周频信号写成只预测明天单日涨跌
4. **目标价位或价格区间**: 基于分析的合理目标价格或区间({currency})
   - 买入建议：提供目标价位和预期涨幅
   - 持有/观望建议：提供等待的价格区间、突破条件或回调条件
   - 卖出建议：提供止损价位、减仓条件或风险触发条件
5. **建议仓位**: 不参与 / 轻仓 / 中性仓位 / 较高仓位，并说明理由
6. **置信度**: 对决策的信心程度(0-1之间)
7. **风险评分**: 投资风险等级(0-1之间，0为低风险，1为高风险)
8. **详细推理**: 支持决策的具体理由，必须引用市场、基本面、新闻或情绪报告中的关键依据

🎯 目标价位计算指导：
- 基于基本面分析中的估值数据（P/E、P/B、DCF等）
- 参考技术分析的支撑位和阻力位
- 考虑行业平均估值水平
- 结合市场情绪和新闻影响
- 即使市场情绪过热，也要基于合理估值给出目标价

特别注意：
- 如果是中国A股（6位数字代码），请使用人民币（¥）作为价格单位
- 如果是中国A股，"卖出"只能表示卖出已有持仓、减仓、止损或空仓等待，绝对不能解释为裸卖空、做空或建立空头仓位
- 如果是美股或港股，请使用美元（$）作为价格单位
- 目标价位必须与当前股价的货币单位保持一致
- 必须使用基本面报告中提供的正确公司名称

请用中文撰写分析内容，并始终以'最终交易建议: **买入/持有/卖出**'结束您的回应以确认您的建议。

请不要忘记利用过去决策的经验教训来避免重复错误。以下是类似情况下的交易反思和经验教训: {past_memory_str}""",
            },
            context,
        ]

        logger.debug(f"💰 [DEBUG] 准备调用LLM，系统提示包含货币: {currency}")
        logger.debug(f"💰 [DEBUG] 系统提示中的关键部分: 目标价格({currency})")

        result = llm.invoke(messages)

        logger.debug(f"💰 [DEBUG] LLM调用完成")
        logger.debug(f"💰 [DEBUG] 交易员回复长度: {len(result.content)}")
        logger.debug(f"💰 [DEBUG] 交易员回复前500字符: {result.content[:500]}...")
        logger.debug(f"💰 [DEBUG] ===== 交易员节点结束 =====")

        return {
            "messages": [result],
            "trader_investment_plan": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
