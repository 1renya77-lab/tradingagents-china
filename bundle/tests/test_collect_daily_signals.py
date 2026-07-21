import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import collect_daily_signals as cds


class _FailingGraph:
    def __init__(self, *args, **kwargs):
        pass

    def propagate(self, *args, **kwargs):
        raise RuntimeError("404 page not found")


class _CountingGraph:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    def propagate(self, ticker, date_str, progress_callback=None):
        self.calls.append(date_str)
        return {}, {
            "action": "持有",
            "confidence": 0.5,
            "risk_score": 0.5,
            "target_price": None,
            "reasoning": "等待确认",
        }


class CollectDailySignalsTest(unittest.TestCase):
    def test_build_signal_dates_daily_uses_business_days(self):
        dates = cds.build_signal_dates("2026-06-01", "2026-06-07", frequency="daily")
        self.assertEqual(
            [d.strftime("%Y-%m-%d") for d in dates],
            ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05"],
        )

    def test_build_signal_dates_weekly_uses_last_business_day(self):
        dates = cds.build_signal_dates("2026-06-01", "2026-06-30", frequency="weekly")
        self.assertEqual(
            [d.strftime("%Y-%m-%d") for d in dates],
            ["2026-06-05", "2026-06-12", "2026-06-19", "2026-06-26", "2026-06-30"],
        )

    def test_build_signal_filename_marks_position_execution_file(self):
        self.assertEqual(
            cds.build_signal_filename("300269", "2026-06-01", "2026-06-30", "weekly"),
            "signals_300269_2026-06-01_2026-06-30_weekly_position.csv",
        )

    def test_weekly_horizon_is_not_next_day(self):
        horizon = cds.build_horizon_config("weekly")
        self.assertEqual(horizon["signal_frequency"], "weekly")
        self.assertEqual(horizon["decision_horizon"], "next_5_trading_days")
        self.assertIn("未来5个交易日", horizon["horizon_instruction"])
        self.assertIn("不要只预测明天单日涨跌", horizon["horizon_instruction"])

    def test_daily_horizon_preserves_next_day_semantics(self):
        horizon = cds.build_horizon_config("daily")
        self.assertEqual(horizon["signal_frequency"], "daily")
        self.assertEqual(horizon["decision_horizon"], "next_trading_day")
        self.assertIn("下一交易日", horizon["horizon_instruction"])

    def test_failed_rows_are_marked_as_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "signals.csv"
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
                with patch.object(cds, "TradingAgentsGraph", _FailingGraph):
                    df = cds.collect_daily_signals(
                        ticker="300269",
                        start_date="2026-06-30",
                        end_date="2026-06-30",
                        frequency="daily",
                        selected_analysts=["market"],
                        output_file=str(output_file),
                    )

        row = df.iloc[0]
        self.assertEqual(row["action"], "持有")
        self.assertEqual(row["status"], "error")
        self.assertIn("404 page not found", row["error_message"])

    def test_existing_success_dates_only_reads_ok_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "signals.csv"
            path.write_text(
                "date,ticker,status\n"
                "2026-06-05,300269,ok\n"
                "2026-06-12,300269,error\n",
                encoding="utf-8",
            )

            dates = cds.load_existing_success_dates(path)

        self.assertEqual(dates, {"2026-06-05"})

    def test_save_progress_merges_and_deduplicates_by_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "signals.csv"
            cds.save_progress(
                path,
                [
                    {"date": "2026-06-12", "ticker": "300269", "status": "ok", "target_position": 0.5},
                    {"date": "2026-06-05", "ticker": "300269", "status": "ok", "target_position": 0.8},
                    {"date": "2026-06-12", "ticker": "300269", "status": "ok", "target_position": 0.6},
                ],
            )

            text = path.read_text(encoding="utf-8")

        self.assertIn("2026-06-05", text)
        self.assertIn("2026-06-12", text)
        self.assertIn("0.6", text)
        self.assertNotIn("0.5", text)

    def test_resume_skips_existing_ok_dates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "signals.csv"
            output_file.write_text(
                "date,ticker,status,error_message,action,confidence,risk_score,target_price,action_score,score,target_position,reasoning\n"
                "2026-06-05,300269,ok,,持有,0.5,0.5,,0.5,0.5,0.5,done\n",
                encoding="utf-8",
            )
            _CountingGraph.calls = []
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
                with patch.object(cds, "TradingAgentsGraph", _CountingGraph):
                    df = cds.collect_daily_signals(
                        ticker="300269",
                        start_date="2026-06-01",
                        end_date="2026-06-12",
                        frequency="weekly",
                        selected_analysts=["market"],
                        output_file=str(output_file),
                        resume=True,
                    )

        self.assertEqual(_CountingGraph.calls, ["2026-06-12"])
        self.assertEqual(len(df), 2)


if __name__ == "__main__":
    unittest.main()
