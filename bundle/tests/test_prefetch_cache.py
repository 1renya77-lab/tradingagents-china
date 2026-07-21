import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd


class PrefetchCacheTest(unittest.TestCase):
    def test_market_slice_excludes_rows_after_requested_end_date(self):
        from tradingagents.dataflows.local_prefetch_cache import (
            load_market_slice,
            save_market_data,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"TRADINGAGENTS_PREFETCH_DIR": tmpdir}):
                save_market_data(
                    "300308",
                    pd.DataFrame(
                        [
                            {"Date": "2026-04-03", "Open": 10, "High": 11, "Low": 9, "Close": 10, "Volume": 100},
                            {"Date": "2026-04-10", "Open": 12, "High": 13, "Low": 11, "Close": 12, "Volume": 120},
                            {"Date": "2026-04-17", "Open": 14, "High": 15, "Low": 13, "Close": 14, "Volume": 140},
                        ]
                    ),
                    source="unit",
                )

                sliced = load_market_slice("300308", "2026-04-01", "2026-04-10")

        self.assertIsNotNone(sliced)
        self.assertEqual([d.strftime("%Y-%m-%d") for d in sliced["Date"]], ["2026-04-03", "2026-04-10"])

    def test_china_fetch_hist_uses_prefetch_cache_without_live_vendor(self):
        from tradingagents.dataflows.local_prefetch_cache import save_market_data
        from tradingagents.dataflows import china_akshare

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"TRADINGAGENTS_PREFETCH_DIR": tmpdir}):
                save_market_data(
                    "300308",
                    pd.DataFrame(
                        [
                            {"Date": "2026-04-01", "Open": 10, "High": 11, "Low": 9, "Close": 10, "Volume": 100},
                            {"Date": "2026-04-02", "Open": 12, "High": 13, "Low": 11, "Close": 12, "Volume": 120},
                        ]
                    ),
                    source="unit",
                )

                with patch.object(china_akshare, "_fetch_hist_akshare", side_effect=AssertionError("live fetch called")):
                    with patch.object(china_akshare, "_fetch_hist_baostock", side_effect=AssertionError("live fetch called")):
                        df = china_akshare._fetch_hist("300308", "2026-04-01", "2026-04-02")

        self.assertEqual(len(df), 2)
        self.assertEqual(df["Date"].max().strftime("%Y-%m-%d"), "2026-04-02")


if __name__ == "__main__":
    unittest.main()
