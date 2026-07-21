import tempfile
import unittest
from pathlib import Path

import pandas as pd

from tradingagents.utils.position_alignment import audit_position_alignment


class PositionAlignmentAuditTest(unittest.TestCase):
    def test_alignment_passes_when_execution_interval_weight_matches_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            signals = root / "signals_300308_2026-04-01_2026-04-10_weekly_position.csv"
            positions = root / "positions.csv"
            pd.DataFrame(
                [
                    {"date": "2026-04-03", "status": "ok", "target_position": 0.3},
                ]
            ).to_csv(signals, index=False)
            pd.DataFrame(
                [
                    {"datetime": "2026-04-03", "SZ300308.weight": 0.0},
                    {"datetime": "2026-04-07", "SZ300308.weight": 0.301},
                ]
            ).to_csv(positions, index=False)

            result = audit_position_alignment(
                signals_path=signals,
                positions_path=positions,
                output_dir=root / "audit",
            )

        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["flagged_rows"], 0)

    def test_alignment_fails_when_weight_deviates_beyond_tolerance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            signals = root / "signals_601899_2026-04-01_2026-04-10_weekly_position.csv"
            positions = root / "positions.csv"
            pd.DataFrame(
                [
                    {"date": "2026-04-03", "status": "ok", "target_position": 0.2},
                ]
            ).to_csv(signals, index=False)
            pd.DataFrame(
                [
                    {"datetime": "2026-04-03", "SH601899.weight": 0.0},
                    {"datetime": "2026-04-07", "SH601899.weight": 0.5},
                ]
            ).to_csv(positions, index=False)

            result = audit_position_alignment(
                signals_path=signals,
                positions_path=positions,
                output_dir=root / "audit",
            )

        self.assertEqual(result["verdict"], "fail")
        self.assertEqual(result["flagged_rows"], 1)

    def test_later_signal_inside_execution_gap_supersedes_earlier_signal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            signals = root / "signals_300308_2026-02-01_2026-02-28_weekly_position.csv"
            positions = root / "positions.csv"
            pd.DataFrame(
                [
                    {"date": "2026-02-13", "status": "ok", "target_position": 0.5},
                    {"date": "2026-02-20", "status": "ok", "target_position": 0.15},
                ]
            ).to_csv(signals, index=False)
            pd.DataFrame(
                [
                    {"datetime": "2026-02-13", "SZ300308.weight": 0.0},
                    {"datetime": "2026-02-24", "SZ300308.weight": 0.151},
                ]
            ).to_csv(positions, index=False)

            result = audit_position_alignment(
                signals_path=signals,
                positions_path=positions,
                output_dir=root / "audit",
            )

            details = pd.read_csv(root / "audit" / "position_alignment_details.csv")

        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["flagged_rows"], 0)
        checked = details[details["status"] == "checked"]
        superseded = details[details["status"] == "skipped_superseded_in_window"]
        self.assertEqual(len(checked), 1)
        self.assertEqual(checked.iloc[0]["signal_date"], "2026-02-20")
        self.assertEqual(len(superseded), 1)
        self.assertEqual(superseded.iloc[0]["signal_date"], "2026-02-13")


if __name__ == "__main__":
    unittest.main()
