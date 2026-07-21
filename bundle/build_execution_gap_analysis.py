#!/usr/bin/env python3
"""Split each signal window into pre-execution gap and post-execution return."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from tradingagents.dataflows.local_prefetch_cache import load_market_data


def _pct(value: float) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{float(value):.2%}"


def _next_trading_date(dates: pd.Series, after_date: pd.Timestamp) -> pd.Timestamp | None:
    future = dates[dates > after_date]
    if future.empty:
        return None
    return pd.Timestamp(future.iloc[0])


def _bar_at(bars: pd.DataFrame, date: pd.Timestamp) -> pd.Series | None:
    matched = bars[bars["Date"] == date]
    if matched.empty:
        return None
    return matched.iloc[0]


def _bar_at_or_before(bars: pd.DataFrame, date: pd.Timestamp) -> pd.Series | None:
    matched = bars[bars["Date"] <= date]
    if matched.empty:
        return None
    return matched.iloc[-1]


def build_execution_gap_rows(signals: pd.DataFrame, bars: pd.DataFrame, *, end: str | None = None) -> pd.DataFrame:
    signals = signals.copy()
    bars = bars.copy()
    signals["date"] = pd.to_datetime(signals["date"])
    signals["target_position"] = pd.to_numeric(signals["target_position"], errors="coerce")
    signals = signals.dropna(subset=["date", "target_position"]).sort_values("date").reset_index(drop=True)

    bars["Date"] = pd.to_datetime(bars["Date"])
    for col in ["Open", "Close"]:
        bars[col] = pd.to_numeric(bars[col], errors="coerce")
    bars = bars.dropna(subset=["Date", "Open", "Close"]).sort_values("Date").reset_index(drop=True)
    if end:
        bars = bars[bars["Date"] <= pd.to_datetime(end)].copy()

    rows: list[dict] = []
    trading_dates = bars["Date"]
    execution_dates: list[pd.Timestamp | None] = [
        _next_trading_date(trading_dates, pd.Timestamp(signal_date)) for signal_date in signals["date"]
    ]

    for idx, signal in signals.iterrows():
        signal_date = pd.Timestamp(signal["date"])
        execution_date = execution_dates[idx]
        if execution_date is None:
            continue
        signal_bar = _bar_at_or_before(bars, signal_date)
        execution_bar = _bar_at(bars, execution_date)
        if signal_bar is None or execution_bar is None:
            continue

        next_execution_date = None
        for candidate in execution_dates[idx + 1 :]:
            if candidate is not None:
                next_execution_date = candidate
                break

        if next_execution_date is not None:
            window_end_date = next_execution_date
            window_end_price = float(_bar_at(bars, next_execution_date)["Open"])
            window_end_price_type = "next_execution_open"
        else:
            last_bar = bars.iloc[-1]
            window_end_date = pd.Timestamp(last_bar["Date"])
            window_end_price = float(last_bar["Close"])
            window_end_price_type = "end_close"

        signal_close = float(signal_bar["Close"])
        execution_open = float(execution_bar["Open"])
        gap_return = execution_open / signal_close - 1.0
        post_execution_return = window_end_price / execution_open - 1.0
        signal_to_window_return = window_end_price / signal_close - 1.0
        target_position = float(signal["target_position"])

        rows.append(
            {
                "signal_date": signal_date.strftime("%Y-%m-%d"),
                "signal_reference_date": pd.Timestamp(signal_bar["Date"]).strftime("%Y-%m-%d"),
                "execution_date": execution_date.strftime("%Y-%m-%d"),
                "window_end": window_end_date.strftime("%Y-%m-%d"),
                "window_end_price_type": window_end_price_type,
                "calendar_gap_days": int((execution_date - signal_date).days),
                "cross_weekend_or_holiday": bool((execution_date - signal_date).days >= 3),
                "target_position": target_position,
                "action": signal.get("action", ""),
                "signal_close": signal_close,
                "execution_open": execution_open,
                "window_end_price": window_end_price,
                "gap_return": gap_return,
                "post_execution_return": post_execution_return,
                "signal_to_window_return": signal_to_window_return,
                "estimated_gap_not_captured": target_position * gap_return,
                "estimated_post_execution_capture": target_position * post_execution_return,
            }
        )

    return pd.DataFrame(rows)


def summarize_execution_gap_rows(rows: pd.DataFrame) -> dict[str, float | int]:
    if rows.empty:
        return {
            "signals": 0,
            "weekend_or_holiday_cases": 0,
            "positive_gap_cases": 0,
            "negative_gap_cases": 0,
            "mean_target_position": np.nan,
            "mean_gap_return": np.nan,
            "mean_post_execution_return": np.nan,
            "sum_estimated_gap_not_captured": np.nan,
            "sum_estimated_post_execution_capture": np.nan,
        }
    weekend_cases = int(rows["cross_weekend_or_holiday"].sum()) if "cross_weekend_or_holiday" in rows.columns else 0
    gap_capture = (
        rows["estimated_gap_not_captured"]
        if "estimated_gap_not_captured" in rows.columns
        else rows["target_position"] * rows["gap_return"]
    )
    post_capture = (
        rows["estimated_post_execution_capture"]
        if "estimated_post_execution_capture" in rows.columns
        else rows["target_position"] * rows["post_execution_return"]
    )
    return {
        "signals": int(len(rows)),
        "weekend_or_holiday_cases": weekend_cases,
        "positive_gap_cases": int((rows["gap_return"] > 0).sum()),
        "negative_gap_cases": int((rows["gap_return"] < 0).sum()),
        "mean_target_position": float(rows["target_position"].mean()),
        "mean_gap_return": float(rows["gap_return"].mean()),
        "mean_post_execution_return": float(rows["post_execution_return"].mean()),
        "sum_estimated_gap_not_captured": float(gap_capture.sum()),
        "sum_estimated_post_execution_capture": float(post_capture.sum()),
    }


def format_execution_gap_markdown(rows: pd.DataFrame, summary: dict[str, float | int], ticker: str) -> str:
    lines = [
        f"# Execution Gap Analysis - {ticker}",
        "",
        "## Summary",
        "",
        f"- signals: `{summary['signals']}`",
        f"- weekend/holiday execution cases: `{summary['weekend_or_holiday_cases']}`",
        f"- positive gap cases: `{summary['positive_gap_cases']}`",
        f"- negative gap cases: `{summary['negative_gap_cases']}`",
        f"- mean target position: `{_pct(summary['mean_target_position'])}`",
        f"- mean signal-close to execution-open gap: `{_pct(summary['mean_gap_return'])}`",
        f"- mean post-execution stock return: `{_pct(summary['mean_post_execution_return'])}`",
        f"- estimated gap not captured by T+1 execution: `{_pct(summary['sum_estimated_gap_not_captured'])}`",
        f"- estimated post-execution position capture: `{_pct(summary['sum_estimated_post_execution_capture'])}`",
        "",
        "## Signal Windows",
        "",
        "| signal_date | execution_date | window_end | target_position | gap_return | post_execution_return | signal_to_window_return | gap_not_captured | post_execution_capture |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in rows.iterrows():
        lines.append(
            f"| {row['signal_date']} | {row['execution_date']} | {row['window_end']} | "
            f"{_pct(row['target_position'])} | {_pct(row['gap_return'])} | "
            f"{_pct(row['post_execution_return'])} | {_pct(row['signal_to_window_return'])} | "
            f"{_pct(row['estimated_gap_not_captured'])} | {_pct(row['estimated_post_execution_capture'])} |"
        )
    lines.extend(
        [
            "",
            "## Reading",
            "",
            "- `gap_return`: signal-day close to next-trading-day open. This is the part a strict after-close T+1-open policy cannot capture.",
            "- `post_execution_return`: execution open to next execution open, or final end-date close for the last window.",
            "- `gap_not_captured` is `target_position * gap_return`; it is an exposure-adjusted estimate, not an executed PnL.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_execution_gap_analysis(
    *,
    signals_path: str | Path,
    ticker: str,
    output_dir: str | Path,
    end: str | None = None,
) -> dict[str, str]:
    signals_path = Path(signals_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    signals = pd.read_csv(signals_path)
    bars = load_market_data(ticker)
    if bars is None or bars.empty:
        raise RuntimeError(f"No prefetched market data found for {ticker}; run prefetch_agent_data.py first.")
    rows = build_execution_gap_rows(signals, bars, end=end)
    summary = summarize_execution_gap_rows(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"execution_gap_analysis_{ticker}.csv"
    md_path = output_dir / f"execution_gap_analysis_{ticker}.md"
    rows.to_csv(csv_path, index=False, encoding="utf-8")
    md_path.write_text(format_execution_gap_markdown(rows, summary, ticker), encoding="utf-8")
    return {"csv": str(csv_path), "md": str(md_path)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze signal close -> next open gap versus post-execution returns.")
    parser.add_argument("--signals", required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--end", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs = build_execution_gap_analysis(
        signals_path=args.signals,
        ticker=args.ticker,
        output_dir=args.output_dir,
        end=args.end,
    )
    print("Execution gap analysis built")
    for key, value in outputs.items():
        print(f"{key:8}: {value}")


if __name__ == "__main__":
    main()
