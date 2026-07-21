import unittest

import pandas as pd

from alpha_recalibration_compare import add_implied_return_columns, build_delta_table, summarize_version


class AlphaRecalibrationCompareTest(unittest.TestCase):
    def test_add_implied_return_columns_uses_cash_plus_stock_mix(self):
        windows = pd.DataFrame(
            [
                {
                    "date": "2026-04-03",
                    "target_position": 0.40,
                    "stock_return": 0.10,
                    "benchmark_return": 0.02,
                }
            ]
        )

        out = add_implied_return_columns(windows)

        self.assertAlmostEqual(out.loc[0, "implied_return"], 0.052)
        self.assertAlmostEqual(out.loc[0, "implied_excess"], 0.032)
        self.assertAlmostEqual(out.loc[0, "capture_ratio"], 0.40)

    def test_summarize_version_reports_capture_on_positive_windows(self):
        windows = pd.DataFrame(
            [
                {
                    "date": "2026-04-03",
                    "target_position": 0.20,
                    "stock_return": 0.10,
                    "benchmark_return": 0.00,
                    "implied_return": 0.02,
                    "implied_excess": 0.02,
                    "capture_ratio": 0.20,
                },
                {
                    "date": "2026-04-10",
                    "target_position": 0.60,
                    "stock_return": -0.05,
                    "benchmark_return": 0.00,
                    "implied_return": -0.03,
                    "implied_excess": -0.03,
                    "capture_ratio": 0.60,
                },
            ]
        )

        summary = summarize_version("test", windows)

        self.assertEqual(summary["signals"], 2)
        self.assertEqual(summary["positive_stock_windows"], 1)
        self.assertAlmostEqual(summary["mean_capture_on_positive_windows"], 0.20)

    def test_build_delta_table_compares_old_and_new_versions(self):
        old = pd.DataFrame(
            [
                {
                    "date": "2026-04-03",
                    "execution_date": "2026-04-07",
                    "window_end": "2026-04-10",
                    "target_position": 0.20,
                    "stock_return": 0.10,
                    "benchmark_return": 0.00,
                    "implied_return": 0.02,
                    "implied_excess": 0.02,
                }
            ]
        )
        new = pd.DataFrame(
            [
                {
                    "date": "2026-04-03",
                    "target_position": 0.40,
                    "implied_return": 0.04,
                    "implied_excess": 0.04,
                    "position_gap_source": "structured_trend_participation_floor",
                    "return_evidence_score": 2,
                    "return_evidence_source": "structured",
                    "constraint_rules": "structured_trend_participation_floor",
                }
            ]
        )

        delta = build_delta_table(old, new)

        self.assertAlmostEqual(delta.loc[0, "position_delta"], 0.20)
        self.assertAlmostEqual(delta.loc[0, "implied_excess_delta"], 0.02)
        self.assertEqual(delta.loc[0, "position_gap_source"], "structured_trend_participation_floor")


if __name__ == "__main__":
    unittest.main()
