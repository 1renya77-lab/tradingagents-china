import time
import json

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
from tradingagents.agents.utils.instrument_utils import build_instrument_context
logger = get_logger("default")


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        history = state["investment_debate_state"].get("history", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        horizon_instruction = state.get(
            "horizon_instruction",
            "本次信号是日频信号，请判断下一交易日的可执行操作。",
        )

        investment_debate_state = state["investment_debate_state"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # 安全检查：确保memory不为None
        if memory is not None:
            past_memories = memory.get_memories(curr_situation, n_matches=2)
        else:
            logger.warning(f"⚠️ [DEBUG] memory为None，跳过历史记忆检索")
            past_memories = []

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        if past_memory_str.strip():
            memory_guidance = f"""历史参考约束：
- 以下历史反思仅可作为检索到的历史案例/历史记录来引用，不要写成“我们亲身犯过这些错误”，除非记录中明确提供了这种一手信息。
- 如果引用历史经验，请明确表述为“历史案例表明”“过往记录显示”“类似情形中常见的问题是”，不要伪造团队、账户或个人的真实经历。

以下是可参考的历史反思：
\"{past_memory_str}\""""
        else:
            memory_guidance = """历史参考约束：
- 当前没有可用的历史记忆记录。
- 在这种情况下，禁止写“我们过去犯过错”“我们曾多次误判”“我们吃过亏”等带有伪记忆色彩的表述。
- 如需类比，只能写成“历史案例表明”“市场上类似标的常见的问题是”“同类银行股常见的估值陷阱是”。"""

        prompt = f"""作为投资组合经理和辩论主持人，您的职责是批判性地评估这轮辩论并做出明确决策：支持看跌分析师、看涨分析师，或者仅在基于所提出论点有强有力理由时选择持有。

简洁地总结双方的关键观点，重点关注最有说服力的证据或推理。您的建议——买入、卖出或持有——必须明确且可操作。避免仅仅因为双方都有有效观点就默认选择持有；要基于辩论中最强有力的论点做出承诺。

此外，为交易员制定详细的投资计划。这应该包括：

您的建议：基于最有说服力论点的明确立场。
理由：解释为什么这些论点导致您的结论。
战略行动：实施建议的具体步骤。
⏱️ 决策周期约束：{horizon_instruction}
请确保最终投资计划的买入/持有/卖出建议服务于上述周期。如果是周频信号，请把结论落到未来5个交易日或直到下一次周频再平衡前的持仓判断，而不是明天单日涨跌判断。
📊 目标价格分析：基于所有可用报告（基本面、新闻、情绪），提供全面的目标价格区间和具体价格目标。考虑：
- 基本面报告中的基本估值
- 新闻对价格预期的影响
- 情绪驱动的价格调整
- 技术支撑/阻力位
- 风险调整价格情景（保守、基准、乐观）
- 价格目标的时间范围必须与本次决策周期一致；如需补充1个月、3个月、6个月视角，请明确区分为中长期背景，不得替代本次交易周期判断
💰 您必须提供具体的目标价格 - 不要回复"无法确定"或"需要更多信息"。

如果存在明确的历史记录，可以将其作为外部历史案例来参考；如果不存在，则只能基于当前报告和一般市场经验推理，绝不能虚构“我们过去的错误”或“我们的真实交易经历”。以对话方式呈现您的分析，就像自然说话一样，不使用特殊格式。

{memory_guidance}

标的约束：
{instrument_context}

以下是综合分析报告：
市场研究：{market_research_report}

情绪分析：{sentiment_report}

新闻分析：{news_report}

基本面分析：{fundamentals_report}

以下是辩论：
辩论历史：
{history}

请用中文撰写所有分析内容和建议。"""

        # 📊 统计 prompt 大小
        prompt_length = len(prompt)
        estimated_tokens = int(prompt_length / 1.8)

        logger.info(f"📊 [Research Manager] Prompt 统计:")
        logger.info(f"   - 辩论历史长度: {len(history)} 字符")
        logger.info(f"   - 总 Prompt 长度: {prompt_length} 字符")
        logger.info(f"   - 估算输入 Token: ~{estimated_tokens} tokens")

        # ⏱️ 记录开始时间
        start_time = time.time()

        response = llm.invoke(prompt)

        # ⏱️ 记录结束时间
        elapsed_time = time.time() - start_time

        # 📊 统计响应信息
        response_length = len(response.content) if response and hasattr(response, 'content') else 0
        estimated_output_tokens = int(response_length / 1.8)

        logger.info(f"⏱️ [Research Manager] LLM调用耗时: {elapsed_time:.2f}秒")
        logger.info(f"📊 [Research Manager] 响应统计: {response_length} 字符, 估算~{estimated_output_tokens} tokens")

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
