import unittest

from inspect_memory_log import format_memory_rows


class InspectMemoryLogTest(unittest.TestCase):
    def test_formats_pending_and_resolved_entries(self):
        entries = [
            {
                "date": "2026-06-30",
                "ticker": "300269",
                "rating": "Sell",
                "pending": False,
                "raw": "-0.4%",
                "alpha": "+2.8%",
                "holding": "3d",
                "reflection": "方向判断正确。",
            },
            {
                "date": "2026-07-03",
                "ticker": "300269",
                "rating": "Sell",
                "pending": True,
                "raw": None,
                "alpha": None,
                "holding": None,
                "reflection": "",
            },
        ]

        rows = format_memory_rows(entries)

        self.assertIn("2026-06-30", rows)
        self.assertIn("resolved", rows)
        self.assertIn("+2.8%", rows)
        self.assertIn("yes", rows)
        self.assertIn("pending", rows)
        self.assertIn("no", rows)


if __name__ == "__main__":
    unittest.main()
