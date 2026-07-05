"""
Build a minimal Qlib provider from A-share daily bars.

This creates only the files needed by Qlib's local provider:

    calendars/day.txt
    instruments/all.txt
    features/<instrument>/*.day.bin

It is meant for small, auditable backtests such as one stock over one year.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd


FIELD_MAP = {
    "open": "开盘",
    "close": "收盘",
    "high": "最高",
    "low": "最低",
    "volume": "成交量",
    "amount": "成交额",
    "change": "涨跌幅",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a minimal Qlib provider from A-share daily bars.")
    parser.add_argument("--ticker", required=True, help="A-share code, e.g. 000001")
    parser.add_argument("--start", required=True, help="Start date, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date, YYYY-MM-DD")
    parser.add_argument(
        "--source",
        default="akshare",
        choices=["akshare", "baostock"],
        help="Daily bar data source to use explicitly",
    )
    parser.add_argument(
        "--provider-uri",
        default="data/qlib_cn_minimal",
        help="Output Qlib provider directory",
    )
    parser.add_argument(
        "--adjust",
        default="qfq",
        choices=["", "qfq", "hfq"],
        help="AKShare adjustment mode: empty string, qfq, or hfq",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Remove provider directory before writing",
    )
    parser.add_argument(
        "--calendar-buffer-days",
        type=int,
        default=10,
        help="Extra calendar days after --end for Qlib execution boundaries",
    )
    return parser.parse_args()


def format_instrument(ticker: str) -> str:
    ticker = ticker.upper().strip()
    if ticker.startswith(("SH", "SZ")):
        return ticker
    if len(ticker) == 6 and ticker.isdigit():
        return f"SH{ticker}" if ticker.startswith(("5", "6", "9")) else f"SZ{ticker}"
    raise ValueError(f"Cannot infer A-share market prefix for ticker: {ticker}")


def plain_ticker(ticker: str) -> str:
    ticker = ticker.upper().strip()
    if ticker.startswith(("SH", "SZ")):
        return ticker[2:]
    return ticker


def fetch_akshare_daily(ticker: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    import akshare as ak

    df = ak.stock_zh_a_hist(
        symbol=plain_ticker(ticker),
        period="daily",
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
        adjust=adjust,
        timeout=20,
    )
    if df.empty:
        raise RuntimeError(f"AKShare returned empty data for {ticker} during {start} -> {end}")

    df = df.copy()
    df["datetime"] = pd.to_datetime(df["日期"])
    df = df.sort_values("datetime").drop_duplicates("datetime", keep="last")
    return df


def baostock_code(ticker: str) -> str:
    instrument = format_instrument(ticker)
    market = instrument[:2].lower()
    code = instrument[2:]
    return f"{market}.{code}"


def fetch_baostock_daily(ticker: str, start: str, end: str) -> pd.DataFrame:
    import baostock as bs

    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"Baostock login failed: {login.error_msg}")

    try:
        fields = "date,open,high,low,close,volume,amount,pctChg"
        rs = bs.query_history_k_data_plus(
            baostock_code(ticker),
            fields,
            start_date=start,
            end_date=end,
            frequency="d",
            adjustflag="2",
        )
        if rs.error_code != "0":
            raise RuntimeError(f"Baostock query failed: {rs.error_msg}")

        rows = []
        while rs.next():
            rows.append(rs.get_row_data())

        if not rows:
            raise RuntimeError(f"Baostock returned empty data for {ticker} during {start} -> {end}")

        raw = pd.DataFrame(rows, columns=rs.fields)
        df = pd.DataFrame(
            {
                "日期": pd.to_datetime(raw["date"]),
                "开盘": pd.to_numeric(raw["open"], errors="coerce"),
                "收盘": pd.to_numeric(raw["close"], errors="coerce"),
                "最高": pd.to_numeric(raw["high"], errors="coerce"),
                "最低": pd.to_numeric(raw["low"], errors="coerce"),
                "成交量": pd.to_numeric(raw["volume"], errors="coerce"),
                "成交额": pd.to_numeric(raw["amount"], errors="coerce"),
                "涨跌幅": pd.to_numeric(raw["pctChg"], errors="coerce"),
            }
        )
        df["datetime"] = df["日期"]
        df = df.sort_values("datetime").drop_duplicates("datetime", keep="last")
        return df
    finally:
        bs.logout()


def write_calendar(provider_uri: Path, dates: pd.Series) -> list[pd.Timestamp]:
    calendar_dir = provider_uri / "calendars"
    calendar_dir.mkdir(parents=True, exist_ok=True)
    calendar = [pd.Timestamp(d).normalize() for d in sorted(pd.to_datetime(dates).unique())]
    with (calendar_dir / "day.txt").open("w", encoding="utf-8") as f:
        for dt in calendar:
            f.write(dt.strftime("%Y-%m-%d") + "\n")
    return calendar


def write_instruments(provider_uri: Path, instrument: str, start: str, end: str) -> None:
    instruments_dir = provider_uri / "instruments"
    instruments_dir.mkdir(parents=True, exist_ok=True)
    with (instruments_dir / "all.txt").open("w", encoding="utf-8") as f:
        f.write(f"{instrument}\t{start}\t{end}\n")


def write_feature_bin(path: Path, values: np.ndarray, start_index: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.hstack([[start_index], values]).astype("<f").tofile(path)


def write_features(provider_uri: Path, instrument: str, df: pd.DataFrame, calendar: list[pd.Timestamp]) -> None:
    feature_dir = provider_uri / "features" / instrument.lower()
    feature_dir.mkdir(parents=True, exist_ok=True)

    indexed = df.set_index("datetime").reindex(calendar)
    for qlib_field, source_col in FIELD_MAP.items():
        values = pd.to_numeric(indexed[source_col], errors="coerce").to_numpy(dtype=np.float32)
        if qlib_field == "change":
            values = values / 100.0
        write_feature_bin(feature_dir / f"{qlib_field}.day.bin", values, start_index=0)

    factor = np.ones(len(calendar), dtype=np.float32)
    write_feature_bin(feature_dir / "factor.day.bin", factor, start_index=0)


def main() -> None:
    args = parse_args()
    provider_uri = Path(args.provider_uri).expanduser().resolve()
    instrument = format_instrument(args.ticker)

    if provider_uri.exists() and args.force:
        shutil.rmtree(provider_uri)
    provider_uri.mkdir(parents=True, exist_ok=True)

    fetch_end = (
        pd.Timestamp(args.end) + timedelta(days=args.calendar_buffer_days)
    ).strftime("%Y-%m-%d")
    if args.source == "akshare":
        df = fetch_akshare_daily(args.ticker, args.start, fetch_end, args.adjust)
    else:
        df = fetch_baostock_daily(args.ticker, args.start, fetch_end)
    calendar = write_calendar(provider_uri, df["datetime"])
    write_instruments(
        provider_uri,
        instrument=instrument,
        start=min(calendar).strftime("%Y-%m-%d"),
        end=max(calendar).strftime("%Y-%m-%d"),
    )
    write_features(provider_uri, instrument, df, calendar)

    print("Minimal Qlib provider built")
    print(f"provider_uri : {provider_uri}")
    print(f"instrument   : {instrument}")
    print(f"rows         : {len(df)}")
    print(f"first_date   : {min(calendar).strftime('%Y-%m-%d')}")
    print(f"last_date    : {max(calendar).strftime('%Y-%m-%d')}")
    print(f"source       : {args.source}")
    print(f"adjust       : {args.adjust or 'none'}")


if __name__ == "__main__":
    main()
