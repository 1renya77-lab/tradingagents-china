#!/usr/bin/env python3
"""Compare old vs recalibrated signals on the same price windows.

This is a lightweight offline diagnostic that estimates how much extra alpha
exposure a new position-calibration rule would capture before committing to a
full Qlib rerun. It uses the same signal windows as alpha_gap_diagnostics.py
but replaces realized agent return with a position-implied proxy:

    implied_return = target_position * stock_return
                   + (1 - target_position) * benchmark_return
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from alpha_gap_diagnostics import build_signal_windows, load_stock_closes


def add_implied_return_columns(windows: pd.DataFrame) -> pd.DataFrame:
    df = windows.copy()
    if df.empty:
        return df
    df["implied_return"] = (
        pd.to_numeric(df["target_position"], errors="coerce").fillna(0.0) * pd.to_numeric(df["stock_return"], errors="coerce").fillna(0.0)
        + (1.0 - pd.to_numeric(df["target_position"], errors="coerce").fillna(0.0))
        * pd.to_numeric(df["benchmark_return"], errors="coerce").fillna(0.0)
    )
    df["implied_excess"] = df["implied_return"] - pd.to_numeric(df["benchmark_return"], errors="coerce").fillna(0.0)
    df["capture_ratio"] = (
        pd.to_numeric(df["target_position"], errors="coerce").fillna(0.0)
    )
    return df


def summarize_version(label: str, windows: pd.DataFrame) -> dict[str, float | int | str]:
    if windows.empty:
        return {
            "label": label,
            "signals": 0,
            "mean_target_position": 0.0,
            "mean_stock_return": 0.0,
            "mean_benchmark_return": 0.0,
            "mean_implied_return": 0.0,
            "mean_implied_excess": 0.0,
            "positive_stock_windows": 0,
            "mean_capture_on_positive_windows": 0.0,
        }
    positive = windows[windows["stock_return"] > 0].copy()
    return {
        "label": label,
        "signals": int(len(windows)),
        "mean_target_position": float(windows["target_position"].mean()),
        "mean_stock_return": float(windows["stock_return"].mean()),
        "mean_benchmark_return": float(windows["benchmark_return"].mean()),
        "mean_implied_return": float(windows["implied_return"].mean()),
        "mean_implied_excess": float(windows["implied_excess"].mean()),
        "positive_stock_windows": int(len(positive)),
        "mean_capture_on_positive_windows": float(positive["capture_ratio"].mean()) if not positive.empty else 0.0,
    }


def build_delta_table(old_windows: pd.DataFrame, new_windows: pd.DataFrame) -> pd.DataFrame:
    old_cols = [
        "date",
        "execution_date",
        "window_end",
        "target_position",
        "stock_return",
        "benchmark_return",
        "implied_return",
        "implied_excess",
    ]
    new_cols = [
        "date",
        "target_position",
        "implied_return",
        "implied_excess",
        "position_gap_source",
        "return_evidence_score",
        "return_evidence_source",
        "constraint_rules",
    ]
    old = old_windows[old_cols].rename(
        columns={
            "target_position": "old_target_position",
            "implied_return": "old_implied_return",
            "implied_excess": "old_implied_excess",
        }
    )
    new = new_windows[new_cols].rename(
        columns={
            "target_position": "new_target_position",
            "implied_return": "new_implied_return",
            "implied_excess": "new_implied_excess",
        }
    )
    merged = old.merge(new, on="date", how="inner")
    merged["position_delta"] = merged["new_target_position"] - merged["old_target_position"]
    merged["implied_excess_delta"] = merged["new_implied_excess"] - merged["old_implied_excess"]
    merged["implied_return_delta"] = merged["new_implied_return"] - merged["old_implied_return"]
    return merged.sort_values(["implied_excess_delta", "position_delta"], ascending=False)


def render_markdown(old_summary: dict, new_summary: dict, delta: pd.DataFrame, *, ticker: str) -> str:
    def pct(v: float) -> str:
        return f"{v:.2%}"

    lines = [
        f"# Offline Recalibration Compare - {ticker}",
        "",
        "## Summary",
        "",
        "| version | signals | mean_target_position | mean_implied_return | mean_implied_excess | positive_windows | mean_capture_on_positive_windows |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| {old_summary['label']} | {old_summary['signals']} | {pct(old_summary['mean_target_position'])} | {pct(old_summary['mean_implied_return'])} | {pct(old_summary['mean_implied_excess'])} | {old_summary['positive_stock_windows']} | {pct(old_summary['mean_capture_on_positive_windows'])} |",
        f"| {new_summary['label']} | {new_summary['signals']} | {pct(new_summary['mean_target_position'])} | {pct(new_summary['mean_implied_return'])} | {pct(new_summary['mean_implied_excess'])} | {new_summary['positive_stock_windows']} | {pct(new_summary['mean_capture_on_positive_windows'])} |",
        "",
        "## Delta",
        "",
        f"- mean_target_position delta: {pct(new_summary['mean_target_position'] - old_summary['mean_target_position'])}",
        f"- mean_implied_return delta: {pct(new_summary['mean_implied_return'] - old_summary['mean_implied_return'])}",
        f"- mean_implied_excess delta: {pct(new_summary['mean_implied_excess'] - old_summary['mean_implied_excess'])}",
        f"- mean_capture_on_positive_windows delta: {pct(new_summary['mean_capture_on_positive_windows'] - old_summary['mean_capture_on_positive_windows'])}",
        "",
        "## Largest Positive Deltas",
        "",
        "| signal_date | old_target | new_target | position_delta | stock_return | benchmark_return | old_implied_excess | new_implied_excess | implied_excess_delta | gap_source | evidence_score | constraint_rules |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for _, row in delta.head(15).iterrows():
        evidence = row.get("return_evidence_score")
        evidence_text = "" if pd.isna(evidence) else f"{float(evidence):.1f}"
        lines.append(
            f"| {row['date']} | {pct(row['old_target_position'])} | {pct(row['new_target_position'])} | "
            f"{pct(row['position_delta'])} | {pct(row['stock_return'])} | {pct(row['benchmark_return'])} | "
            f"{pct(row['old_implied_excess'])} | {pct(row['new_implied_excess'])} | {pct(row['implied_excess_delta'])} | "
            f"{row.get('position_gap_source', '')} | {evidence_text} | {row.get('constraint_rules', '')} |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline compare old vs recalibrated signals on the same price windows.")
    parser.add_argument("--old-signals", required=True)
    parser.add_argument("--new-signals", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--old-label", default="old")
    parser.add_argument("--new-label", default="new")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    old_signals = pd.read_csv(args.old_signals)
    new_signals = pd.read_csv(args.new_signals)
    report = pd.read_csv(args.report, index_col=0)
    closes = load_stock_closes(args.provider_uri, args.ticker, args.start, args.end)

    old_windows = add_implied_return_columns(build_signal_windows(old_signals, report, closes))
    new_windows = add_implied_return_columns(build_signal_windows(new_signals, report, closes))
    old_summary = summarize_version(args.old_label, old_windows)
    new_summary = summarize_version(args.new_label, new_windows)
    delta = build_delta_table(old_windows, new_windows)

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    delta_csv = output_dir / f"offline_recalibration_delta_{args.ticker}_{args.start}_{args.end}.csv"
    summary_md = output_dir / f"offline_recalibration_compare_{args.ticker}_{args.start}_{args.end}.md"
    delta.to_csv(delta_csv, index=False)
    summary_md.write_text(render_markdown(old_summary, new_summary, delta, ticker=args.ticker), encoding="utf-8")

    print("Offline recalibration comparison finished")
    print(f"delta_csv : {delta_csv}")
    print(f"summary_md: {summary_md}")


if __name__ == "__main__":
    main()
