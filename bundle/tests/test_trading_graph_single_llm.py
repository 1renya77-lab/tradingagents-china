import unittest

from tradingagents.graph.trading_graph import TradingAgentsGraph


class _FakeTool:
    def __init__(self, fn):
        self.func = fn


class _FakeToolkit:
    def __init__(self):
        self.get_stock_market_data_unified = _FakeTool(lambda ticker, start, end: f"market:{ticker}:{start}:{end}")
        self.get_stock_fundamentals_unified = _FakeTool(lambda ticker, curr_date=None: f"fund:{ticker}:{curr_date}")
        self.get_stock_news_unified = _FakeTool(lambda ticker, curr_date: f"news:{ticker}:{curr_date}")
        self.get_stock_sentiment_unified = _FakeTool(lambda ticker, curr_date: f"social:{ticker}:{curr_date}")


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def invoke(self, messages):
        return _FakeResponse(
            "**Action**: 买入\n"
            "**Target Position**: 70.00%\n"
            "**Target Price**: 15.5\n"
            "**Confidence**: 0.8\n"
            "**Risk Score**: 0.3\n"
            "**Reasoning**: 四类信息共振，看多未来一周。"
        )


class TradingGraphSingleLLMTest(unittest.TestCase):
    def test_single_llm_direct_builds_unified_final_state(self):
        graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
        graph.toolkit = _FakeToolkit()
        graph.deep_thinking_llm = _FakeLLM()

        init_state = {
            "company_of_interest": "300308",
            "trade_date": "2026-04-10",
            "horizon_instruction": "请判断未来5个交易日的持仓操作。",
            "messages": [],
        }

        final_state = graph._run_single_llm_direct("300308", "2026-04-10", init_state)

        self.assertIn("market:300308", final_state["market_report"])
        self.assertIn("fund:300308:2026-04-10", final_state["fundamentals_report"])
        self.assertIn("news:300308:2026-04-10", final_state["news_report"])
        self.assertIn("social:300308:2026-04-10", final_state["sentiment_report"])
        self.assertIn("**Action**: 买入", final_state["final_trade_decision"])
        self.assertEqual(final_state["trader_investment_plan"], final_state["final_trade_decision"])


if __name__ == "__main__":
    unittest.main()
