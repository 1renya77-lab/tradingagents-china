import tempfile
import unittest
from pathlib import Path

from tradingagents.agents.utils.memory_log import TradingMemoryLog


class TradingMemoryLogTest(unittest.TestCase):
    def test_stores_resolves_and_formats_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "decision_memory.md"
            memory_log = TradingMemoryLog({"memory_log_path": str(log_path)})

            memory_log.store_decision(
                ticker="300269",
                trade_date="2026-06-30",
                final_trade_decision="评级：Buy\n依据：放量突破。",
            )

            pending = memory_log.get_pending_entries()
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["ticker"], "300269")
            self.assertIs(pending[0]["pending"], True)

            memory_log.update_with_outcome(
                ticker="300269",
                trade_date="2026-06-30",
                raw_return=0.034,
                alpha_return=0.021,
                holding_days=1,
                reflection="方向判断正确，alpha 为 +2.1%。下次继续要求成交量和价格结构互相确认。",
            )

            entries = memory_log.load_entries()
            self.assertIs(entries[0]["pending"], False)
            self.assertEqual(entries[0]["raw"], "+3.4%")
            self.assertEqual(entries[0]["alpha"], "+2.1%")

            context = memory_log.get_past_context("300269")
            self.assertIn("Past analyses of 300269", context)
            self.assertIn("评级：Buy", context)
            self.assertIn("方向判断正确", context)

    def test_does_not_duplicate_pending_decisions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "decision_memory.md"
            memory_log = TradingMemoryLog({"memory_log_path": str(log_path)})

            for _ in range(2):
                memory_log.store_decision(
                    ticker="300269",
                    trade_date="2026-06-30",
                    final_trade_decision="评级：Hold",
                )

            self.assertEqual(len(memory_log.get_pending_entries()), 1)


if __name__ == "__main__":
    unittest.main()
