from __future__ import annotations

import functools
import os
from datetime import datetime

import pandas as pd

from .errors import NoMarketDataError, VendorNotConfiguredError


def _require_tushare():
    try:
        import tushare as ts
    except ImportError as exc:
        raise VendorNotConfiguredError("tushare is not installed") from exc

    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        raise VendorNotConfiguredError("TUSHARE_TOKEN is not configured")

    ts.set_token(token)
    return ts, ts.pro_api()


def _normalize_tushare_symbol(symbol: str) -> str:
    raw = str(symbol).strip().upper()
    if raw.endswith(".SH"):
        return raw[:-3] + ".SH"
    if raw.endswith(".SZ"):
        return raw[:-3] + ".SZ"
    if raw.startswith("SH") and len(raw) == 8:
        return raw[2:] + ".SH"
    if raw.startswith("SZ") and len(raw) == 8:
        return raw[2:] + ".SZ"
    if raw.isdigit() and len(raw) == 6:
        suffix = ".SH" if raw.startswith(("5", "6", "9")) else ".SZ"
        return raw + suffix
    raise NoMarketDataError(symbol, raw, "not a supported A-share symbol for Tushare")


def _compact(date_str: str) -> str:
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y%m%d")


@functools.lru_cache(maxsize=1)
def _stock_basic_table() -> pd.DataFrame:
    ts, pro = _require_tushare()
    del ts
    frames = []
    for status in ("L", "P", "D"):
        df = pro.stock_basic(
            exchange="",
            list_status=status,
            fields="ts_code,symbol,name,area,industry,market,list_date,list_status",
        )
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["ts_code"])
    for col in ("ts_code", "symbol", "name", "industry", "market", "list_date", "list_status"):
        if col in out.columns:
            out[col] = out[col].astype(str).str.strip()
    return out


def resolve_symbol_from_name(name: str) -> str | None:
    query = str(name).strip()
    if not query:
        return None
    df = _stock_basic_table()
    if df.empty:
        return None
    exact = df[df["name"] == query]
    if not exact.empty:
        return str(exact.iloc[0]["symbol"])
    partial = df[df["name"].str.contains(query, na=False)]
    if len(partial) == 1:
        return str(partial.iloc[0]["symbol"])
    return None


def get_tushare_hist(symbol: str, start_date: str, end_date: str, period: str = "daily") -> pd.DataFrame:
    ts, pro = _require_tushare()
    ts_code = _normalize_tushare_symbol(symbol)
    freq_map = {"daily": "D", "weekly": "W", "monthly": "M"}
    freq = freq_map.get(period, "D")
    df = ts.pro_bar(
        ts_code=ts_code,
        api=pro,
        start_date=_compact(start_date),
        end_date=_compact(end_date),
        freq=freq,
        adj="qfq",
    )
    if df is None or df.empty:
        raise NoMarketDataError(symbol, ts_code, f"no Tushare rows between {start_date} and {end_date}")

    rename_map = {
        "trade_date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "vol": "Volume",
        "amount": "Amount",
        "pct_chg": "PctChange",
    }
    out = df.rename(columns=rename_map)
    out["Date"] = pd.to_datetime(out["Date"], format="%Y%m%d", errors="coerce")
    out = out.dropna(subset=["Date"]).sort_values("Date")
    for col in ("Open", "High", "Low", "Close", "Volume", "Amount", "PctChange"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["Open", "High", "Low", "Close"])
    if out.empty:
        raise NoMarketDataError(symbol, ts_code, "Tushare returned no numeric OHLC rows")
    return out


def get_tushare_stock_info(symbol: str) -> dict:
    ts_code = _normalize_tushare_symbol(symbol)
    df = _stock_basic_table()
    if df.empty:
        return {}
    row = df[df["ts_code"] == ts_code]
    if row.empty:
        return {}
    item = row.iloc[0]
    return {
        "ts_code": item.get("ts_code"),
        "symbol": item.get("symbol"),
        "name": item.get("name"),
        "industry": item.get("industry"),
        "market": item.get("market"),
        "list_date": item.get("list_date"),
        "list_status": item.get("list_status"),
    }


def get_tushare_daily_basic(symbol: str, trade_date: str) -> dict:
    _, pro = _require_tushare()
    ts_code = _normalize_tushare_symbol(symbol)
    date_str = _compact(trade_date)
    df = pro.daily_basic(
        ts_code=ts_code,
        trade_date=date_str,
        fields="ts_code,trade_date,turnover_rate,volume_ratio,pe,pb,pe_ttm,total_mv,circ_mv",
    )
    if df is None or df.empty:
        return {}
    item = df.iloc[0].to_dict()
    return {k: item.get(k) for k in item.keys()}


def get_tushare_financial_bundle(symbol: str, limit: int = 4) -> dict:
    _, pro = _require_tushare()
    ts_code = _normalize_tushare_symbol(symbol)
    query = {"ts_code": ts_code, "limit": limit}
    out: dict[str, pd.DataFrame] = {}
    for name, func in (
        ("income_statement", pro.income),
        ("balance_sheet", pro.balancesheet),
        ("cashflow_statement", pro.cashflow),
        ("financial_indicators", pro.fina_indicator),
    ):
        try:
            df = func(**query)
        except Exception:
            df = None
        if df is not None and not df.empty:
            out[name] = df
    return out


def get_tushare_news(symbol: str | None, start_date: str, end_date: str, limit: int = 20) -> pd.DataFrame:
    _, pro = _require_tushare()
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=1)
    sources = ("sina", "eastmoney", "10jqka")
    frames = []
    for src in sources:
        try:
            df = pro.news(
                src=src,
                start_date=start_dt.strftime("%Y-%m-%d 00:00:00"),
                end_date=(end_dt - pd.Timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S"),
            )
        except Exception:
            continue
        if df is None or df.empty:
            continue
        tmp = df.copy()
        tmp["datetime"] = pd.to_datetime(tmp["datetime"], errors="coerce")
        tmp = tmp[tmp["datetime"].notna() & (tmp["datetime"] >= start_dt) & (tmp["datetime"] < end_dt)]
        if symbol:
            code = _normalize_tushare_symbol(symbol).split(".")[0]
            tmp = tmp[
                tmp.get("content", pd.Series(dtype=str)).astype(str).str.contains(code, na=False)
                | tmp.get("title", pd.Series(dtype=str)).astype(str).str.contains(code, na=False)
            ]
        if not tmp.empty:
            tmp["source_name"] = src
            frames.append(tmp)
    if not frames:
        raise NoMarketDataError(symbol or "market", symbol or "market", "no Tushare news rows in window")
    out = pd.concat(frames, ignore_index=True).sort_values("datetime", ascending=False)
    out = out.drop_duplicates(subset=["title", "datetime"]).head(limit)
    return out
