"""
China A-share only data interface

完全使用 akshare，不依赖 yfinance
"""

import sys
from pathlib import Path

# 临时屏蔽 yfinance 导入错误
class YFinanceBlocker:
    """阻止 yfinance 导入，避免版本冲突"""
    def __init__(self, real_import):
        self.real_import = real_import

    def __getattr__(self, name):
        if name == 'exceptions':
            class FakeExceptions:
                pass
            return FakeExceptions()
        return getattr(sys.modules.get('yfinance', self), name, lambda *a, **k: None)

    def __call__(self, *args, **kwargs):
        return self.real_import(*args, **kwargs)

# 尝试导入，如果失败则用空模块替代
try:
    import yfinance
except ImportError:
    yfinance = type(sys)('yfinance')
    yfinance.exceptions = type(sys)('yfinance.exceptions')

from datetime import datetime, timedelta
from typing import Annotated

from langchain_core.tools import tool

# 导入 china_akshare
from tradingagents.dataflows.china_akshare import (
    get_china_stock_data as _stock_data,
    get_china_indicator as _indicator,
    get_china_verified_market_snapshot as _snapshot,
)


# ===== LangChain Tools =====

@tool
def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company, e.g. 600519.SH or 000001.SZ"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve China A-share stock price data (OHLCV).

    Args:
        symbol: A-share symbol like 600519.SH (Shanghai) or 000001.SZ (Shenzhen)
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        str: A formatted dataframe containing the stock price data
    """
    return _stock_data(symbol, start_date, end_date)


@tool
def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "indicator name: rsi, macd, boll, etc."],
    curr_date: Annotated[str, "current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "number of days to look back"] = 30,
) -> str:
    """
    Get technical indicators for China A-share stock.

    Args:
        symbol: A-share symbol like 600519.SH
        indicator: Indicator name (rsi, macd, boll, macds, macdh, boll_ub, boll_lb, etc.)
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Days to look back

    Returns:
        str: Technical indicator values
    """
    return _indicator(symbol, indicator, curr_date, look_back_days)


@tool
def get_verified_market_snapshot(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "number of days to look back"] = 30,
) -> str:
    """
    Get verified market data snapshot for China A-share stock.

    Args:
        symbol: A-share symbol like 600519.SH
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Days to look back

    Returns:
        str: Verified OHLCV and technical indicators
    """
    return _snapshot(symbol, curr_date, look_back_days)


# 工具列表
TOOLS = {
    "get_stock_data": get_stock_data,
    "get_indicators": get_indicators,
    "get_verified_market_snapshot": get_verified_market_snapshot,
}


if __name__ == "__main__":
    # 测试
    print("Testing China A-share tools...\n")

    print("[1] get_stock_data:")
    result = get_stock_data.invoke({
        "symbol": "600519.SH",
        "start_date": "2024-01-01",
        "end_date": "2024-01-10"
    })
    print(result[:300])

    print("\n[2] get_indicators (RSI):")
    result = get_indicators.invoke({
        "symbol": "600519.SH",
        "indicator": "rsi",
        "curr_date": "2024-01-10",
        "look_back_days": 30
    })
    print(result[:300])

    print("\n[3] get_verified_market_snapshot:")
    result = get_verified_market_snapshot.invoke({
        "symbol": "600519.SH",
        "curr_date": "2024-01-10",
        "look_back_days": 30
    })
    print(result[:500])
