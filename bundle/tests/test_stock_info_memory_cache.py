import unittest
from unittest.mock import Mock, patch
from tempfile import TemporaryDirectory
from pathlib import Path

from tradingagents.dataflows.data_source_manager import ChinaDataSource, DataSourceManager


class StockInfoMemoryCacheTest(unittest.TestCase):
    def test_get_stock_info_reuses_valid_result_in_process(self):
        manager = DataSourceManager.__new__(DataSourceManager)
        manager.current_source = ChinaDataSource.AKSHARE
        manager._stock_info_memory_cache = {}
        manager.get_data_adapter = Mock(return_value=None)
        manager._get_local_artifact_stock_info = Mock(return_value={})
        manager._try_fallback_stock_info = Mock(
            return_value={
                "symbol": "300308",
                "name": "中际旭创",
                "source": "baostock",
            }
        )

        with patch(
            "tradingagents.config.runtime_settings.use_app_cache_enabled",
            return_value=False,
        ):
            first = manager.get_stock_info("300308")
            second = manager.get_stock_info("300308")

        self.assertEqual(first["name"], "中际旭创")
        self.assertEqual(second["name"], "中际旭创")
        manager._try_fallback_stock_info.assert_called_once_with("300308")

    def test_get_stock_info_uses_local_artifact_cache_before_remote_sources(self):
        manager = DataSourceManager.__new__(DataSourceManager)
        manager.current_source = ChinaDataSource.AKSHARE
        manager._stock_info_memory_cache = {}
        manager.get_data_adapter = Mock(return_value=None)
        manager._try_fallback_stock_info = Mock()

        with TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            report_dir = repo_root / "outputs" / "runs" / "demo" / "reports"
            report_dir.mkdir(parents=True)
            (report_dir / "report_300308_2026-05-08.md").write_text(
                "# 中际旭创（300308）技术分析报告\n所属行业: 通信设备\n上市日期: 2012-04-10\n",
                encoding="utf-8",
            )

            with patch(
                "tradingagents.dataflows.data_source_manager.REPO_ROOT",
                repo_root,
            ):
                result = manager.get_stock_info("300308")

        self.assertEqual(result["name"], "中际旭创")
        self.assertEqual(result["industry"], "通信设备")
        self.assertEqual(result["list_date"], "2012-04-10")
        self.assertEqual(result["source"], "local_artifact_cache")
        manager._try_fallback_stock_info.assert_not_called()


if __name__ == "__main__":
    unittest.main()
