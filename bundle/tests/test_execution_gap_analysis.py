import unittest

import pandas as pd

from build_execution_gap_analysis import build_execution_gap_rows, summarize_execution_gap_rows


class ExecutionGapAnalysisTest(unittest.TestCase):
    def test_build_execution_gap_rows_splits_gap_and_post_execution_returns(self):
        signals = pd.DataFrame(
            [
                {"date": "2026-04-03", "target_position": 0.5, "action": "持有"},
                {"date": "2026-04-10", "target_position": 0.2, "action": "减仓"},
            ]
        )
        bars = pd.DataFrame(
            [
                {"Date": "2026-04-03", "Open": 100.0, "Close": 100.0},
                {"Date": "2026-04-07", "Open": 110.0, "Close": 112.0},
                {"Date": "2026-04-08", "Open": 112.0, "Close": 116.0},
                {"Date": "2026-04-10", "Open": 116.0, "Close": 120.0},
                {"Date": "2026-04-13", "Open": 126.0, "Close": 125.0},
                {"Date": "2026-04-14", "Open": 125.0, "Close": 130.0},
            ]
        )

        rows = build_execution_gap_rows(signals, bars, end="2026-04-14")

        self.assertEqual(len(rows), 2)
        first = rows.iloc[0]
        self.assertEqual(first["signal_date"], "2026-04-03")
        self.assertEqual(first["execution_date"], "2026-04-07")
        self.assertAlmostEqual(first["gap_return"], 0.10)
        self.assertAlmostEqual(first["post_execution_return"], 126.0 / 110.0 - 1.0)
        self.assertAlmostEqual(first["signal_to_window_return"], 126.0 / 100.0 - 1.0)
        self.assertTrue(first["cross_weekend_or_holiday"])

    def test_summarize_execution_gap_rows_reports_missed_gap_share(self):
        rows = pd.DataFrame(
            [
                {"gap_return": 0.10, "post_execution_return": 0.05, "target_position": 0.5},
                {"gap_return": -0.02, "post_execution_return": 0.03, "target_position": 0.2},
            ]
        )

        summary = summarize_execution_gap_rows(rows)

        self.assertEqual(summary["signals"], 2)
        self.assertAlmostEqual(summary["positive_gap_cases"], 1)
        self.assertAlmostEqual(summary["mean_gap_return"], 0.04)


if __name__ == "__main__":
    unittest.main()
