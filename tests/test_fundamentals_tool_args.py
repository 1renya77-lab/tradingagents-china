import unittest

from tradingagents.agents.analysts.fundamentals_analyst import _coerce_fundamentals_tool_args


class FundamentalsToolArgsTest(unittest.TestCase):
    def test_missing_or_none_dates_are_replaced_with_analysis_window(self):
        tool_call = {
            "name": "get_stock_fundamentals_unified",
            "args": {
                "ticker": "300269",
                "start_date": None,
                "end_date": None,
                "curr_date": None,
            },
        }

        _coerce_fundamentals_tool_args(
            tool_call,
            ticker="300269",
            start_date="2025-12-22",
            current_date="2026-01-01",
        )

        self.assertEqual(tool_call["args"]["start_date"], "2025-12-22")
        self.assertEqual(tool_call["args"]["end_date"], "2026-01-01")
        self.assertEqual(tool_call["args"]["curr_date"], "2026-01-01")

    def test_existing_valid_dates_are_preserved(self):
        tool_call = {
            "name": "get_stock_fundamentals_unified",
            "args": {
                "ticker": "300269",
                "start_date": "2025-12-01",
                "end_date": "2025-12-31",
                "curr_date": "2025-12-31",
            },
        }

        _coerce_fundamentals_tool_args(
            tool_call,
            ticker="300269",
            start_date="2025-12-22",
            current_date="2026-01-01",
        )

        self.assertEqual(tool_call["args"]["start_date"], "2025-12-01")
        self.assertEqual(tool_call["args"]["end_date"], "2025-12-31")
        self.assertEqual(tool_call["args"]["curr_date"], "2025-12-31")


if __name__ == "__main__":
    unittest.main()
