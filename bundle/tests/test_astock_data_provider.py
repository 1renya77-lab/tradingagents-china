import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
import os

import pandas as pd

from tradingagents.dataflows import china_research
from tradingagents.dataflows.astock_data_provider import (
    cninfo_announcements,
    eastmoney_stock_news,
    filter_baostock_financial_indicators,
    format_astock_fundamentals_report,
    format_astock_news_report,
    get_astock_fundamentals_report,
    get_astock_news_report,
)


class AStockDataProviderTest(unittest.TestCase):
    def test_news_report_filters_future_and_undated_items(self):
        text = format_astock_news_report(
            "601899",
            "2026-06-05",
            news_items=[
                {
                    "title": "信号日前新闻",
                    "content": "用于历史回测",
                    "time": "2026-06-05 09:30:00",
                    "source": "东财",
                    "url": "https://example.com/old",
                },
                {
                    "title": "未来新闻",
                    "content": "不应进入",
                    "time": "2026-06-05 19:31:00",
                    "source": "东财",
                },
                {
                    "title": "同日无具体时间新闻",
                    "content": "不应进入",
                    "time": "2026-06-05",
                    "source": "东财",
                },
                {"title": "无时间新闻", "content": "不应进入", "source": "东财"},
            ],
            announcements=[
                {
                    "title": "信号日前公告",
                    "type": "临时公告",
                    "date": "2026-06-04",
                    "url": "https://example.com/notice",
                }
            ],
        )

        self.assertIn("DATA_SOURCE: a-stock-data", text)
        self.assertIn("CUTOFF_DATE: 2026-06-05 19:30:00", text)
        self.assertIn("SIGNAL_GENERATION_TIME: 2026-06-05 20:00:00", text)
        self.assertIn("EXECUTION_RULE: signal generated after close on T; rebalance at T+1 open.", text)
        self.assertIn("TEMPORAL_RULE", text)
        self.assertIn("信号日前新闻", text)
        self.assertIn("信号日前公告", text)
        self.assertNotIn("未来新闻", text)
        self.assertNotIn("同日无具体时间新闻", text)
        self.assertNotIn("无时间新闻", text)

    def test_fundamentals_report_keeps_company_profile_and_audited_announcements(self):
        text = format_astock_fundamentals_report(
            "601899",
            "2026-06-05",
            company_info={
                "name": "紫金矿业",
                "industry": "贵金属",
                "mcap": 100000000,
                "list_date": "20080425",
            },
            statements={
                "income_statement": [
                    {"报告期": "2025-12-31", "净利润": "100"},
                    {"报告期": "2026-06-30", "净利润": "200"},
                ]
            },
            announcements=[
                {"title": "2025年年度报告", "type": "年报", "date": "2026-03-28 18:00:00"},
                {"title": "未来公告", "type": "公告", "date": "2026-06-30"},
            ],
        )

        self.assertIn("紫金矿业", text)
        self.assertIn("贵金属", text)
        self.assertIn("2025年年度报告", text)
        self.assertNotIn("未来公告", text)
        self.assertIn("report_period_only", text)
        self.assertIn("2025-12-31", text)
        self.assertNotIn("2026-06-30", text)

    def test_astock_statement_rows_require_audited_announcement_before_cutoff(self):
        text = format_astock_fundamentals_report(
            "601899",
            "2026-04-17",
            company_info={},
            statements={
                "income_statement": [
                    {"报告期": "2026-03-31", "净利润": "future q1"},
                    {"报告期": "2025-12-31", "净利润": "known annual"},
                ]
            },
            announcements=[
                {"title": "2025年年度报告", "type": "年报", "date": "2026-03-21 18:00:00"},
                {"title": "2026年第一季度报告", "type": "一季报", "date": "2026-04-22 18:00:00"},
            ],
        )

        self.assertIn("2025-12-31", text)
        self.assertIn("known annual", text)
        self.assertNotIn("2026-03-31", text)
        self.assertNotIn("future q1", text)

    def test_baostock_financial_indicators_filter_by_publication_date(self):
        indicators = {
            "profit": [
                {"pubDate": "2025-10-18", "statDate": "2025-09-30", "roeAvg": "0.244994"},
                {"pubDate": "2025-08-27", "statDate": "2025-06-30", "roeAvg": "0.165272"},
            ]
        }

        before_q3 = filter_baostock_financial_indicators(indicators, "2025-10-03")
        after_q3 = filter_baostock_financial_indicators(indicators, "2025-10-24")

        self.assertEqual(before_q3["profit"][0]["statDate"], "2025-06-30")
        self.assertNotIn("2025-09-30", [row["statDate"] for row in before_q3["profit"]])
        self.assertEqual(after_q3["profit"][0]["statDate"], "2025-09-30")

    def test_fundamentals_report_includes_baostock_financial_indicators(self):
        text = format_astock_fundamentals_report(
            "601899",
            "2025-10-24",
            company_info={},
            statements={},
            announcements=[],
            baostock_financials={
                "profit": [
                    {
                        "pubDate": "2025-10-18",
                        "statDate": "2025-09-30",
                        "roeAvg": "0.244994",
                        "netProfit": "45701159981",
                    }
                ],
                "growth": [
                    {
                        "pubDate": "2025-10-18",
                        "statDate": "2025-09-30",
                        "YOYNI": "0.539882",
                    }
                ],
            },
        )

        self.assertIn("DATA_QUALITY: ok=true", text)
        self.assertIn("BaoStock Financial Indicators", text)
        self.assertIn("2025-09-30", text)
        self.assertIn("45701159981", text)

    def test_china_fundamentals_appends_astock_enrichment(self):
        with patch.object(china_research, "get_stock_info", return_value={}), patch.object(
            china_research, "get_industryClassification", return_value="贵金属"
        ), patch.object(china_research, "_latest_spot_snapshot", return_value={}), patch.object(
            china_research, "_financial_abstract", return_value=pd.DataFrame()
        ), patch.object(china_research, "_profit_snapshot_baostock", return_value=pd.DataFrame()), patch.object(
            china_research, "get_astock_fundamentals_report", return_value="DATA_SOURCE: a-stock-data\n公司资料"
        ):
            text = china_research.get_china_fundamentals("601899", "2026-06-05")

        self.assertIn("a-stock-data fundamentals", text)
        self.assertIn("DATA_SOURCE: a-stock-data", text)

    def test_china_fundamentals_prefers_astock_as_primary_source(self):
        with patch.object(
            china_research,
            "get_astock_fundamentals_report",
            return_value=(
                "DATA_QUALITY: ok=true\n"
                "DATA_SOURCE: a-stock-data\n"
                "DATA_VENDOR: EastMoney stock info + Sina statements + CNInfo announcements\n"
                "CUTOFF_DATE: 2026-06-05\n"
                "A-STOCK ONLY"
            ),
        ), patch.object(china_research, "_latest_spot_snapshot") as spot, patch.object(
            china_research, "_financial_abstract"
        ) as abstract, patch.object(china_research, "_profit_snapshot_baostock") as baostock:
            text = china_research.get_china_fundamentals("601899", "2026-06-05")

        self.assertTrue(text.startswith("DATA_QUALITY: ok=true\nDATA_SOURCE: a-stock-data"))
        self.assertIn("A-STOCK ONLY", text)
        spot.assert_not_called()
        abstract.assert_not_called()
        baostock.assert_not_called()

    def test_baostock_profit_snapshot_filters_by_publication_date(self):
        future_q1 = pd.DataFrame(
            [
                {
                    "code": "sh.601899",
                    "pubDate": "2026-04-22",
                    "statDate": "2026-03-31",
                    "netProfit": "25165728674",
                }
            ]
        )
        known_annual = pd.DataFrame(
            [
                {
                    "code": "sh.601899",
                    "pubDate": "2026-03-21",
                    "statDate": "2025-12-31",
                    "netProfit": "63822189587",
                }
            ]
        )

        def fake_get_stock_fundamentals(code, year, quarter):
            if (year, quarter) == (2026, 1):
                return future_q1
            if (year, quarter) == (2025, 4):
                return known_annual
            return pd.DataFrame()

        with patch.object(
            china_research,
            "get_stock_fundamentals",
            side_effect=fake_get_stock_fundamentals,
        ):
            df = china_research._profit_snapshot_baostock("601899", "2026-04-17")

        self.assertIn("2025-12-31", df["statDate"].tolist())
        self.assertNotIn("2026-03-31", df["statDate"].tolist())

    def test_china_news_uses_astock_when_akshare_has_no_audited_rows(self):
        with patch.object(
            china_research,
            "get_astock_news_report",
            return_value="DATA_QUALITY: ok=true\nDATA_SOURCE: a-stock-data\n信号日前公告",
        ), patch.object(china_research, "_require_akshare", side_effect=RuntimeError("akshare down")):
            text = china_research.get_china_news("601899", "2026-06-01", "2026-06-05")

        self.assertIn("DATA_SOURCE: a-stock-data", text)
        self.assertIn("信号日前公告", text)

    def test_china_news_prefers_astock_even_when_akshare_has_rows(self):
        class FakeAk:
            @staticmethod
            def stock_news_em(symbol):
                return pd.DataFrame(
                    [
                        {
                            "新闻标题": "AkShare 新闻",
                            "发布时间": "2026-06-05 10:00:00",
                            "文章来源": "东方财富",
                        }
                    ]
                )

        with patch.object(
            china_research,
            "get_astock_news_report",
            return_value="DATA_QUALITY: ok=true\nDATA_SOURCE: a-stock-data\n信号日前公告",
        ), patch.object(china_research, "_require_akshare", return_value=FakeAk):
            text = china_research.get_china_news("601899", "2026-06-01", "2026-06-05")

        self.assertIn("DATA_SOURCE: a-stock-data", text)
        self.assertIn("信号日前公告", text)
        self.assertNotIn("AkShare 新闻", text)

    def test_astock_fundamentals_keeps_partial_data_when_company_profile_fails(self):
        with TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"TRADINGAGENTS_PREFETCH_DIR": tmp}
        ), patch(
            "tradingagents.dataflows.astock_data_provider.eastmoney_stock_info",
            side_effect=RuntimeError("eastmoney down"),
        ), patch(
            "tradingagents.dataflows.astock_data_provider.cninfo_announcements",
            return_value=[{"title": "2026年第一季度报告", "type": "一季报", "date": "2026-04-28"}],
        ), patch(
            "tradingagents.dataflows.astock_data_provider.sina_financial_report",
            return_value=[{"报告期": "2026-03-31", "营业收入": "100"}],
        ), patch(
            "tradingagents.dataflows.astock_data_provider.fetch_baostock_financial_indicators",
            return_value={},
        ):
            text = get_astock_fundamentals_report("601899", "2026-06-05")

        self.assertIn("DATA_QUALITY: ok=true", text)
        self.assertIn("EastMoney company profile unavailable", text)
        self.assertIn("2026年第一季度报告", text)
        self.assertIn("2026-03-31", text)

    def test_astock_news_keeps_announcements_when_stock_news_fails(self):
        with TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"TRADINGAGENTS_PREFETCH_DIR": tmp}
        ), patch(
            "tradingagents.dataflows.astock_data_provider.eastmoney_stock_news",
            side_effect=RuntimeError("eastmoney news down"),
        ), patch(
            "tradingagents.dataflows.astock_data_provider.cninfo_announcements",
            return_value=[{"title": "信号日前公告", "type": "公告", "date": "2026-06-04"}],
        ):
            text = get_astock_news_report("601899", "2026-06-05")

        self.assertIn("DATA_QUALITY: ok=true", text)
        self.assertIn("EastMoney stock news unavailable", text)
        self.assertIn("信号日前公告", text)

    def test_astock_news_does_not_use_legacy_pool_cache_for_signal_date(self):
        from tradingagents.dataflows.local_prefetch_cache import (
            NEWS_SOURCE_CNINFO,
            NEWS_SOURCE_EASTMONEY,
            save_news_items,
        )

        with TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"TRADINGAGENTS_PREFETCH_DIR": tmp}
        ):
            save_news_items(
                "601899",
                NEWS_SOURCE_EASTMONEY,
                [{"title": "旧总池新闻", "content": "pool", "time": "2026-06-01 10:00:00", "source": "东财"}],
                origin="unit",
            )
            save_news_items(
                "601899",
                NEWS_SOURCE_CNINFO,
                [{"title": "旧总池公告", "type": "公告", "date": "2026-06-01 10:00:00"}],
                origin="unit",
            )
            with patch(
                "tradingagents.dataflows.astock_data_provider.eastmoney_stock_news",
                return_value=[{"title": "实时信号日新闻", "content": "live", "time": "2026-06-05 10:00:00", "source": "东财"}],
            ), patch(
                "tradingagents.dataflows.astock_data_provider.cninfo_announcements",
                return_value=[{"title": "实时信号日公告", "type": "公告", "date": "2026-06-04 18:00:00"}],
            ):
                text = get_astock_news_report("601899", "2026-06-05")

        self.assertIn("实时信号日新闻", text)
        self.assertIn("实时信号日公告", text)
        self.assertNotIn("旧总池新闻", text)
        self.assertNotIn("旧总池公告", text)

    def test_astock_news_excludes_stale_announcements_from_news_agent_window(self):
        text = format_astock_news_report(
            "601899",
            "2025-12-26",
            news_items=[],
            announcements=[
                {"title": "近期开会公告", "type": "公告", "date": "2025-12-20 18:00:00"},
                {"title": "过旧治理公告", "type": "公告", "date": "2025-11-29 18:00:00"},
            ],
        )

        self.assertIn("DATA_QUALITY: ok=true", text)
        self.assertIn("近期开会公告", text)
        self.assertNotIn("过旧治理公告", text)
        self.assertIn("news_agent_recent_window_days=14", text)

    def test_astock_fundamentals_falls_back_to_baostock_company_profile(self):
        with TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"TRADINGAGENTS_PREFETCH_DIR": tmp}
        ), patch(
            "tradingagents.dataflows.astock_data_provider.eastmoney_stock_info",
            side_effect=RuntimeError("eastmoney down"),
        ), patch(
            "tradingagents.dataflows.astock_data_provider.get_stock_info",
            return_value={
                "code": "sz.300308",
                "code_name": "中际旭创",
                "ipoDate": "2012-04-10",
            },
        ), patch(
            "tradingagents.dataflows.astock_data_provider.get_industryClassification",
            return_value="C39计算机、通信和其他电子设备制造业",
        ), patch(
            "tradingagents.dataflows.astock_data_provider.cninfo_announcements",
            return_value=[],
        ), patch(
            "tradingagents.dataflows.astock_data_provider.sina_financial_report",
            return_value=[],
        ), patch(
            "tradingagents.dataflows.astock_data_provider.fetch_baostock_financial_indicators",
            return_value={},
        ):
            text = get_astock_fundamentals_report("300308", "2026-04-03")

        self.assertIn("DATA_QUALITY: ok=false", text)
        self.assertIn("- name: 中际旭创", text)
        self.assertIn("- industry: C39计算机、通信和其他电子设备制造业", text)
        self.assertIn("- list_date: 2012-04-10", text)

    def test_astock_fundamentals_falls_back_to_cninfo_profile_when_baostock_missing(self):
        with TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"TRADINGAGENTS_PREFETCH_DIR": tmp}
        ), patch(
            "tradingagents.dataflows.astock_data_provider.eastmoney_stock_info",
            side_effect=RuntimeError("eastmoney down"),
        ), patch(
            "tradingagents.dataflows.astock_data_provider.get_stock_info",
            return_value=None,
        ), patch(
            "tradingagents.dataflows.astock_data_provider.get_industryClassification",
            return_value=None,
        ), patch(
            "tradingagents.dataflows.astock_data_provider.cninfo_stock_profile",
            return_value={
                "code": "300308",
                "name": "中际旭创",
                "org_id": "gssz0300308",
                "exchange": "SZSE",
                "mcap": 1000000000,
            },
        ), patch(
            "tradingagents.dataflows.astock_data_provider.cninfo_announcements",
            return_value=[],
        ), patch(
            "tradingagents.dataflows.astock_data_provider.sina_financial_report",
            return_value=[],
        ), patch(
            "tradingagents.dataflows.astock_data_provider.fetch_baostock_financial_indicators",
            return_value={},
        ):
            text = get_astock_fundamentals_report("300308", "2026-04-03")

        self.assertIn("DATA_QUALITY: ok=true", text)
        self.assertIn("- name: 中际旭创", text)
        self.assertIn("- org_id: gssz0300308", text)
        self.assertIn("- exchange: SZSE", text)

    def test_eastmoney_stock_news_paginates_until_cutoff_window(self):
        class FakeResponse:
            def __init__(self, text):
                self.text = text

            def raise_for_status(self):
                return None

        def make_payload(items):
            return 'jQuery_news(' + pd.Series(
                [{"result": {"cmsArticleWebOld": items}}]
            ).to_json(orient="records")[1:-1] + ')'

        newest_page = [
            {"title": "2026-06 新闻", "content": "future", "date": "2026-06-21 10:00:00", "mediaName": "东财", "url": "u1"},
        ]
        cutoff_page = [
            {"title": "2026-04-02 新闻", "content": "old", "date": "2026-04-02 10:00:00", "mediaName": "东财", "url": "u2"},
        ]

        calls = []

        def fake_get(_url, params=None, **_kwargs):
            calls.append(params["param"])
            if '"pageIndex":1' in params["param"]:
                return FakeResponse(make_payload(newest_page))
            if '"pageIndex":2' in params["param"]:
                return FakeResponse(make_payload(cutoff_page))
            return FakeResponse(make_payload([]))

        with patch("tradingagents.dataflows.astock_data_provider.requests.get", side_effect=fake_get):
            items = eastmoney_stock_news("300308", page_size=1, cutoff_date="2026-04-03", max_pages=3)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[-1]["title"], "2026-04-02 新闻")
        self.assertGreaterEqual(len(calls), 2)

    def test_cninfo_announcements_paginates_until_cutoff_window(self):
        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        calls = []

        def fake_post(_url, data=None, **_kwargs):
            calls.append(data["pageNum"])
            page = int(data["pageNum"])
            if page == 1:
                announcements = [
                    {"announcementTitle": "2026-06 公告", "announcementTypeName": "公告", "announcementTime": pd.Timestamp("2026-06-01").timestamp() * 1000, "announcementId": "1"},
                ]
            elif page == 2:
                announcements = [
                    {"announcementTitle": "2026-04-02 公告", "announcementTypeName": "公告", "announcementTime": pd.Timestamp("2026-04-02").timestamp() * 1000, "announcementId": "2"},
                ]
            else:
                announcements = []
            return FakeResponse({"announcements": announcements})

        with patch("tradingagents.dataflows.astock_data_provider._cninfo_orgid", return_value="gssz0300308"), patch(
            "tradingagents.dataflows.astock_data_provider.requests.post",
            side_effect=fake_post,
        ):
            items = cninfo_announcements("300308", page_size=1, cutoff_date="2026-04-03", max_pages=3)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[-1]["title"], "2026-04-02 公告")
        self.assertEqual(calls[:2], ["1", "2"])

    def test_cninfo_announcements_keep_download_url(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "announcements": [
                        {
                            "announcementTitle": "2025年度报告",
                            "announcementTypeName": "定期报告",
                            "announcementTime": pd.Timestamp("2026-03-31").timestamp() * 1000,
                            "announcementId": "1225056498",
                            "adjunctUrl": "finalpage/2026-03-31/1225056498.PDF",
                            "adjunctType": "PDF",
                            "adjunctSize": 1024,
                        }
                    ]
                }

        with patch("tradingagents.dataflows.astock_data_provider._cninfo_orgid", return_value="gssz0300308"), patch(
            "tradingagents.dataflows.astock_data_provider.requests.post",
            return_value=FakeResponse(),
        ):
            items = cninfo_announcements("300308", page_size=1, cutoff_date="2026-04-03", max_pages=1)

        self.assertEqual(items[0]["announcement_id"], "1225056498")
        self.assertEqual(items[0]["adjunct_url"], "finalpage/2026-03-31/1225056498.PDF")
        self.assertEqual(
            items[0]["download_url"],
            "https://static.cninfo.com.cn/finalpage/2026-03-31/1225056498.PDF",
        )


if __name__ == "__main__":
    unittest.main()
