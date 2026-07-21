import unittest
import inspect

from tradingagents.agents.managers.risk_manager import build_risk_manager_prompt
from tradingagents.agents.risk_mgmt.aggresive_debator import build_risky_debator_prompt
from tradingagents.agents.risk_mgmt.conservative_debator import create_safe_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.utils.data_availability import MISSING_DATA_INTERPRETATION_RULE


class RiskPromptContractsTest(unittest.TestCase):
    def test_risky_debator_prompt_forbids_role_refusal_and_requires_offensive_position(self):
        prompt = build_risky_debator_prompt(
            trader_decision="建议持有。",
            horizon_instruction="本次信号是周频信号。",
            market_research_report="市场强趋势向上，均线多头排列。",
            sentiment_report="情绪积极。",
            news_report="订单催化。",
            fundamentals_report="基本面稳健。",
            history="",
            current_safe_response="风险较高。",
            current_neutral_response="建议观望。",
        )

        self.assertIn("不得拒绝扮演激进风险分析师", prompt)
        self.assertIn("进攻性仓位", prompt)
        self.assertIn("alpha", prompt.lower())
        self.assertIn("IR", prompt)
        self.assertIn("证据链", prompt)
        self.assertIn("触发进攻加仓", prompt)
        self.assertIn("现在可承受的进攻仓位", prompt)
        self.assertIn(MISSING_DATA_INTERPRETATION_RULE, prompt)
        self.assertNotIn("60%-80%", prompt)
        self.assertNotIn("80%-95%", prompt)

    def test_risk_manager_prompt_requires_alpha_ir_and_explicit_target_position(self):
        prompt = build_risk_manager_prompt(
            instrument_context="A股长仓约束",
            history="Risky Analyst: 建议提高仓位。",
            trader_plan="建议持有。",
            horizon_instruction="本次信号是周频信号。",
            memory_guidance="当前没有历史记忆。",
        )

        self.assertIn("target_position", prompt)
        self.assertIn("A股为长仓/现金约束", prompt)
        self.assertIn("数据缺失", prompt)
        self.assertIn("不要套用固定技术指标或固定仓位分档", prompt)
        self.assertIn("未来5个交易日", prompt)
        self.assertIn("先判断合适的目标仓位，再给出 action", prompt)
        self.assertIn("仓位失效条件", prompt)
        self.assertIn("news/social 数据缺失只表示该信息源", prompt)
        self.assertIn("不能单独推出卖出、减仓或降低仓位", prompt)
        self.assertNotIn("trend_strength >=", prompt)
        self.assertNotIn("reward_risk_score >=", prompt)
        self.assertNotIn("recommended_position_floor` 通常", prompt)
        self.assertNotIn("45%-55% 不是默认仓位带", prompt)
        self.assertNotIn("mid_position_justification", prompt)
        self.assertNotIn("MACD 零轴下方、均线空头排列且 RSI<50", prompt)
        self.assertNotIn("默认应在 65%-85%", prompt)
        self.assertNotIn("通常不应低于 45%-55%", prompt)
        self.assertNotIn("20%-40% 的探索性参与仓位", prompt)

    def test_safe_and_neutral_prompts_do_not_treat_low_vol_or_mid_position_as_default(self):
        class FakeLLM:
            def invoke(self, prompt):
                self.prompt = prompt
                class Resp:
                    content = "ok"
                return Resp()

        state = {
            "risk_debate_state": {"history": "", "safe_history": "", "neutral_history": "", "risky_history": "", "count": 0},
            "market_report": "趋势仍在。",
            "sentiment_report": "情绪中性。",
            "news_report": "催化待确认。",
            "fundamentals_report": "基本面较强。",
            "trader_investment_plan": "建议持有。",
            "horizon_instruction": "本次信号是周频信号。",
        }

        safe_llm = FakeLLM()
        create_safe_debator(safe_llm)(state)
        self.assertIn("不能把“低波动”本身当作胜利", safe_llm.prompt)
        self.assertIn("保留部分仓位的风险收益理由", safe_llm.prompt)
        self.assertIn("PE/PB/估值口径看起来异常", safe_llm.prompt)
        self.assertIn(MISSING_DATA_INTERPRETATION_RULE, safe_llm.prompt)
        self.assertNotIn("0%-10%", safe_llm.prompt)

        neutral_llm = FakeLLM()
        create_neutral_debator(neutral_llm)(state)
        self.assertIn("不能把“折中”简化成默认 50% 仓位", neutral_llm.prompt)
        self.assertIn("合理的 target_position", neutral_llm.prompt)
        self.assertIn("估值口径或 PE/PB 数据异常", neutral_llm.prompt)
        self.assertIn(MISSING_DATA_INTERPRETATION_RULE, neutral_llm.prompt)
        self.assertNotIn("35%-45%", neutral_llm.prompt)

    def test_downstream_decision_nodes_share_missing_data_interpretation_contract(self):
        from tradingagents.agents.trader import trader
        from tradingagents.agents.researchers import bull_researcher, bear_researcher
        from tradingagents.agents.managers import research_manager

        for module in (trader, bull_researcher, bear_researcher, research_manager):
            source = inspect.getsource(module)
            self.assertIn("MISSING_DATA_INTERPRETATION_RULE", source)


if __name__ == "__main__":
    unittest.main()
