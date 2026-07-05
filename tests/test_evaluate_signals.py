import unittest

import pandas as pd

from evaluate_signals import build_summary, format_markdown_summary


class EvaluateSignalsTest(unittest.TestCase):
    def test_build_summary_counts_actions_and_returns(self):
        df = pd.DataFrame(
            [
                {
                    "date": "2026-06-30",
                    "ticker": "300269",
                    "action": "卖出",
                    "confidence": 0.7,
                    "risk_score": 0.5,
                    "score": 0.2375,
                    "forward_return": -0.004,
                    "benchmark_return": -0.032,
                    "alpha": 0.028,
                    "decision_alpha": -0.028,
                    "directional_hit": False,
                },
                {
                    "date": "2026-07-01",
                    "ticker": "300269",
                    "action": "卖出",
                    "confidence": 0.9,
                    "risk_score": 0.8,
                    "score": 0.095,
                    "forward_return": -0.110,
                    "benchmark_return": -0.031,
                    "alpha": -0.079,
                    "decision_alpha": 0.079,
                    "directional_hit": True,
                },
            ]
        )

        summary = build_summary(df)

        self.assertEqual(summary["rows"], 2)
        self.assertEqual(summary["action_counts"]["卖出"], 2)
        self.assertAlmostEqual(summary["avg_confidence"], 0.8)
        self.assertAlmostEqual(summary["avg_alpha"], -0.0255)
        self.assertAlmostEqual(summary["avg_decision_alpha"], 0.0255)
        self.assertAlmostEqual(summary["directional_hit_rate"], 0.5)
        self.assertAlmostEqual(summary["cumulative_return"], -0.11356)

    def test_format_markdown_summary_contains_core_metrics(self):
        summary = {
            "name": "case",
            "rows": 2,
            "action_counts": {"卖出": 2},
            "avg_confidence": 0.8,
            "avg_risk_score": 0.65,
            "avg_score": 0.1663,
            "avg_forward_return": -0.057,
            "avg_benchmark_return": -0.0315,
            "avg_alpha": -0.0255,
            "avg_decision_alpha": 0.0255,
            "cumulative_return": -0.11356,
            "max_drawdown": -0.110,
            "win_rate": 0.0,
            "directional_hit_rate": 0.5,
        }

        text = format_markdown_summary([summary])

        self.assertIn("case", text)
        self.assertIn("avg_alpha", text)
        self.assertIn("decision_alpha", text)
        self.assertIn("卖出:2", text)


if __name__ == "__main__":
    unittest.main()
