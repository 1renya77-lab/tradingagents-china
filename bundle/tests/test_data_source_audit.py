import json
import tempfile
import unittest
from pathlib import Path

from tradingagents.utils.data_source_audit import audit_data_sources


class DataSourceAuditTest(unittest.TestCase):
    def test_extracts_structured_data_source_headers_from_audit_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run"
            audit_dir = run_dir / "audit_reports"
            audit_dir.mkdir(parents=True)
            payload = {
                "input_state": {
                    "news_report": (
                        "DATA_QUALITY: ok=true\n"
                        "DATA_SOURCE: a-stock-data\n"
                        "DATA_VENDOR: EastMoney stock news + CNInfo announcements\n"
                        "ROWS: 3\n"
                        "CUTOFF_DATE: 2026-04-03\n"
                    )
                }
            }
            (audit_dir / "audit_300308_2026-04-03.json").write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )

            result = audit_data_sources(run_dir)

        self.assertEqual(result["structured_records"], 1)
        self.assertEqual(result["summary"][0]["component"], "news")
        self.assertIn("a-stock-data", result["summary"][0]["sources"])

    def test_records_unstructured_artifacts_instead_of_fabricating_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run"
            report_dir = run_dir / "reports"
            report_dir.mkdir(parents=True)
            (report_dir / "report_300308_2026-04-03.md").write_text(
                "这是一份没有机器可读 DATA_SOURCE 头的自然语言报告。",
                encoding="utf-8",
            )

            result = audit_data_sources(run_dir)

        self.assertEqual(result["structured_records"], 0)
        self.assertEqual(result["inferred_records"], 0)
        self.assertEqual(result["unstructured_records"], 1)

    def test_marks_old_artifact_source_mentions_as_inferred(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run"
            report_dir = run_dir / "reports"
            report_dir.mkdir(parents=True)
            (report_dir / "report_601899_2026-04-17.md").write_text(
                "**数据来源**：AkShare/BaoStock\n"
                "新闻数据来源为东方财富股票新闻与巨潮资讯公告。",
                encoding="utf-8",
            )

            result = audit_data_sources(run_dir)

        self.assertEqual(result["structured_records"], 0)
        self.assertGreaterEqual(result["inferred_records"], 3)
        self.assertEqual(result["unstructured_records"], 0)
        sources = "; ".join(row["sources"] for row in result["summary"])
        self.assertIn("AkShare", sources)
        self.assertIn("BaoStock", sources)
        self.assertIn("EastMoney", sources)


if __name__ == "__main__":
    unittest.main()
