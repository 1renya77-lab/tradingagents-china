#!/usr/bin/env python3
"""Prefetch A-share market data into a local cutoff-safe cache."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from tradingagents.dataflows.china_akshare import _fetch_hist_akshare, _fetch_hist_baostock
from tradingagents.dataflows.local_prefetch_cache import market_cache_path, save_market_data


def build_prefetch_start(start_date: str, lookback_days: int) -> str:
    start = datetime.strptime(start_date, "%Y-%m-%d")
    return (start - timedelta(days=int(lookback_days))).strftime("%Y-%m-%d")


def fetch_market_data(ticker: str, start_date: str, end_date: str, source: str) -> tuple[pd.DataFrame, str]:
    if source == "akshare":
        return _fetch_hist_akshare(ticker, start_date, end_date), "akshare"
    if source == "baostock":
        return _fetch_hist_baostock(ticker, start_date, end_date), "baostock"
    if source == "auto":
        errors = []
        for name, fetcher in (("akshare", _fetch_hist_akshare), ("baostock", _fetch_hist_baostock)):
            try:
                return fetcher(ticker, start_date, end_date), name
            except Exception as exc:
                errors.append(f"{name}: {exc}")
        raise RuntimeError("all market data sources failed: " + " | ".join(errors))
    raise ValueError("source must be akshare, baostock, or auto")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prefetch A-share market data for cutoff-safe local reuse.")
    parser.add_argument("--ticker", required=True, help="A-share ticker, e.g. 300308")
    parser.add_argument("--start", required=True, help="Experiment start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Experiment end date YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=320, help="Extra days before --start for indicators")
    parser.add_argument("--source", choices=["auto", "akshare", "baostock"], default="auto")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    fetch_start = build_prefetch_start(args.start, args.lookback_days)
    df, source = fetch_market_data(args.ticker, fetch_start, args.end, args.source)
    path = save_market_data(args.ticker, df, source=source)

    print("Market data prefetched")
    print(f"ticker      : {args.ticker}")
    print(f"fetch_start : {fetch_start}")
    print(f"end         : {args.end}")
    print(f"source      : {source}")
    print(f"rows        : {len(df)}")
    print(f"first_date  : {df['Date'].min().strftime('%Y-%m-%d')}")
    print(f"last_date   : {df['Date'].max().strftime('%Y-%m-%d')}")
    print(f"cache_path  : {Path(path)}")
    print(f"active_path : {market_cache_path(args.ticker)}")
    print("cutoff_rule : later agent calls still receive only rows <= their signal date")


if __name__ == "__main__":
    main()
