import tempfile
import unittest
from pathlib import Path

import pandas as pd

from compare_baselines import build_buy_and_hold_signals, format_comparison_markdown


class CompareBaselinesTest(unittest.TestCase):
    def test_build_buy_and_hold_signals_only_uses_first_agent_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "agent.csv"
            output = Path(tmpdir) / "baseline.csv"
            pd.DataFrame(
                [
                    {"date": "2026-04-03", "ticker": "300750", "target_position": 0.2},
                    {"date": "2026-04-10", "ticker": "300750", "target_position": 0.4},
                ]
            ).to_csv(source, index=False)

            result = build_buy_and_hold_signals(
                source_signals=source,
                output_path=output,
                target_position=1.0,
                strategy_name="buy_hold_100",
            )

            df = pd.read_csv(result)

        self.assertEqual(list(df["date"]), ["2026-04-03"])
        self.assertEqual([str(value) for value in df["ticker"]], ["300750"])
        self.assertEqual(list(df["action"]), ["买入并持有"])
        self.assertEqual(list(df["target_position"]), [1.0])
        self.assertIn("buy_hold_100", df["reasoning"].iloc[0])
        self.assertIn("initial target_position=1.00", df["reasoning"].iloc[0])

    def test_format_comparison_markdown_contains_core_metrics(self):
        metrics = pd.DataFrame(
            [
                {
                    "strategy": "agent",
                    "total_return": 0.10,
                    "annual_return": 0.50,
                    "sharpe": 1.2,
                    "max_drawdown": -0.05,
                    "turnover_sum": 0.8,
                    "trades": 4,
                },
                {
                    "strategy": "buy_hold_100",
                    "total_return": 0.20,
                    "annual_return": 1.10,
                    "sharpe": 1.0,
                    "max_drawdown": -0.12,
                    "turnover_sum": 1.0,
                    "trades": 1,
                },
            ]
        )

        text = format_comparison_markdown(metrics, ticker="300750")

        self.assertIn("300750", text)
        self.assertIn("agent", text)
        self.assertIn("buy_hold_100", text)
        self.assertIn("10.00%", text)
        self.assertIn("Sharpe", text)


if __name__ == "__main__":
    unittest.main()
