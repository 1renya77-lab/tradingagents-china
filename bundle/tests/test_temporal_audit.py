import unittest
import tempfile
from pathlib import Path

import pandas as pd

from tradingagents.dataflows.china_research import _filter_by_date
from tradingagents.tools.unified_news_tool import UnifiedNewsAnalyzer
from tradingagents.utils.temporal_audit import audit_temporal_integrity


class TemporalAuditTest(unittest.TestCase):
    def test_financial_rows_without_dates_are_excluded(self):
        df = pd.DataFrame([{"metric": "roe", "value": 10.0}])

        filtered = _filter_by_date(df, "2026-01-01")

        self.assertTrue(filtered.empty)

    def test_financial_rows_after_cutoff_are_excluded(self):
        df = pd.DataFrame(
            [
                {"公告日期": "2026-01-02", "metric": "future"},
                {"公告日期": "2025-12-31", "metric": "known"},
            ]
        )

        filtered = _filter_by_date(df, "2026-01-01")

        self.assertEqual(filtered["metric"].tolist(), ["known"])

    def test_news_without_publish_time_or_after_cutoff_is_excluded(self):
        analyzer = UnifiedNewsAnalyzer(toolkit=None)
        items = [
            {"title": "undated"},
            {"title": "future", "publish_time": "2026-01-02 09:00:00"},
            {"title": "known", "publish_time": "2026-01-01 15:00:00"},
        ]

        filtered = analyzer._filter_items_by_curr_date(items, "2026-01-01")

        self.assertEqual([item["title"] for item in filtered], ["known"])

    def test_run_temporal_audit_flags_future_published_line(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run"
            report_dir = run_dir / "reports"
            report_dir.mkdir(parents=True)
            (report_dir / "report_300308_2026-04-03.md").write_text(
                "Published: 2026-04-04 09:00:00\n",
                encoding="utf-8",
            )

            result = audit_temporal_integrity(run_dir)

        self.assertEqual(result["verdict"], "fail")
        self.assertEqual(result["issue_count"], 1)

    def test_run_temporal_audit_ignores_generation_time(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run"
            report_dir = run_dir / "reports"
            report_dir.mkdir(parents=True)
            (report_dir / "report_300308_2026-04-03.md").write_text(
                "报告生成时间: 2026-07-07 10:00:00\nPublished: 2026-04-03 15:00:00\n",
                encoding="utf-8",
            )

            result = audit_temporal_integrity(run_dir)

        self.assertEqual(result["verdict"], "pass")

    def test_run_temporal_audit_counts_missing_timestamp_and_rule_mentions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run"
            report_dir = run_dir / "reports"
            report_dir.mkdir(parents=True)
            (report_dir / "report_300308_2026-04-03.md").write_text(
                "TEMPORAL_RULE: only publish_time/disclosure_date <= cutoff_date are used; "
                "undated rows are excluded.\n",
                encoding="utf-8",
            )

            result = audit_temporal_integrity(run_dir)

        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["missing_timestamp_mentions"], 1)
        self.assertEqual(result["temporal_rule_mentions"], 1)


if __name__ == "__main__":
    unittest.main()
