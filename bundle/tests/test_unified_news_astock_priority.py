import unittest
from unittest.mock import Mock, patch

from tradingagents.tools.unified_news_tool import UnifiedNewsAnalyzer


class UnifiedNewsAStockPriorityTest(unittest.TestCase):
    def test_a_share_news_prefers_astock_before_other_sources(self):
        analyzer = UnifiedNewsAnalyzer(toolkit=Mock())

        with patch(
            "tradingagents.dataflows.astock_data_provider.get_astock_news_report",
            return_value=(
                "DATA_QUALITY: ok=true\n"
                "DATA_SOURCE: a-stock-data\n"
                "DATA_VENDOR: EastMoney stock news + CNInfo announcements\n"
                "CUTOFF_DATE: 2026-06-05\n"
                "信号日前公告"
            ),
        ), patch.object(analyzer, "_get_news_from_database") as db_news, patch.object(
            analyzer, "_fetch_akshare_a_share_news_bundle"
        ) as ak_news:
            text = analyzer._get_a_share_news("601899", "2026-06-05", 10)

        self.assertIn("DATA_SOURCE: a-stock-data", text)
        self.assertIn("信号日前公告", text)
        db_news.assert_not_called()
        ak_news.assert_not_called()

    def test_a_share_news_returns_explicit_failure_without_legacy_fallbacks(self):
        analyzer = UnifiedNewsAnalyzer(toolkit=Mock())

        with patch(
            "tradingagents.dataflows.astock_data_provider.get_astock_news_report",
            side_effect=RuntimeError("network down"),
        ), patch.object(analyzer, "_get_news_from_database") as db_news, patch.object(
            analyzer, "_fetch_akshare_a_share_news_bundle"
        ) as ak_news:
            text = analyzer._get_a_share_news("601899", "2026-06-05", 10)

        self.assertIn("DATA_QUALITY: ok=false", text)
        self.assertIn("DATA_SOURCE: a-stock-data", text)
        self.assertIn("network down", text)
        db_news.assert_not_called()
        ak_news.assert_not_called()


if __name__ == "__main__":
    unittest.main()
