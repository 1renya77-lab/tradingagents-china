import unittest
from pathlib import Path

from run_experiment import build_signal_output_path, normalize_experiment_config


class RunExperimentTest(unittest.TestCase):
    def test_build_signal_output_path_uses_run_scope(self):
        path = build_signal_output_path(
            bundle_root=Path("/tmp/bundle"),
            run_name="baseline_v1",
            ticker="300269",
            start_date="2026-06-30",
            end_date="2026-07-03",
        )
        self.assertEqual(
            path,
            Path("/tmp/bundle").resolve()
            / "outputs"
            / "runs"
            / "baseline_v1"
            / "signals"
            / "signals_300269_2026-06-30_2026-07-03_daily_position.csv",
        )

    def test_normalize_experiment_config_applies_defaults(self):
        cfg = normalize_experiment_config(
            {
                "run_name": "with_memory",
                "stocks": [{"ticker": "300269", "start": "2026-06-30", "end": "2026-07-03"}],
            }
        )
        self.assertEqual(cfg["provider"], "deepseek")
        self.assertEqual(cfg["quick_model"], "deepseek-v4-flash")
        self.assertEqual(cfg["deep_model"], "deepseek-v4-flash")
        self.assertEqual(cfg["analysts"], ["market", "news", "social", "fundamentals"])
        self.assertEqual(cfg["stocks"][0]["ticker"], "300269")


if __name__ == "__main__":
    unittest.main()
