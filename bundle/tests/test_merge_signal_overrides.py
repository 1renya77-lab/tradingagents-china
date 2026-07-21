import unittest

import pandas as pd

from merge_signal_overrides import merge_signal_overrides


class MergeSignalOverridesTest(unittest.TestCase):
    def test_override_replaces_matching_date_and_ticker(self):
        base = pd.DataFrame(
            [
                {"date": "2025-07-04", "ticker": "300308", "target_position": 0.0, "action": "卖出"},
                {"date": "2025-07-11", "ticker": "300308", "target_position": 0.75, "action": "持有"},
            ]
        )
        override = pd.DataFrame(
            [
                {"date": "2025-07-04", "ticker": "300308", "target_position": 0.45, "action": "持有"},
            ]
        )

        out = merge_signal_overrides(base, [override])

        row = out[out["date"] == "2025-07-04"].iloc[0]
        self.assertAlmostEqual(float(row["target_position"]), 0.45)
        self.assertEqual(row["action"], "持有")

    def test_override_appends_when_row_does_not_exist(self):
        base = pd.DataFrame(
            [{"date": "2025-07-04", "ticker": "300308", "target_position": 0.0, "action": "卖出"}]
        )
        override = pd.DataFrame(
            [{"date": "2025-07-11", "ticker": "300308", "target_position": 0.45, "action": "持有"}]
        )

        out = merge_signal_overrides(base, [override])

        self.assertEqual(len(out), 2)
        self.assertTrue(((out["date"] == "2025-07-11") & (out["ticker"] == "300308")).any())


if __name__ == "__main__":
    unittest.main()
