"""
BaoStock 数据源适配器
用于获取 A 股历史数据

支持:
- 日线数据
- 复权因子
- 财务数据
"""

import baostock as bs
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Tuple


# 全局登录状态
_bs_logged_in = False


def _ensure_login():
    """确保登录 Baostock。"""
    global _bs_logged_in
    if _bs_logged_in:
        return
    lg = bs.login()
    if lg.error_code != '0':
        raise RuntimeError(f"Baostock login failed: {lg.error_msg}")
    _bs_logged_in = True


def _ensure_logout():
    """确保登出 Baostock"""
    global _bs_logged_in
    if _bs_logged_in:
        try:
            bs.logout()
        except Exception:
            pass
        _bs_logged_in = False


def _relogin():
    global _bs_logged_in
    try:
        bs.logout()
    except Exception:
        pass
    _bs_logged_in = False
    _ensure_login()


def _run_query(query_fn, *args, **kwargs):
    """
    统一执行 BaoStock 查询。
    首次失败时仅重登一次，避免长时间卡在反复探活/重试上。
    """
    _ensure_login()
    last_error = None
    for attempt in range(2):
        try:
            rs = query_fn(*args, **kwargs)
            if rs.error_code == '0':
                return rs
            last_error = RuntimeError(f"Baostock query failed: {rs.error_msg}")
        except Exception as exc:
            last_error = exc
        if attempt == 0:
            _relogin()
    if last_error is None:
        raise RuntimeError("Baostock query failed with unknown error")
    raise last_error


def _convert_adjust_flag(adjust: str) -> str:
    """转换复权标志"""
    mapping = {
        "qfq": "1",  # 前复权
        "hfq": "2",  # 后复权
        "3": "3",    # 不复权
        "none": "3",
    }
    return mapping.get(str(adjust).lower(), "3")


def format_stock_code(ticker: str) -> str:
    """
    将 A 股代码转换为 BaoStock 格式

    Args:
        ticker: 股票代码，如 "600519" 或 "SH600519"

    Returns:
        BaoStock 格式，如 "sh.600519"
    """
    ticker = ticker.upper().strip()

    if ticker.startswith("SH"):
        code = ticker[2:]
        return f"sh.{code}"
    elif ticker.startswith("SZ"):
        code = ticker[2:]
        return f"sz.{code}"
    elif len(ticker) == 6:
        if ticker.startswith(("6", "5")):
            return f"sh.{ticker}"
        else:
            return f"sz.{ticker}"
    else:
        return ticker


def get_kline_data(
    ticker: str,
    start_date: str,
    end_date: str,
    freq: str = "d",
    adjust: str = "qfq"
) -> Optional[pd.DataFrame]:
    """
    获取 K 线数据

    Args:
        ticker: 股票代码
        start_date: 开始日期 "YYYY-MM-DD"
        end_date: 结束日期 "YYYY-MM-DD"
        freq: 频率 "d"=日线, "w"=周线, "m"=月线
        adjust: 复权类型 "qfq"=前复权, "hfq"=后复权, None=不复权

    Returns:
        DataFrame with columns: date, open, high, low, close, volume, amount
    """
    code = format_stock_code(ticker)
    rs = _run_query(
        bs.query_history_k_data_plus,
        code,
        "date,open,high,low,close,volume,amount",
        start_date=start_date,
        end_date=end_date,
        frequency=freq,
        adjustflag=_convert_adjust_flag(adjust)
    )

    data_list = []
    while rs.next():
        data_list.append(rs.get_row_data())

    if not data_list:
        return None

    df = pd.DataFrame(data_list, columns=rs.fields)

    # 转换类型
    numeric_cols = ["open", "high", "low", "close", "volume", "amount"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    return df


def get_stock_fundamentals(ticker: str, year: int, quarter: int) -> Optional[pd.DataFrame]:
    """
    获取股票财务数据

    Args:
        ticker: 股票代码
        year: 年份
        quarter: 季度 (1-4)

    Returns:
        DataFrame with fundamentals data
    """
    code = format_stock_code(ticker)
    rs = _run_query(
        bs.query_profit_data,
        code=code,
        year=year,
        quarter=quarter
    )

    data_list = []
    while rs.next():
        data_list.append(rs.get_row_data())

    if not data_list:
        return None

    return pd.DataFrame(data_list, columns=rs.fields)


def get_industryClassification(ticker: str) -> Optional[str]:
    """获取行业分类"""
    code = format_stock_code(ticker)
    rs = _run_query(bs.query_stock_industry, code)

    data_list = []
    while rs.next():
        data_list.append(rs.get_row_data())

    if not data_list:
        return None

    df = pd.DataFrame(data_list, columns=rs.fields)
    if len(df) > 0 and "industry" in df.columns:
        return df.iloc[0]["industry"]
    return None


def get_stock_info(ticker: str) -> Optional[dict]:
    """获取股票基本信息"""
    code = format_stock_code(ticker)
    rs = _run_query(bs.query_stock_basic, code=code)

    data_list = []
    while rs.next():
        data_list.append(rs.get_row_data())

    if not data_list:
        return None

    df = pd.DataFrame(data_list, columns=rs.fields)
    if len(df) > 0:
        return df.iloc[0].to_dict()
    return None


def get_trading_dates(
    start_date: str,
    end_date: str,
    is_trade_date: bool = True
) -> pd.DatetimeIndex:
    """
    获取交易日历

    Args:
        start_date: 开始日期
        end_date: 结束日期
        is_trade_date: True=只返回交易日, False=返回所有日期

    Returns:
        DatetimeIndex of dates
    """
    _ensure_login()

    rs = bs.query_trade_dates(
        start_date=start_date,
        end_date=end_date
    )

    if rs.error_code != '0':
        return pd.DatetimeIndex([])

    data_list = []
    while rs.next():
        data_list.append(rs.get_row_data())

    if not data_list:
        return pd.DatetimeIndex([])

    df = pd.DataFrame(data_list, columns=rs.fields)

    if is_trade_date:
        df = df[df["is_trading_day"] == "1"]

    return pd.to_datetime(df["calendar_date"])


class BaoStockProvider:
    """
    BaoStock 数据源提供者

    提供与 TradingAgents 数据接口兼容的封装
    """

    def __init__(self):
        _ensure_login()

    def __del__(self):
        _ensure_logout()

    def get_stock_data(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        fields: Optional[list] = None
    ) -> dict:
        """
        获取股票数据 (兼容接口)

        Returns:
            dict with keys: open, high, low, close, volume, amount, date
        """
        df = get_kline_data(ticker, start_date, end_date)

        if df is None:
            return {}

        result = {
            "open": df["open"].tolist() if "open" in df.columns else [],
            "high": df["high"].tolist() if "high" in df.columns else [],
            "low": df["low"].tolist() if "low" in df.columns else [],
            "close": df["close"].tolist() if "close" in df.columns else [],
            "volume": df["volume"].tolist() if "volume" in df.columns else [],
            "date": df["date"].dt.strftime("%Y-%m-%d").tolist() if "date" in df.columns else [],
        }

        if fields:
            return {k: v for k, v in result.items() if k in fields or k == "date"}

        return result

    def get_financial_data(
        self,
        ticker: str,
        year: int,
        quarter: int
    ) -> dict:
        """获取财务数据"""
        df = get_stock_fundamentals(ticker, year, quarter)

        if df is None:
            return {}

        return df.to_dict(orient="records")

    def get_market_indicators(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> dict:
        """
        计算市场技术指标

        Returns:
            dict with RSI, MACD, BOLL, etc.
        """
        df = get_kline_data(ticker, start_date, end_date)

        if df is None or len(df) < 20:
            return {}

        close = df["close"].values

        # RSI
        delta = pd.Series(close).diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss
        rsi = (100 - (100 / (1 + rs))).iloc[-1] if not pd.isna(rs.iloc[-1]) else 50

        # BOLL (简单版本)
        sma = pd.Series(close).rolling(window=20).mean()
        std = pd.Series(close).rolling(window=20).std()
        upper_band = sma + 2 * std
        lower_band = sma - 2 * std
        boll = {
            "upper": upper_band.iloc[-1] if not pd.isna(upper_band.iloc[-1]) else close[-1] * 1.05,
            "middle": sma.iloc[-1] if not pd.isna(sma.iloc[-1]) else close[-1],
            "lower": lower_band.iloc[-1] if not pd.isna(lower_band.iloc[-1]) else close[-1] * 0.95,
        }

        # MACD
        ema12 = pd.Series(close).ewm(span=12).mean()
        ema26 = pd.Series(close).ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        macd_hist = macd - signal

        return {
            "RSI": round(rsi, 2) if not pd.isna(rsi) else 50,
            "MACD": round(macd.iloc[-1], 4) if not pd.isna(macd.iloc[-1]) else 0,
            "MACD_signal": round(signal.iloc[-1], 4) if not pd.isna(signal.iloc[-1]) else 0,
            "MACD_hist": round(macd_hist.iloc[-1], 4) if not pd.isna(macd_hist.iloc[-1]) else 0,
            "BOLL_upper": round(boll["upper"], 2),
            "BOLL_middle": round(boll["middle"], 2),
            "BOLL_lower": round(boll["lower"], 2),
            "close": close[-1],
            "volume": int(df["volume"].iloc[-1]) if "volume" in df.columns else 0,
        }


if __name__ == "__main__":
    # 测试
    provider = BaoStockProvider()

    print("获取 600519 日线数据...")
    data = provider.get_stock_data("600519", "2024-01-01", "2024-03-31")
    if data:
        print(f"  获取到 {len(data.get('close', []))} 条数据")
        print(f"  最新收盘价: {data['close'][-1] if data.get('close') else 'N/A'}")
    else:
        print("  获取失败")

    print("\n获取技术指标...")
    indicators = provider.get_market_indicators("600519", "2024-01-01", "2024-03-31")
    print(f"  RSI: {indicators.get('RSI', 'N/A')}")
    print(f"  MACD: {indicators.get('MACD', 'N/A')}")
    print(f"  BOLL: {indicators.get('BOLL_upper', 'N/A')}")

    print("\n获取交易日历...")
    dates = get_trading_dates("2024-01-01", "2024-03-31")
    print(f"  交易日数量: {len(dates)}")
