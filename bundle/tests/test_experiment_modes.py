import unittest

from tradingagents.experiment_modes import EXPERIMENT_MODES, resolve_experiment_mode


class ExperimentModesTest(unittest.TestCase):
    def test_experiment_mode_config_maps_three_study_modes(self):
        self.assertEqual(
            set(EXPERIMENT_MODES),
            {"single_llm_direct", "multi_agent_no_debate", "multi_agent_full_debate"},
        )

        single = resolve_experiment_mode("single_llm_direct")
        self.assertEqual(single.selected_analysts, ["market", "fundamentals", "news", "social"])
        self.assertTrue(single.single_llm_direct_enabled)
        self.assertFalse(single.enable_investment_debate)
        self.assertFalse(single.enable_risk_debate)

        no_debate = resolve_experiment_mode("multi_agent_no_debate")
        self.assertEqual(no_debate.selected_analysts, ["market", "fundamentals", "news", "social"])
        self.assertFalse(no_debate.single_llm_direct_enabled)
        self.assertFalse(no_debate.enable_investment_debate)
        self.assertFalse(no_debate.enable_risk_debate)

        full = resolve_experiment_mode("multi_agent_full_debate")
        self.assertEqual(full.selected_analysts, ["market", "fundamentals", "news", "social"])
        self.assertFalse(full.single_llm_direct_enabled)
        self.assertTrue(full.enable_investment_debate)
        self.assertTrue(full.enable_risk_debate)

    def test_unknown_experiment_mode_fails_fast(self):
        with self.assertRaises(ValueError):
            resolve_experiment_mode("market_only")


if __name__ == "__main__":
    unittest.main()
