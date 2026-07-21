import unittest
from unittest.mock import patch

from tradingagents.agents.utils.agent_utils import Toolkit


class FundamentalsDataSourcesTest(unittest.TestCase):
    def test_a_share_fundamentals_entry_includes_china_fundamentals_aggregate(self):
        with patch(
            "tradingagents.utils.stock_utils.StockUtils.get_market_info",
            return_value={
                "is_china": True,
                "is_hk": False,
                "market_name": "中国A股",
                "currency_name": "人民币",
                "currency_symbol": "¥",
            },
        ), patch(
            "tradingagents.dataflows.interface.get_china_stock_data_unified",
            return_value="PRICE_DATA",
        ), patch(
            "tradingagents.dataflows.china_research.get_china_fundamentals",
            return_value="DATA_SOURCE: a-stock-data\nA-STOCK FUNDAMENTALS",
        ):
            text = Toolkit.get_stock_fundamentals_unified.func(
                "002415",
                curr_date="2026-04-10",
            )

        self.assertIn("## A股聚合基本面数据", text)
        self.assertIn("DATA_SOURCE: a-stock-data", text)
        self.assertIn("A-STOCK FUNDAMENTALS", text)

    def test_a_share_fundamentals_keeps_partial_sections_when_one_source_fails(self):
        with patch(
            "tradingagents.utils.stock_utils.StockUtils.get_market_info",
            return_value={
                "is_china": True,
                "is_hk": False,
                "market_name": "中国A股",
                "currency_name": "人民币",
                "currency_symbol": "¥",
            },
        ), patch(
            "tradingagents.dataflows.interface.get_china_stock_data_unified",
            return_value="PRICE_DATA",
        ), patch(
            "tradingagents.dataflows.china_research.get_china_fundamentals",
            return_value="DATA_QUALITY: ok=true\nAGGREGATE_OK",
        ), patch(
            "tradingagents.dataflows.china_research.get_china_income_statement",
            side_effect=RuntimeError("income down"),
        ), patch(
            "tradingagents.dataflows.china_research.get_china_balance_sheet",
            return_value="BALANCE_OK",
        ), patch(
            "tradingagents.dataflows.china_research.get_china_cashflow",
            return_value="CASHFLOW_OK",
        ):
            text = Toolkit.get_stock_fundamentals_unified.func(
                "002415",
                curr_date="2026-04-10",
            )

        self.assertIn("PRICE_DATA", text)
        self.assertIn("AGGREGATE_OK", text)
        self.assertIn("BALANCE_OK", text)
        self.assertIn("CASHFLOW_OK", text)
        self.assertIn("基本面分段错误摘要", text)
        self.assertIn("income down", text)
        self.assertNotIn("数据获取失败:", text)


if __name__ == "__main__":
    unittest.main()
