import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd


class StrategyBaselinesTest(unittest.TestCase):
    def test_build_rule_baseline_signals_uses_prefetch_market_cache(self):
        from strategy_baselines import build_rule_baseline_signals
        from tradingagents.dataflows.local_prefetch_cache import save_market_data

        with TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"TRADINGAGENTS_PREFETCH_DIR": tmpdir}):
                dates = pd.date_range("2026-01-01", periods=90, freq="B")
                market = pd.DataFrame(
                    {
                        "Date": dates,
                        "Open": range(100, 100 + len(dates)),
                        "High": range(101, 101 + len(dates)),
                        "Low": range(99, 99 + len(dates)),
                        "Close": range(100, 100 + len(dates)),
                        "Volume": [100000] * len(dates),
                    }
                )
                save_market_data("300308", market, source="unit")

                root = Path(tmpdir)
                signal_path = root / "signals.csv"
                pd.DataFrame(
                    {
                        "date": ["2026-03-20", "2026-03-27", "2026-04-03"],
                        "ticker": ["300308", "300308", "300308"],
                    }
                ).to_csv(signal_path, index=False)

                outputs = build_rule_baseline_signals(
                    source_signals=signal_path,
                    ticker="300308",
                    provider_uri="unused",
                    output_dir=root / "out",
                )

                self.assertEqual(set(outputs), {"macd", "kdj_rsi", "zmr", "sma"})
                sample = pd.read_csv(outputs["sma"])
                self.assertEqual(len(sample), 3)
                self.assertIn("target_position", sample.columns)
                self.assertIn("reasoning", sample.columns)

    def test_build_strategy_comparison_table_outputs_files(self):
        from build_strategy_comparison_table import build_strategy_comparison_table

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            comparison_csv = root / "comparison.csv"
            pd.DataFrame(
                [
                    {"strategy": "buy_hold_100", "total_return": 0.10, "annual_return": 0.25, "sharpe": 1.2, "max_drawdown": -0.08, "win_rate": 0.55},
                    {"strategy": "macd", "total_return": 0.05, "annual_return": 0.12, "sharpe": 0.8, "max_drawdown": -0.04, "win_rate": 0.45},
                    {"strategy": "agent", "total_return": 0.18, "annual_return": 0.40, "sharpe": 1.6, "max_drawdown": -0.03, "win_rate": 0.60},
                ]
            ).to_csv(comparison_csv, index=False)

            outputs = build_strategy_comparison_table(
                comparison_csv=comparison_csv,
                output_dir=root,
                ticker="300308",
            )

            self.assertTrue(Path(outputs["csv"]).exists())
            self.assertTrue(Path(outputs["md"]).exists())
            self.assertTrue(Path(outputs["png"]).exists())
            table = pd.read_csv(outputs["csv"])
            self.assertIn("WR%↑", table.columns)
            self.assertAlmostEqual(float(table.loc[table["Models"] == "TradingAgents", "WR%↑"].iloc[0]), 60.00)

    def test_compute_daily_win_rate_ignores_flat_days(self):
        from compare_baselines import compute_daily_win_rate

        report = pd.DataFrame({"return": [0.0, 0.02, -0.01, 0.0, 0.03]})

        self.assertAlmostEqual(compute_daily_win_rate(report), 2 / 3)


if __name__ == "__main__":
    unittest.main()
