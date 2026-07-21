#!/usr/bin/env python3
"""Diagnose missed upside and alpha gaps from existing TradingAgents backtests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _compound_return(series: pd.Series) -> float:
    clean = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return float((1.0 + clean).prod() - 1.0)


def summarize_signal_windows(
    windows: pd.DataFrame,
    *,
    low_position_threshold: float = 0.30,
    upside_threshold: float = 0.05,
    alpha_opportunity_threshold: float = 0.05,
    strong_evidence_threshold: float = 4.0,
) -> dict[str, float | int]:
    if windows.empty:
        return {
            "signals": 0,
            "mean_target_position": np.nan,
            "low_position_missed_upside_cases": 0,
            "low_position_missed_upside_sum": 0.0,
            "underallocated_alpha_cases": 0,
            "underallocated_alpha_sum": 0.0,
            "strong_evidence_underallocation_cases": 0,
            "mean_window_stock_return": np.nan,
            "mean_window_agent_return": np.nan,
            "mean_window_benchmark_return": np.nan,
        }

    df = windows.copy()
    missed_mask = (
        (df["target_position"] <= low_position_threshold)
        & (df["stock_return"] >= upside_threshold)
        & (df["agent_return"] < df["stock_return"])
    )
    missed_upside = (df.loc[missed_mask, "stock_return"] - df.loc[missed_mask, "agent_return"]).clip(lower=0.0)
    stock_excess = df["stock_return"] - df["benchmark_return"]
    agent_excess = df["agent_return"] - df["benchmark_return"]
    underallocated_alpha_mask = (
        (df["target_position"] <= low_position_threshold)
        & (stock_excess >= alpha_opportunity_threshold)
        & (agent_excess < stock_excess)
    )
    underallocated_alpha = (stock_excess.loc[underallocated_alpha_mask] - agent_excess.loc[underallocated_alpha_mask]).clip(lower=0.0)
    if "return_evidence_score" in df.columns:
        evidence_score = pd.to_numeric(df["return_evidence_score"], errors="coerce").fillna(0.0)
    else:
        evidence_score = pd.Series(0.0, index=df.index)
    strong_evidence_mask = underallocated_alpha_mask & (evidence_score >= strong_evidence_threshold)

    return {
        "signals": int(len(df)),
        "mean_target_position": float(df["target_position"].mean()),
        "low_position_missed_upside_cases": int(missed_mask.sum()),
        "low_position_missed_upside_sum": float(missed_upside.sum()),
        "underallocated_alpha_cases": int(underallocated_alpha_mask.sum()),
        "underallocated_alpha_sum": float(underallocated_alpha.sum()),
        "strong_evidence_underallocation_cases": int(strong_evidence_mask.sum()),
        "mean_window_stock_return": float(df["stock_return"].mean()),
        "mean_window_agent_return": float(df["agent_return"].mean()),
        "mean_window_benchmark_return": float(df["benchmark_return"].mean()),
    }


def parse_position_calibration(raw: object) -> dict:
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def classify_position_gap(row: pd.Series, *, tolerance: float = 1e-6) -> str:
    raw_position = pd.to_numeric(pd.Series([row.get("raw_position")]), errors="coerce").iloc[0]
    target_position = pd.to_numeric(pd.Series([row.get("target_position")]), errors="coerce").iloc[0]
    if pd.isna(raw_position) or pd.isna(target_position):
        return "unknown"
    if abs(float(raw_position) - float(target_position)) <= tolerance:
        return "upstream_raw_low"
    if float(target_position) > float(raw_position):
        return "downstream_floor_raise"
    return "downstream_cap_reduce"


def return_evidence_from_signal(row: pd.Series) -> dict[str, object]:
    calibration = parse_position_calibration(row.get("position_calibration"))
    evidence = calibration.get("return_evidence") if isinstance(calibration, dict) else {}
    if not isinstance(evidence, dict):
        evidence = {}
    raw = evidence.get("raw") if isinstance(evidence.get("raw"), dict) else {}
    constraints = calibration.get("constraints") if isinstance(calibration.get("constraints"), list) else []
    constraint_rules = []
    for item in constraints:
        if isinstance(item, dict) and item.get("rule"):
            constraint_rules.append(str(item["rule"]))
    return {
        "return_evidence_score": evidence.get("score", np.nan),
        "return_evidence_source": evidence.get("source", ""),
        "trend_strength": raw.get("trend_strength", np.nan),
        "reward_risk_score": raw.get("reward_risk_score", np.nan),
        "catalyst_strength": raw.get("catalyst_strength", np.nan),
        "drawdown_risk": raw.get("drawdown_risk", np.nan),
        "data_quality": raw.get("data_quality", np.nan),
        "raw_position": calibration.get("raw_position", np.nan),
        "position_gap_source": classify_position_gap(
            pd.Series(
                {
                    "raw_position": calibration.get("raw_position", np.nan),
                    "target_position": row.get("target_position", np.nan),
                }
            )
        ),
        "constraint_rules": ",".join(constraint_rules),
    }


def format_instrument(ticker: str) -> str:
    ticker = ticker.upper().strip()
    if ticker.startswith(("SH", "SZ")):
        return ticker
    if len(ticker) == 6 and ticker.isdigit():
        return f"SH{ticker}" if ticker.startswith(("5", "6", "9")) else f"SZ{ticker}"
    return ticker


def load_stock_closes(provider_uri: str, ticker: str, start: str, end: str) -> pd.Series:
    import qlib
    from qlib.data import D

    qlib.init(provider_uri=provider_uri, region="cn")
    instrument = format_instrument(ticker)
    features = D.features([instrument], ["$close"], start_time=start, end_time=end, freq="day")
    closes = features["$close"].dropna()
    if isinstance(closes.index, pd.MultiIndex):
        closes.index = closes.index.get_level_values("datetime")
    closes.index = pd.to_datetime(closes.index)
    closes = closes.sort_index()
    if closes.empty:
        raise RuntimeError(f"No close data for {instrument} during {start} -> {end}")
    return closes.astype(float)


def build_signal_windows(signals: pd.DataFrame, report: pd.DataFrame, closes: pd.Series) -> pd.DataFrame:
    signals = signals.copy()
    signals["date"] = pd.to_datetime(signals["date"])
    signals["target_position"] = pd.to_numeric(signals["target_position"], errors="coerce")
    signals = signals.dropna(subset=["date", "target_position"]).sort_values("date")

    report = report.copy()
    report.index = pd.to_datetime(report.index)
    report = report.sort_index()
    closes = closes.sort_index()

    rows = []
    report_dates = report.index
    for idx, row in signals.iterrows():
        signal_date = row["date"]
        future_dates = report_dates[report_dates > signal_date]
        if len(future_dates) == 0:
            continue
        exec_date = future_dates[0]
        next_signal_dates = signals.loc[signals.index > idx, "date"]
        if len(next_signal_dates) > 0:
            next_exec_candidates = report_dates[report_dates > next_signal_dates.iloc[0]]
            window_end = next_exec_candidates[0] if len(next_exec_candidates) > 0 else report_dates[-1]
        else:
            window_end = report_dates[-1]

        window_report = report.loc[(report.index >= exec_date) & (report.index < window_end)]
        window_closes = closes.loc[(closes.index >= exec_date) & (closes.index < window_end)]
        if window_report.empty or len(window_closes) < 2:
            continue

        rows.append(
            {
                "date": signal_date.strftime("%Y-%m-%d"),
                "execution_date": exec_date.strftime("%Y-%m-%d"),
                "window_end": window_report.index[-1].strftime("%Y-%m-%d"),
                "target_position": float(row["target_position"]),
                "stock_return": float(window_closes.iloc[-1] / window_closes.iloc[0] - 1.0),
                "benchmark_return": _compound_return(window_report.get("bench", pd.Series(0.0, index=window_report.index))),
                "agent_return": _compound_return(window_report["return"]),
                "action": row.get("action", ""),
                **return_evidence_from_signal(row),
            }
        )

    out = pd.DataFrame(rows)
    if not out.empty:
        out["stock_excess_vs_benchmark"] = out["stock_return"] - out["benchmark_return"]
        out["agent_excess_vs_benchmark"] = out["agent_return"] - out["benchmark_return"]
        out["missed_upside"] = (out["stock_return"] - out["agent_return"]).clip(lower=0.0)
    return out


def format_markdown(windows: pd.DataFrame, summary: dict, ticker: str) -> str:
    lines = [
        f"# Alpha Gap Diagnostics - {ticker}",
        "",
        "## Summary",
        "",
        f"- signals: {summary['signals']}",
        f"- mean target_position: {summary['mean_target_position']:.2%}",
        f"- low-position missed-upside cases: {summary['low_position_missed_upside_cases']}",
        f"- missed-upside sum: {summary['low_position_missed_upside_sum']:.2%}",
        f"- underallocated alpha cases: {summary['underallocated_alpha_cases']}",
        f"- underallocated alpha sum: {summary['underallocated_alpha_sum']:.2%}",
        f"- strong-evidence underallocation cases: {summary['strong_evidence_underallocation_cases']}",
        f"- mean stock window return: {summary['mean_window_stock_return']:.2%}",
        f"- mean agent window return: {summary['mean_window_agent_return']:.2%}",
        f"- mean benchmark window return: {summary['mean_window_benchmark_return']:.2%}",
        "",
        "## Largest Missed Upside",
        "",
        "| signal_date | target_position | stock_return | agent_return | benchmark_return | missed_upside |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    if not windows.empty:
        for _, row in windows.sort_values("missed_upside", ascending=False).head(10).iterrows():
            lines.append(
                f"| {row['date']} | {row['target_position']:.2%} | {row['stock_return']:.2%} | "
                f"{row['agent_return']:.2%} | {row['benchmark_return']:.2%} | {row['missed_upside']:.2%} |"
            )
    lines.extend(
        [
            "",
            "## Underallocated Alpha Cases",
            "",
            "| signal_date | raw_position | target_position | gap_source | stock_excess | agent_excess | alpha_gap | evidence_score | evidence_source | constraint_rules |",
            "| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    if not windows.empty:
        df = windows.copy()
        df["stock_excess_vs_benchmark"] = df["stock_return"] - df["benchmark_return"]
        df["agent_excess_vs_benchmark"] = df["agent_return"] - df["benchmark_return"]
        df["alpha_gap"] = (df["stock_excess_vs_benchmark"] - df["agent_excess_vs_benchmark"]).clip(lower=0.0)
        alpha_cases = df[(df["target_position"] <= 0.30) & (df["stock_excess_vs_benchmark"] >= 0.05)]
        for _, row in alpha_cases.sort_values("alpha_gap", ascending=False).head(10).iterrows():
            evidence_score = row.get("return_evidence_score", np.nan)
            evidence_score_text = "" if pd.isna(evidence_score) else f"{float(evidence_score):.1f}"
            lines.append(
                f"| {row['date']} | {float(row.get('raw_position', np.nan)):.2%} | {row['target_position']:.2%} | "
                f"{row.get('position_gap_source', '')} | "
                f"{row['stock_excess_vs_benchmark']:.2%} | {row['agent_excess_vs_benchmark']:.2%} | "
                f"{row['alpha_gap']:.2%} | {evidence_score_text} | {row.get('return_evidence_source', '')} | "
                f"{row.get('constraint_rules', '')} |"
            )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose low-position missed upside from a Qlib backtest.")
    parser.add_argument("--signals", required=True, help="Signal CSV with target_position")
    parser.add_argument("--report", required=True, help="Qlib backtest report CSV for the same signal file")
    parser.add_argument("--provider-uri", required=True, help="Qlib provider_uri")
    parser.add_argument("--ticker", required=True, help="A-share ticker")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--low-position-threshold", type=float, default=0.30)
    parser.add_argument("--upside-threshold", type=float, default=0.05)
    parser.add_argument("--alpha-opportunity-threshold", type=float, default=0.05)
    parser.add_argument("--strong-evidence-threshold", type=float, default=4.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    signals = pd.read_csv(args.signals)
    report = pd.read_csv(args.report, index_col=0)
    closes = load_stock_closes(args.provider_uri, args.ticker, args.start, args.end)
    windows = build_signal_windows(signals, report, closes)
    summary = summarize_signal_windows(
        windows,
        low_position_threshold=args.low_position_threshold,
        upside_threshold=args.upside_threshold,
        alpha_opportunity_threshold=args.alpha_opportunity_threshold,
        strong_evidence_threshold=args.strong_evidence_threshold,
    )

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"alpha_gap_windows_{args.ticker}_{args.start}_{args.end}.csv"
    md_path = output_dir / f"alpha_gap_diagnostics_{args.ticker}_{args.start}_{args.end}.md"
    windows.to_csv(csv_path, index=False)
    md_path.write_text(format_markdown(windows, summary, args.ticker), encoding="utf-8")

    print("Alpha gap diagnostics finished")
    print(f"windows_csv : {csv_path}")
    print(f"report_md   : {md_path}")
    print(f"missed_cases: {summary['low_position_missed_upside_cases']}")


if __name__ == "__main__":
    main()
