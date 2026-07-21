import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
import os
import json

import pandas as pd

from tradingagents.agents.utils.data_availability import (
    build_skipped_analyst_report,
    is_missing_data_payload,
)


class DataAvailabilitySkipTest(unittest.TestCase):
    def test_detects_explicit_failed_data_quality_payload(self):
        payload = (
            "DATA_QUALITY: ok=false\n"
            "DATA_SOURCE: a-stock-data\n"
            "ROWS: 0\n"
            "No audited stock news before cutoff."
        )

        self.assertTrue(is_missing_data_payload(payload))

    def test_keeps_partial_but_quality_ok_payload(self):
        payload = (
            "DATA_QUALITY: ok=true\n"
            "DATA_SOURCE: a-stock-data\n"
            "ROWS: 2\n"
            "Company profile unavailable, but announcements are available."
        )

        self.assertFalse(is_missing_data_payload(payload))

    def test_skipped_report_makes_absence_explicit(self):
        report = build_skipped_analyst_report(
            analyst="news",
            ticker="300308",
            current_date="2026-04-03",
            reason="no usable audited news before cutoff",
            raw_payload="DATA_QUALITY: ok=false\nROWS: 0",
        )

        self.assertIn("## news 数据审核结果", report)
        self.assertIn("截止日期: 2026-04-03 19:30", report)
        self.assertIn("不要把缺失数据解读为利好、利空或中性信号", report)
        self.assertIn("该分析师本次跳过", report)
        self.assertNotIn("RAW_DATA_SUMMARY", report)
        self.assertNotIn("DATA_QUALITY: ok=false\nROWS: 0", report)

    def test_sentiment_analyst_skips_when_all_sources_missing(self):
        from tradingagents.agents.analysts.legacy.sentiment_analyst import create_sentiment_analyst

        class FailingLLM:
            def invoke(self, *_args, **_kwargs):
                raise AssertionError("LLM should not be called when all sentiment inputs are missing")

        with patch(
            "tradingagents.agents.analysts.legacy.sentiment_analyst.bind_structured",
            return_value=FailingLLM(),
        ), patch(
            "tradingagents.agents.analysts.legacy.sentiment_analyst.get_news.func",
            return_value="DATA_QUALITY: ok=false\nROWS: 0\nNo audited stock news before cutoff.",
        ), patch(
            "tradingagents.agents.analysts.legacy.sentiment_analyst.fetch_stocktwits_messages",
            return_value="<no StockTwits messages found for $300308>",
        ), patch(
            "tradingagents.agents.analysts.legacy.sentiment_analyst.fetch_reddit_posts",
            return_value="<no Reddit posts found mentioning 300308 across r/stocks in the past 7 days>",
        ):
            node = create_sentiment_analyst(FailingLLM())
            result = node(
                {
                    "company_of_interest": "300308",
                    "trade_date": "2026-04-03",
                    "messages": [],
                }
            )

        self.assertIn("## sentiment 数据审核结果", result["sentiment_report"])
        self.assertIn("该分析师本次跳过", result["sentiment_report"])

    def test_social_media_analyst_skips_when_public_discussion_missing(self):
        from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst

        class FailingLLM:
            def bind_tools(self, *_args, **_kwargs):
                raise AssertionError("LLM should not be called when social discussion data is missing")

        class FakeTool:
            def invoke(self, _args):
                return (
                    "DATA_QUALITY: ok=false\n"
                    "DATA_SOURCE: chinese-social-public\n"
                    "ROWS: 0\n"
                    "SKIPPED_ANALYST: social\n"
                    "REASON: no usable social discussion data before cutoff"
                )

        class FakeToolkit:
            get_stock_sentiment_unified = FakeTool()

        with patch(
            "tradingagents.agents.analysts.social_media_analyst._get_company_name_for_social_media",
            return_value="中际旭创",
        ):
            node = create_social_media_analyst(FailingLLM(), FakeToolkit())
            result = node(
                {
                    "company_of_interest": "300308",
                    "trade_date": "2026-04-03",
                    "messages": [],
                }
            )

        self.assertIn("## social 数据审核结果", result["sentiment_report"])
        self.assertIn("该分析师本次跳过", result["sentiment_report"])

    def test_chinese_social_sentiment_requires_signal_date_snapshot_cache(self):
        from tradingagents.dataflows.news.chinese_finance import get_chinese_social_sentiment

        with TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"TRADINGAGENTS_PREFETCH_DIR": tmp}):
                report = get_chinese_social_sentiment("300308", "2026-04-03")

        self.assertIn("DATA_QUALITY: ok=false", report)
        self.assertIn("signal-date snapshot", report)
        self.assertIn("SKIPPED_ANALYST: social", report)

    def test_data_auditor_marks_missing_analyst_inputs_from_preflight(self):
        from tradingagents.agents.data_auditor import create_data_auditor
        from tradingagents.dataflows.local_prefetch_cache import (
            NEWS_SOURCE_CNINFO,
            NEWS_SOURCE_EASTMONEY,
            save_json_data,
            save_market_data,
            save_news_items,
        )

        with TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            preflight_dir = project_dir / "outputs" / "runs" / "audit_smoke" / "data_preflight"
            preflight_dir.mkdir(parents=True)
            (preflight_dir / "preflight_data_quality.csv").write_text(
                "ticker,signal_date,market_ok,market_rows,news_ok,news_rows,"
                "fundamentals_ok,fundamentals_rows,social_discussion_ok,"
                "social_discussion_rows,social_event_rows,all_core_ok\n"
                "300308,2026-04-03,True,215,True,15,True,19,False,0,15,True\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"TRADINGAGENTS_PREFETCH_DIR": str(project_dir / "data" / "prefetch")}):
                save_market_data(
                    "300308",
                    pd.DataFrame(
                        [
                            {
                                "Date": f"2026-03-{day:02d}",
                                "Open": 10 + day,
                                "High": 11 + day,
                                "Low": 9 + day,
                                "Close": 10 + day,
                                "Volume": 1000 + day,
                            }
                            for day in range(1, 26)
                        ]
                    ),
                    source="unit",
                )
                save_json_data(
                    "300308",
                    "fundamentals",
                    "eastmoney_company_info",
                    {"price": 10, "mcap": 1000000000},
                )
                save_news_items(
                    "300308",
                    NEWS_SOURCE_EASTMONEY,
                    [{"title": "信号日前新闻", "content": "用于新闻审核", "time": "2026-04-02 10:00:00", "source": "东财"}],
                    origin="unit",
                    snapshot_date="2026-04-03",
                    replace=True,
                )
                save_news_items(
                    "300308",
                    NEWS_SOURCE_CNINFO,
                    [{"title": "信号日前公告", "type": "公告", "date": "2026-04-02 18:00:00"}],
                    origin="unit",
                    snapshot_date="2026-04-03",
                    replace=True,
                )

                auditor = create_data_auditor(
                    config={"project_dir": str(project_dir), "run_name": "audit_smoke"},
                    selected_analysts=["market", "fundamentals", "news", "social"],
                )
                result = auditor({"company_of_interest": "300308", "trade_date": "2026-04-03"})

        self.assertEqual(set(result["skip_analysts"].keys()), {"social"})
        self.assertIn("## social 数据审核结果", result["sentiment_report"])
        self.assertIn("Data Auditor", result["data_audit_report"])

    def test_social_media_analyst_honors_data_auditor_skip_without_llm_or_tool(self):
        from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst

        class FailingLLM:
            def bind_tools(self, *_args, **_kwargs):
                raise AssertionError("LLM should not be called after Data Auditor marks social missing")

        class FailingTool:
            def invoke(self, *_args, **_kwargs):
                raise AssertionError("tool should not be called after Data Auditor marks social missing")

        class FakeToolkit:
            get_stock_sentiment_unified = FailingTool()

        node = create_social_media_analyst(FailingLLM(), FakeToolkit())
        result = node(
            {
                "company_of_interest": "300308",
                "trade_date": "2026-04-03",
                "messages": [],
                "skip_analysts": {"social": "preflight social_discussion_rows=0"},
            }
        )

        self.assertIn("## social 数据审核结果", result["sentiment_report"])
        self.assertIn("preflight social_discussion_rows=0", result["sentiment_report"])

    def test_data_auditor_checks_evidence_cutoff_not_only_preflight_ok(self):
        from tradingagents.agents.data_auditor import create_data_auditor

        old_prefetch_dir = os.environ.get("TRADINGAGENTS_PREFETCH_DIR")
        with TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            cache_dir = Path(tmp) / "prefetch"
            os.environ["TRADINGAGENTS_PREFETCH_DIR"] = str(cache_dir)

            preflight_dir = project_dir / "outputs" / "runs" / "audit_evidence" / "data_preflight"
            preflight_dir.mkdir(parents=True)
            (preflight_dir / "preflight_data_quality.csv").write_text(
                "ticker,signal_date,market_ok,market_rows,news_ok,news_rows,"
                "fundamentals_ok,fundamentals_rows,social_discussion_ok,"
                "social_discussion_rows,social_event_rows,all_core_ok\n"
                "300308,2026-04-03,True,25,True,2,True,3,True,1,0,True\n",
                encoding="utf-8",
            )

            market_dir = cache_dir / "market"
            market_dir.mkdir(parents=True)
            market_rows = ["Symbol,Date,Open,High,Low,Close,Volume,Source"]
            for day in range(10, 32):
                market_rows.append(f"300308,2026-03-{day:02d},10,11,9,10.5,1000,unit")
            for day in range(1, 3):
                market_rows.append(f"300308,2026-04-{day:02d},10,11,9,10.5,1000,unit")
            (market_dir / "300308.csv").write_text("\n".join(market_rows), encoding="utf-8")

            news_dir = cache_dir / "news"
            news_dir.mkdir(parents=True)
            (news_dir / "300308_eastmoney.csv").write_text(
                "Symbol,title,content,time,source,url,CacheSource\n"
                "300308,未来新闻,未来内容,2026-04-04 09:00:00,EastMoney,http://future,unit\n",
                encoding="utf-8",
            )
            (news_dir / "300308_cninfo.csv").write_text(
                "Symbol,title,content,time,source,url,type,date,announcement_id,adjunct_url,download_url,adjunct_type,adjunct_size_kb,text_excerpt,text_status,CacheSource\n"
                "300308,当日无时间公告,, ,CNInfo,http://same,,2026-04-03,1,,http://pdf,PDF,10,正文摘要,ok,unit\n",
                encoding="utf-8",
            )

            fundamentals_dir = cache_dir / "fundamentals"
            fundamentals_dir.mkdir(parents=True)
            (fundamentals_dir / "300308_eastmoney_company_info.json").write_text(
                json.dumps({"name": "中际旭创", "industry": "通信设备", "mcap": 1000000000}, ensure_ascii=False),
                encoding="utf-8",
            )

            social_dir = cache_dir / "social"
            social_dir.mkdir(parents=True)
            (social_dir / "300308_sentiment_2026-04-03.json").write_text(
                json.dumps(
                    {
                        "forum_sentiment": {"discussion_count": 0},
                        "xueqiu_sentiment": {"post_count": 0},
                        "irm_sentiment": {"irm_count": 1},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            auditor = create_data_auditor(
                config={"project_dir": str(project_dir), "run_name": "audit_evidence"},
                selected_analysts=["market", "fundamentals", "news", "social"],
            )
            result = auditor({"company_of_interest": "300308", "trade_date": "2026-04-03"})

        if old_prefetch_dir is None:
            os.environ.pop("TRADINGAGENTS_PREFETCH_DIR", None)
        else:
            os.environ["TRADINGAGENTS_PREFETCH_DIR"] = old_prefetch_dir

        self.assertIn("news", result["skip_analysts"])
        self.assertIn("usable_evidence_rows=0", result["skip_analysts"]["news"])
        self.assertNotIn("market", result["skip_analysts"])
        self.assertNotIn("fundamentals", result["skip_analysts"])
        self.assertNotIn("social", result["skip_analysts"])
        self.assertEqual(result["data_evidence_audit"]["social"]["irm_rows"], 1)
        self.assertEqual(result["data_evidence_audit"]["news"]["usable_rows"], 0)

    def test_data_auditor_skips_fundamentals_when_only_announcements_exist(self):
        from tradingagents.agents.data_auditor import create_data_auditor

        old_prefetch_dir = os.environ.get("TRADINGAGENTS_PREFETCH_DIR")
        with TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            cache_dir = Path(tmp) / "prefetch"
            os.environ["TRADINGAGENTS_PREFETCH_DIR"] = str(cache_dir)

            preflight_dir = project_dir / "outputs" / "runs" / "fundamentals_only_announcements" / "data_preflight"
            preflight_dir.mkdir(parents=True)
            (preflight_dir / "preflight_data_quality.csv").write_text(
                "ticker,signal_date,market_ok,market_rows,news_ok,news_rows,"
                "fundamentals_ok,fundamentals_rows,social_discussion_ok,"
                "social_discussion_rows,social_event_rows,all_core_ok\n"
                "601899,2025-10-03,True,25,False,0,True,1,False,0,0,True\n",
                encoding="utf-8",
            )

            market_dir = cache_dir / "market"
            market_dir.mkdir(parents=True)
            market_rows = ["Symbol,Date,Open,High,Low,Close,Volume,Source"]
            for day in range(1, 26):
                market_rows.append(f"601899,2025-09-{day:02d},10,11,9,10.5,1000,unit")
            (market_dir / "601899.csv").write_text("\n".join(market_rows), encoding="utf-8")

            fundamentals_dir = cache_dir / "fundamentals"
            fundamentals_dir.mkdir(parents=True)
            (fundamentals_dir / "601899_sina_statements.json").write_text(
                json.dumps({"income_statement": [], "balance_sheet": [], "cashflow": []}, ensure_ascii=False),
                encoding="utf-8",
            )

            news_dir = cache_dir / "news"
            news_dir.mkdir(parents=True)
            (news_dir / "601899_cninfo.csv").write_text(
                "Symbol,title,content,time,source,url,type,date,announcement_id,adjunct_url,download_url,adjunct_type,adjunct_size_kb,text_excerpt,text_status,CacheSource\n"
                "601899,治理制度,, ,CNInfo,http://same,,2025-09-30 00:00:00,1,,http://pdf,PDF,10,制度正文,ok,unit\n",
                encoding="utf-8",
            )

            auditor = create_data_auditor(
                config={"project_dir": str(project_dir), "run_name": "fundamentals_only_announcements"},
                selected_analysts=["market", "fundamentals"],
            )
            result = auditor({"company_of_interest": "601899", "trade_date": "2025-10-03"})

        if old_prefetch_dir is None:
            os.environ.pop("TRADINGAGENTS_PREFETCH_DIR", None)
        else:
            os.environ["TRADINGAGENTS_PREFETCH_DIR"] = old_prefetch_dir

        self.assertIn("fundamentals", result["skip_analysts"])
        self.assertIn("announcements are supplementary only", result["skip_analysts"]["fundamentals"])
        self.assertEqual(result["data_evidence_audit"]["fundamentals"]["usable_rows"], 0)

    def test_data_auditor_skips_fundamentals_when_company_profile_has_no_valuation_fields(self):
        from tradingagents.agents.data_auditor import create_data_auditor

        old_prefetch_dir = os.environ.get("TRADINGAGENTS_PREFETCH_DIR")
        with TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            cache_dir = Path(tmp) / "prefetch"
            os.environ["TRADINGAGENTS_PREFETCH_DIR"] = str(cache_dir)

            preflight_dir = project_dir / "outputs" / "runs" / "sparse_company_profile" / "data_preflight"
            preflight_dir.mkdir(parents=True)
            (preflight_dir / "preflight_data_quality.csv").write_text(
                "ticker,signal_date,market_ok,market_rows,news_ok,news_rows,"
                "fundamentals_ok,fundamentals_rows,social_discussion_ok,"
                "social_discussion_rows,social_event_rows,all_core_ok\n"
                "601899,2025-10-03,True,25,False,0,True,1,False,0,0,True\n",
                encoding="utf-8",
            )

            market_dir = cache_dir / "market"
            market_dir.mkdir(parents=True)
            market_rows = ["Symbol,Date,Open,High,Low,Close,Volume,Source"]
            for day in range(1, 26):
                market_rows.append(f"601899,2025-09-{day:02d},10,11,9,10.5,1000,unit")
            (market_dir / "601899.csv").write_text("\n".join(market_rows), encoding="utf-8")

            fundamentals_dir = cache_dir / "fundamentals"
            fundamentals_dir.mkdir(parents=True)
            (fundamentals_dir / "601899_eastmoney_company_info.json").write_text(
                json.dumps({"name": "紫金矿业", "industry": "有色金属"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (fundamentals_dir / "601899_sina_statements.json").write_text(
                json.dumps({"income_statement": [], "balance_sheet": [], "cashflow": []}, ensure_ascii=False),
                encoding="utf-8",
            )

            auditor = create_data_auditor(
                config={"project_dir": str(project_dir), "run_name": "sparse_company_profile"},
                selected_analysts=["market", "fundamentals"],
            )
            result = auditor({"company_of_interest": "601899", "trade_date": "2025-10-03"})

        if old_prefetch_dir is None:
            os.environ.pop("TRADINGAGENTS_PREFETCH_DIR", None)
        else:
            os.environ["TRADINGAGENTS_PREFETCH_DIR"] = old_prefetch_dir

        self.assertIn("fundamentals", result["skip_analysts"])
        self.assertEqual(result["data_evidence_audit"]["fundamentals"]["company_rows"], 0)
        self.assertEqual(result["data_evidence_audit"]["fundamentals"]["statement_rows"], 0)


if __name__ == "__main__":
    unittest.main()
