#!/usr/bin/env python3
"""Build post-hoc feedback windows for TradingAgents mechanism studies."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from alpha_gap_diagnostics import build_signal_windows, load_stock_closes


def _as_float(row: pd.Series, key: str, default: float = 0.0) -> float:
    try:
        value = float(row.get(key, default))
        return value if np.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def classify_case_type(row: pd.Series, *, low: float = 0.30, high: float = 0.65, move: float = 0.03) -> str:
    position = _as_float(row, "target_position")
    stock_return = _as_float(row, "stock_return")
    agent_return = _as_float(row, "agent_return")

    if stock_return >= move and position >= high:
        return "success_attack"
    if stock_return <= -move and position <= low:
        return "success_defense"
    if stock_return >= move and position <= low and agent_return < stock_return:
        return "missed_upside"
    if stock_return <= -move and position >= high:
        return "wrong_exposure"
    return "neutral"


def score_decision_quality(row: pd.Series) -> float:
    position = _as_float(row, "target_position")
    stock_return = _as_float(row, "stock_return")
    benchmark_return = _as_float(row, "benchmark_return")
    agent_return = _as_float(row, "agent_return")
    stock_excess = stock_return - benchmark_return
    agent_excess = agent_return - benchmark_return

    if stock_excess > 0:
        directional = position
    elif stock_excess < 0:
        directional = 1.0 - position
    else:
        directional = 0.5

    excess_component = np.tanh(agent_excess * 8.0) * 0.25
    return float(np.clip(directional + excess_component, 0.0, 1.0))


def add_feedback_columns(windows: pd.DataFrame, *, run_name: str = "", experiment_mode: str = "", ticker: str = "") -> pd.DataFrame:
    out = windows.copy()
    if out.empty:
        return out
    out.insert(0, "run_name", run_name)
    out.insert(1, "experiment_mode", experiment_mode)
    out.insert(2, "ticker", ticker)
    out = out.rename(columns={"date": "signal_date"})
    out["stock_excess"] = out["stock_return"] - out["benchmark_return"]
    out["agent_excess"] = out["agent_return"] - out["benchmark_return"]
    out["downside_protection"] = np.where(
        out["stock_return"] < 0,
        (out["agent_return"] - out["stock_return"]).clip(lower=0.0),
        0.0,
    )
    out["wrong_exposure"] = np.where(
        (out["stock_return"] < 0) & (out["target_position"] >= 0.65),
        (out["stock_return"] - out["agent_return"]).abs(),
        0.0,
    )
    out["decision_quality_score"] = out.apply(score_decision_quality, axis=1)
    out["case_type"] = out.apply(classify_case_type, axis=1)
    return out


def build_feedback_windows(
    *,
    signals_path: Path,
    report_path: Path,
    provider_uri: str,
    ticker: str,
    start: str,
    end: str,
    output_path: Path,
    run_name: str = "",
    experiment_mode: str = "",
) -> Path:
    signals = pd.read_csv(signals_path)
    report = pd.read_csv(report_path, index_col=0)
    closes = load_stock_closes(provider_uri, ticker, start, end)
    windows = build_signal_windows(signals, report, closes)
    feedback = add_feedback_columns(
        windows,
        run_name=run_name,
        experiment_mode=experiment_mode,
        ticker=ticker,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    feedback.to_csv(output_path, index=False, encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build post-hoc feedback windows.")
    parser.add_argument("--signals", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-name", default="")
    parser.add_argument("--experiment-mode", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = build_feedback_windows(
        signals_path=Path(args.signals),
        report_path=Path(args.report),
        provider_uri=args.provider_uri,
        ticker=args.ticker,
        start=args.start,
        end=args.end,
        output_path=Path(args.output),
        run_name=args.run_name,
        experiment_mode=args.experiment_mode,
    )
    print(f"feedback_windows: {path}")


if __name__ == "__main__":
    main()
