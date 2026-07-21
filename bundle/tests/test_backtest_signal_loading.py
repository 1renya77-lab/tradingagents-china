import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest_existing_signals_qlib import load_signal_csv


class BacktestSignalLoadingTest(unittest.TestCase):
    def test_load_signal_csv_prefers_target_position_when_available(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "signals.csv"
            pd.DataFrame(
                [
                    {
                        "date": "2026-04-03",
                        "ticker": "300750",
                        "score": 0.5,
                        "target_position": 0.35,
                    }
                ]
            ).to_csv(path, index=False)

            signal = load_signal_csv(path, "300750")

        self.assertEqual(signal.name, "target_position")
        self.assertAlmostEqual(float(signal.iloc[0]), 0.35)


if __name__ == "__main__":
    unittest.main()
