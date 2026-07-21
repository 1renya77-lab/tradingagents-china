import unittest

import pandas as pd

from alpha_gap_diagnostics import classify_position_gap, format_markdown, summarize_signal_windows


class AlphaGapDiagnosticsTest(unittest.TestCase):
    def test_classify_position_gap_distinguishes_upstream_and_downstream_sources(self):
        self.assertEqual(
            classify_position_gap(pd.Series({"raw_position": 0.20, "target_position": 0.20})),
            "upstream_raw_low",
        )
        self.assertEqual(
            classify_position_gap(pd.Series({"raw_position": 0.20, "target_position": 0.50})),
            "downstream_floor_raise",
        )
        self.assertEqual(
            classify_position_gap(pd.Series({"raw_position": 0.80, "target_position": 0.50})),
            "downstream_cap_reduce",
        )

    def test_summarize_signal_windows_flags_low_position_missed_upside(self):
        windows = pd.DataFrame(
            [
                {
                    "date": "2026-04-03",
                    "target_position": 0.20,
                    "stock_return": 0.12,
                    "benchmark_return": 0.02,
                    "agent_return": 0.01,
                },
                {
                    "date": "2026-04-10",
                    "target_position": 0.70,
                    "stock_return": 0.08,
                    "benchmark_return": 0.01,
                    "agent_return": 0.06,
                },
            ]
        )

        summary = summarize_signal_windows(
            windows,
            low_position_threshold=0.30,
            upside_threshold=0.05,
        )

        self.assertEqual(summary["signals"], 2)
        self.assertEqual(summary["low_position_missed_upside_cases"], 1)
        self.assertAlmostEqual(summary["low_position_missed_upside_sum"], 0.11)
        self.assertAlmostEqual(summary["mean_target_position"], 0.45)

    def test_summarize_signal_windows_flags_underallocated_alpha(self):
        windows = pd.DataFrame(
            [
                {
                    "date": "2026-04-03",
                    "target_position": 0.20,
                    "stock_return": 0.12,
                    "benchmark_return": 0.02,
                    "agent_return": 0.01,
                    "return_evidence_score": 5,
                },
                {
                    "date": "2026-04-10",
                    "target_position": 0.20,
                    "stock_return": 0.03,
                    "benchmark_return": 0.04,
                    "agent_return": 0.01,
                    "return_evidence_score": 5,
                },
                {
                    "date": "2026-04-17",
                    "target_position": 0.70,
                    "stock_return": 0.10,
                    "benchmark_return": 0.01,
                    "agent_return": 0.07,
                    "return_evidence_score": 5,
                },
            ]
        )

        summary = summarize_signal_windows(
            windows,
            low_position_threshold=0.30,
            upside_threshold=0.05,
            alpha_opportunity_threshold=0.05,
            strong_evidence_threshold=4,
        )

        self.assertEqual(summary["underallocated_alpha_cases"], 1)
        self.assertAlmostEqual(summary["underallocated_alpha_sum"], 0.11)
        self.assertEqual(summary["strong_evidence_underallocation_cases"], 1)

    def test_format_markdown_includes_underallocated_alpha_table(self):
        windows = pd.DataFrame(
            [
                {
                    "date": "2026-04-03",
                    "raw_position": 0.20,
                    "target_position": 0.20,
                    "position_gap_source": "upstream_raw_low",
                    "stock_return": 0.12,
                    "benchmark_return": 0.02,
                    "agent_return": 0.01,
                    "missed_upside": 0.11,
                    "return_evidence_score": 5,
                    "return_evidence_source": "structured",
                    "constraint_rules": "",
                }
            ]
        )
        summary = summarize_signal_windows(windows)

        markdown = format_markdown(windows, summary, "300308")

        self.assertIn("## Underallocated Alpha Cases", markdown)
        self.assertIn(
            "| 2026-04-03 | 20.00% | 20.00% | upstream_raw_low | 10.00% | -1.00% | 11.00% | 5.0 | structured |  |",
            markdown,
        )


if __name__ == "__main__":
    unittest.main()
