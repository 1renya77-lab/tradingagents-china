"""Local prefetch cache with explicit cutoff-date slicing.

This cache is intentionally simple: it stores raw market rows by symbol and
only returns rows inside the requested date window. A cache file may contain
future rows relative to a backtest signal date, but callers only receive
``start_date <= Date <= end_date``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


REQUIRED_MARKET_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]


def cache_root() -> Path:
    configured = os.getenv("TRADINGAGENTS_PREFETCH_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data" / "prefetch"


def normalize_symbol(symbol: str) -> str:
    raw = str(symbol).strip().upper()
    if raw.endswith(".SH"):
        raw = raw[:-3]
    if raw.endswith(".SZ"):
        raw = raw[:-3]
    if raw.startswith("SH") or raw.startswith("SZ"):
        raw = raw[2:]
    return raw


def market_cache_path(symbol: str) -> Path:
    return cache_root() / "market" / f"{normalize_symbol(symbol)}.csv"


def _normalize_market_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    missing = [col for col in REQUIRED_MARKET_COLUMNS if col not in out.columns]
    if missing:
        raise ValueError(f"market cache data missing required columns: {missing}")

    out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    out = out.dropna(subset=["Date"])
    for col in ["Open", "High", "Low", "Close", "Volume", "Amount", "PctChange", "Turnover"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["Open", "High", "Low", "Close"])
    out = out.sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
    return out.reset_index(drop=True)


def save_market_data(symbol: str, df: pd.DataFrame, source: str = "unknown") -> Path:
    path = market_cache_path(symbol)
    path.parent.mkdir(parents=True, exist_ok=True)

    normalized = _normalize_market_frame(df)
    if path.exists():
        existing = pd.read_csv(path)
        normalized = _normalize_market_frame(pd.concat([existing, normalized], ignore_index=True))

    normalized.insert(0, "Symbol", normalize_symbol(symbol))
    normalized["Source"] = source
    normalized.to_csv(path, index=False, encoding="utf-8")
    return path


def load_market_data(symbol: str) -> pd.DataFrame | None:
    path = market_cache_path(symbol)
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if "Symbol" in df.columns:
        df = df.drop(columns=["Symbol"])
    if "Source" in df.columns:
        df = df.drop(columns=["Source"])
    normalized = _normalize_market_frame(df)
    return normalized if not normalized.empty else None


def load_market_slice(symbol: str, start_date: str, end_date: str) -> pd.DataFrame | None:
    df = load_market_data(symbol)
    if df is None or df.empty:
        return None

    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    if pd.isna(start) or pd.isna(end):
        raise ValueError(f"invalid date window: {start_date} -> {end_date}")

    # Calendar boundaries can fall on weekends or A-share holidays. Allow a
    # small gap at either side, while still never returning rows after ``end``.
    calendar_gap = pd.Timedelta(days=7)
    if df["Date"].min() > start + calendar_gap:
        return None
    if df["Date"].max() < end - calendar_gap:
        return None

    sliced = df[(df["Date"] >= start) & (df["Date"] <= end)].copy()
    return sliced.reset_index(drop=True) if not sliced.empty else None
