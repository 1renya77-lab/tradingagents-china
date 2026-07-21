import unittest

from prefetch_market_data import build_prefetch_start


class PrefetchMarketDataTest(unittest.TestCase):
    def test_build_prefetch_start_subtracts_lookback_days(self):
        self.assertEqual(build_prefetch_start("2026-04-01", 320), "2025-05-16")


if __name__ == "__main__":
    unittest.main()
