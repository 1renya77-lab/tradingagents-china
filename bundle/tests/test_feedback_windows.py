import unittest

import pandas as pd

from build_feedback_windows import classify_case_type, score_decision_quality


class FeedbackWindowsTest(unittest.TestCase):
    def test_feedback_window_case_types(self):
        self.assertEqual(
            classify_case_type(pd.Series({"target_position": 0.80, "stock_return": 0.08, "agent_return": 0.06})),
            "success_attack",
        )
        self.assertEqual(
            classify_case_type(pd.Series({"target_position": 0.10, "stock_return": -0.06, "agent_return": -0.01})),
            "success_defense",
        )
        self.assertEqual(
            classify_case_type(pd.Series({"target_position": 0.10, "stock_return": 0.07, "agent_return": 0.01})),
            "missed_upside",
        )
        self.assertEqual(
            classify_case_type(pd.Series({"target_position": 0.80, "stock_return": -0.07, "agent_return": -0.06})),
            "wrong_exposure",
        )

    def test_decision_quality_rewards_directional_alignment(self):
        good_attack = score_decision_quality(
            pd.Series({"target_position": 0.80, "stock_return": 0.10, "agent_return": 0.08, "benchmark_return": 0.02})
        )
        missed = score_decision_quality(
            pd.Series({"target_position": 0.10, "stock_return": 0.10, "agent_return": 0.01, "benchmark_return": 0.02})
        )
        good_defense = score_decision_quality(
            pd.Series({"target_position": 0.10, "stock_return": -0.08, "agent_return": -0.01, "benchmark_return": 0.00})
        )
        wrong = score_decision_quality(
            pd.Series({"target_position": 0.80, "stock_return": -0.08, "agent_return": -0.07, "benchmark_return": 0.00})
        )

        self.assertGreater(good_attack, missed)
        self.assertGreater(good_defense, wrong)


if __name__ == "__main__":
    unittest.main()
