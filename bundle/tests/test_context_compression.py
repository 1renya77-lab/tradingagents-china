import unittest

from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.managers.risk_manager import create_risk_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.context_compression import build_evidence_brief


class FakeResponse:
    content = "中性风险意见：维持轻仓并观察数据质量，严格执行止损纪律。"


class RecordingLLM:
    def __init__(self):
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return FakeResponse()


def sample_state():
    long_market = "市场研究报告：" + "价格低于MA20，MACD零轴下方。" * 200
    long_fund = (
        "基本面报告：DATA_QUALITY: ok=false\n"
        "WARNING: financial snapshot unavailable with explicit disclosure/report date on or before cutoff\n"
        + "禁止编造PE/PB/EPS。" * 120
    )
    return {
        "market_report": long_market,
        "market_brief": "MARKET_BRIEF: 价格低于MA20；MACD零轴下方；风险偏空。",
        "sentiment_report": "情绪报告：" + "讨论热度有限。" * 120,
        "sentiment_brief": "SENTIMENT_BRIEF: 情绪有限；无明确催化。",
        "news_report": "新闻报告：" + "截止日前无可用新闻。" * 120,
        "news_brief": "NEWS_BRIEF: audited_empty；无新闻驱动。",
        "fundamentals_report": long_fund,
        "fundamentals_brief": "FUND_BRIEF: DATA_QUALITY: ok=false；财务数据缺失；不得编造估值。",
        "trader_investment_plan": "交易员计划：" + "轻仓试探，严格止损。" * 80,
        "trader_investment_plan_brief": "TRADER_BRIEF: 轻仓试探；止损优先。",
        "horizon_instruction": "周频，未来5个交易日。",
        "risk_debate_state": {
            "history": "旧历史：" + "很长。" * 200,
            "risk_debate_brief": "RISK_STATE: 尚无一致结论。",
            "current_risky_response": "激进观点：" + "反弹空间。" * 80,
            "current_risky_response_brief": "RISKY_BRIEF: 有反弹空间。",
            "current_safe_response": "保守观点：" + "基本面缺失。" * 80,
            "current_safe_response_brief": "SAFE_BRIEF: 基本面缺失限制仓位。",
            "current_neutral_response": "",
            "count": 0,
        },
    }


class ContextCompressionTest(unittest.TestCase):
    def test_evidence_brief_preserves_data_quality_and_caps_length(self):
        text = (
            "# 基本面报告\n"
            "DATA_QUALITY: ok=false\n"
            "DATA_SOURCE: a-stock-data\n"
            "CUTOFF_DATE: 2026-04-24\n"
            "WARNING: report_period_only, not disclosure_date\n"
            + "财务数据缺失，不能编造估值。" * 300
        )

        brief = build_evidence_brief("fundamentals", text, max_chars=500)

        self.assertLessEqual(len(brief), 500)
        self.assertIn("DATA_QUALITY: ok=false", brief)
        self.assertIn("DATA_SOURCE: a-stock-data", brief)
        self.assertIn("CUTOFF_DATE: 2026-04-24", brief)
        self.assertIn("report_period_only", brief)

    def test_neutral_debator_uses_briefs_only_when_compression_enabled(self):
        compressed_llm = RecordingLLM()
        compressed_node = create_neutral_debator(
            compressed_llm, config={"context_compression_enabled": True}
        )
        compressed_node(sample_state())
        compressed_prompt = compressed_llm.prompts[0]

        self.assertIn("MARKET_BRIEF", compressed_prompt)
        self.assertIn("RISK_STATE", compressed_prompt)
        self.assertNotIn("价格低于MA20，MACD零轴下方。" * 20, compressed_prompt)

        full_llm = RecordingLLM()
        full_node = create_neutral_debator(full_llm, config={"context_compression_enabled": False})
        full_node(sample_state())
        full_prompt = full_llm.prompts[0]

        self.assertIn("价格低于MA20，MACD零轴下方。" * 20, full_prompt)
        self.assertNotIn("MARKET_BRIEF", full_prompt)

    def test_risk_manager_uses_risk_debate_brief_when_compression_enabled(self):
        state = sample_state()
        state["company_of_interest"] = "300269"
        state["investment_plan"] = "TRADER_PLAN: 轻仓试探。"
        state["risk_debate_state"]["history"] = "FULL_RISK_HISTORY:" + "完整辩论。" * 300
        state["risk_debate_state"]["risk_debate_brief"] = "RISK_DEBATE_BRIEF: 数据缺失限制仓位。"
        state["risk_debate_state"]["risky_history"] = ""
        state["risk_debate_state"]["safe_history"] = ""
        state["risk_debate_state"]["neutral_history"] = ""

        compressed_llm = RecordingLLM()
        compressed_node = create_risk_manager(
            compressed_llm, memory=None, config={"context_compression_enabled": True}
        )
        compressed_node(state)
        compressed_prompt = compressed_llm.prompts[0]

        self.assertIn("RISK_DEBATE_BRIEF", compressed_prompt)
        self.assertNotIn("完整辩论。" * 20, compressed_prompt)

        full_llm = RecordingLLM()
        full_node = create_risk_manager(
            full_llm, memory=None, config={"context_compression_enabled": False}
        )
        full_node(state)
        full_prompt = full_llm.prompts[0]

        self.assertIn("完整辩论。" * 20, full_prompt)
        self.assertNotIn("RISK_DEBATE_BRIEF", full_prompt)

    def test_research_manager_uses_compressed_reports_and_debate_when_enabled(self):
        state = sample_state()
        state["company_of_interest"] = "300269"
        state["investment_debate_state"] = {
            "history": "FULL_INVEST_HISTORY:" + "完整投资辩论。" * 300,
            "investment_debate_brief": "INVEST_DEBATE_BRIEF: 多空分歧集中在数据质量。",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 1,
        }

        compressed_llm = RecordingLLM()
        compressed_node = create_research_manager(
            compressed_llm, memory=None, config={"context_compression_enabled": True}
        )
        compressed_node(state)
        compressed_prompt = compressed_llm.prompts[0]

        self.assertIn("MARKET_BRIEF", compressed_prompt)
        self.assertIn("INVEST_DEBATE_BRIEF", compressed_prompt)
        self.assertNotIn("完整投资辩论。" * 20, compressed_prompt)

        full_llm = RecordingLLM()
        full_node = create_research_manager(
            full_llm, memory=None, config={"context_compression_enabled": False}
        )
        full_node(state)
        full_prompt = full_llm.prompts[0]

        self.assertIn("完整投资辩论。" * 20, full_prompt)
        self.assertNotIn("MARKET_BRIEF", full_prompt)


if __name__ == "__main__":
    unittest.main()
