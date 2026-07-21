"""China A-share market-data adapter with AkShare -> BaoStock fallback."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from .errors import NoMarketDataError, VendorNotConfiguredError
from .data_quality import data_quality_header


INDICATOR_DESCRIPTIONS = {
    "close_50_sma": "50 SMA: A medium-term trend indicator.",
    "close_200_sma": "200 SMA: A long-term trend benchmark.",
    "close_10_ema": "10 EMA: A responsive short-term average.",
    "macd": "MACD: Computes momentum via differences of EMAs.",
    "macds": "MACD Signal: An EMA smoothing of the MACD line.",
    "macdh": "MACD Histogram: Shows the gap between the MACD line and its signal.",
    "rsi": "RSI: Measures momentum to flag overbought/oversold conditions.",
    "boll": "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands.",
    "boll_ub": "Bollinger Upper Band: Typically 2 standard deviations above the middle line.",
    "boll_lb": "Bollinger Lower Band: Typically 2 standard deviations below the middle line.",
    "atr": "ATR: Averages true range to measure volatility.",
    "vwma": "VWMA: A moving average weighted by volume.",
}


def _require_akshare():
    try:
        import akshare as ak
    except ImportError as exc:
        raise VendorNotConfiguredError("akshare is not installed") from exc
    return ak


def _require_baostock():
    try:
        from .baostock_provider import get_kline_data
    except ImportError as exc:
        raise VendorNotConfiguredError("baostock is not installed") from exc
    return get_kline_data


def _normalize_a_share_symbol(symbol: str) -> str:
    raw = str(symbol).strip().upper()
    if raw.endswith(".SH") or raw.startswith("SH"):
        return raw.replace(".SH", "").replace("SH", "", 1)
    if raw.endswith(".SZ") or raw.startswith("SZ"):
        return raw.replace(".SZ", "").replace("SZ", "", 1)
    if raw.isdigit() and len(raw) == 6:
        return raw
    raise NoMarketDataError(symbol, raw, "not a supported A-share symbol")


def _compact_date(date_str: str) -> str:
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y%m%d")


def _normalize_ohlcv(df: pd.DataFrame, symbol: str, canonical: str, source: str) -> pd.DataFrame:
    rename_map = {
        "日期": "Date",
        "开盘": "Open",
        "收盘": "Close",
        "最高": "High",
        "最低": "Low",
        "成交量": "Volume",
        "成交额": "Amount",
        "振幅": "Amplitude",
        "涨跌幅": "PctChange",
        "涨跌额": "Change",
        "换手率": "Turnover",
        "date": "Date",
        "open": "Open",
        "close": "Close",
        "high": "High",
        "low": "Low",
        "volume": "Volume",
        "amount": "Amount",
        "trade_date": "Date",
        "vol": "Volume",
    }
    out = df.rename(columns=rename_map).copy()
    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in out.columns]
    if missing:
        raise NoMarketDataError(symbol, canonical, f"{source} result missing columns: {missing}")

    out = out[required + [c for c in ["Amount", "PctChange", "Turnover"] if c in out.columns]].copy()
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    out = out.dropna(subset=["Date"]).sort_values("Date")
    for col in ["Open", "High", "Low", "Close", "Volume", "Amount", "PctChange", "Turnover"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["Open", "High", "Low", "Close"])
    if out.empty:
        raise NoMarketDataError(symbol, canonical, f"{source} returned no numeric OHLC rows")
    return out


def _fetch_hist_akshare(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    ak = _require_akshare()
    code = _normalize_a_share_symbol(symbol)
    df = ak.stock_zh_a_hist(
        symbol=code,
        period="daily",
        start_date=_compact_date(start_date),
        end_date=_compact_date(end_date),
        adjust="qfq",
    )
    if df is None or df.empty:
        raise NoMarketDataError(symbol, code, f"no AkShare rows between {start_date} and {end_date}")
    return _normalize_ohlcv(df, symbol, code, "AkShare")


def _fetch_hist_baostock(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    get_kline_data = _require_baostock()
    code = _normalize_a_share_symbol(symbol)
    df = get_kline_data(code, start_date, end_date, freq="d", adjust="qfq")
    if df is None or df.empty:
        raise NoMarketDataError(symbol, code, f"no BaoStock rows between {start_date} and {end_date}")
    return _normalize_ohlcv(df, symbol, code, "BaoStock")


def _fetch_hist(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    from .local_prefetch_cache import load_market_slice

    cached = load_market_slice(symbol, start_date, end_date)
    if cached is not None and not cached.empty:
        return cached

    errors: list[Exception] = []
    for fetcher in (_fetch_hist_akshare, _fetch_hist_baostock):
        try:
            df = fetcher(symbol, start_date, end_date)
            try:
                from .local_prefetch_cache import save_market_data

                save_market_data(symbol, df, source=fetcher.__name__.replace("_fetch_hist_", ""))
            except Exception:
                pass
            return df
        except Exception as exc:
            errors.append(exc)
            continue
    if errors:
        raise errors[0]
    raise NoMarketDataError(symbol, symbol, "no China vendor available")


def _add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = out["Close"]
    high = out["High"]
    low = out["Low"]
    volume = out["Volume"] if "Volume" in out.columns else pd.Series(index=out.index, dtype=float)

    out["close_50_sma"] = close.rolling(50, min_periods=1).mean()
    out["close_200_sma"] = close.rolling(200, min_periods=1).mean()
    out["close_10_ema"] = close.ewm(span=10, adjust=False).mean()

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["macd"] = ema12 - ema26
    out["macds"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["macdh"] = out["macd"] - out["macds"]

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    rs = gain / loss.replace(0, pd.NA)
    out["rsi"] = 100 - (100 / (1 + rs))

    mid = close.rolling(20, min_periods=1).mean()
    std = close.rolling(20, min_periods=1).std(ddof=0)
    out["boll"] = mid
    out["boll_ub"] = mid + 2 * std
    out["boll_lb"] = mid - 2 * std

    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    out["atr"] = tr.rolling(14, min_periods=1).mean()

    vol_sum = volume.rolling(20, min_periods=1).sum()
    out["vwma"] = (close * volume).rolling(20, min_periods=1).sum() / vol_sum.replace(0, pd.NA)
    return out


def get_china_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    df = _fetch_hist(symbol, start_date, end_date)
    display = df.copy()
    display["Date"] = display["Date"].dt.strftime("%Y-%m-%d")
    for col in ["Open", "High", "Low", "Close", "Amount", "PctChange", "Turnover"]:
        if col in display.columns:
            display[col] = display[col].round(2)

    header = (
        data_quality_header(
            ok=True,
            source="AkShare/BaoStock",
            rows=len(display),
            cutoff_date=end_date,
        )
        + "\n\n"
        f"# China A-share stock data for {symbol.upper()} from {start_date} to {end_date}\n"
        f"# Source: Multi-source China fallback (AkShare/BaoStock), qfq adjusted\n"
        f"# Total records: {len(display)}\n"
        "# Currency: CNY\n"
        "# A-share note: SELL means closing/avoiding long exposure, not short selling.\n\n"
    )
    return header + display.to_csv(index=False)


def get_china_indicator(symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
    indicator = indicator.lower().strip()
    if indicator not in INDICATOR_DESCRIPTIONS:
        raise ValueError(f"Indicator {indicator} is not supported. Please choose from: {list(INDICATOR_DESCRIPTIONS)}")

    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=max(look_back_days + 260, 320))
    df = _fetch_hist(symbol, start_dt.strftime("%Y-%m-%d"), curr_date)
    ind_df = _add_indicators(df)
    ind_df = ind_df[ind_df["Date"] <= pd.to_datetime(curr_date)].tail(max(1, int(look_back_days)))

    lines = [
        data_quality_header(
            ok=True,
            source="AkShare/BaoStock",
            rows=len(ind_df),
            cutoff_date=curr_date,
        ),
        "",
        f"## {indicator} values for China A-share {symbol.upper()}",
        "",
        f"- Requested analysis date: {curr_date}",
        "- Source: Multi-source China fallback (AkShare/BaoStock), qfq adjusted",
        "- Rows after the requested analysis date are excluded.",
        "",
    ]
    for _, row in ind_df.iterrows():
        value = row.get(indicator)
        rendered = "N/A" if pd.isna(value) else f"{float(value):.4f}"
        lines.append(f"{row['Date'].strftime('%Y-%m-%d')}: {rendered}")

    lines += ["", INDICATOR_DESCRIPTIONS[indicator]]
    return "\n".join(lines)


def get_china_verified_market_snapshot(symbol: str, curr_date: str, look_back_days: int = 30) -> str:
    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=max(look_back_days + 260, 320))
    df = _add_indicators(_fetch_hist(symbol, start_dt.strftime("%Y-%m-%d"), curr_date))
    df = df[df["Date"] <= pd.to_datetime(curr_date)].sort_values("Date")
    if df.empty:
        raise NoMarketDataError(symbol, symbol, f"no rows on or before {curr_date}")

    latest = df.iloc[-1]
    recent = df.tail(max(1, min(int(look_back_days), 30)))
    fields = ["Open", "High", "Low", "Close", "Volume"]
    indicators = ["close_10_ema", "close_50_sma", "close_200_sma", "rsi", "boll", "boll_ub", "boll_lb", "macd", "macds", "macdh", "atr", "vwma"]

    def fmt(v):
        if pd.isna(v):
            return "N/A"
        if isinstance(v, (int, float)):
            return f"{float(v):.2f}"
        return str(v)

    lines = [
        data_quality_header(
            ok=True,
            source="AkShare/BaoStock",
            rows=len(df),
            cutoff_date=curr_date,
            warning=(
                f"latest trading row is {latest['Date'].strftime('%Y-%m-%d')}, before requested date"
                if latest["Date"].strftime("%Y-%m-%d") < curr_date
                else None
            ),
        ),
        "",
        f"## Verified market data snapshot for China A-share {symbol.upper()}",
        "",
        f"- Requested analysis date: {curr_date}",
        f"- Latest trading row used: {latest['Date'].strftime('%Y-%m-%d')}",
        "- Rows after the requested analysis date are excluded before verification.",
        "- Currency: CNY",
        "- SELL means closing/avoiding long exposure, not short selling.",
        "- Source: Multi-source China fallback (AkShare/BaoStock)",
        "",
        "### Latest verified OHLCV row",
        "",
        "| Field | Value |",
        "|---|---:|",
    ]
    for field in fields:
        lines.append(f"| {field} | {fmt(latest.get(field))} |")

    lines += ["", "### Verified technical indicators (latest row)", "", "| Indicator | Value |", "|---|---:|"]
    for name in indicators:
        lines.append(f"| {name} | {fmt(latest.get(name))} |")

    lines += ["", f"### Recent verified closes (last {len(recent)} rows)", "", "| Date | Close |", "|---|---:|"]
    for _, row in recent.iterrows():
        lines.append(f"| {row['Date'].strftime('%Y-%m-%d')} | {fmt(row.get('Close'))} |")

    return "\n".join(lines)
