import json
import tempfile
import unittest
from pathlib import Path

from tradingagents.utils.provenance import collect_run_provenance


class ProvenanceTest(unittest.TestCase):
    def test_collects_structured_headers_and_time_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run"
            audit_dir = run_dir / "audit_reports"
            audit_dir.mkdir(parents=True)
            payload = {
                "input_state": {
                    "news_report": (
                        "DATA_QUALITY: ok=true\n"
                        "DATA_SOURCE: a-stock-data\n"
                        "DATA_VENDOR: EastMoney + CNInfo\n"
                        "DATA_ROWS: 2\n"
                        "DATA_CUTOFF_DATE: 2026-04-03\n"
                        "Published: 2026-04-03 10:00:00\n"
                    )
                }
            }
            (audit_dir / "audit_300308_2026-04-03.json").write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )

            result = collect_run_provenance(run_dir)

            self.assertEqual(result["records"], 1)
            news_records = json.loads((run_dir / "provenance" / "news_sources.json").read_text(encoding="utf-8"))
            self.assertEqual(news_records[0]["source"], "a-stock-data")
            self.assertEqual(news_records[0]["time_evidence"][0]["parsed_time"], "2026-04-03 10:00:00")


if __name__ == "__main__":
    unittest.main()
