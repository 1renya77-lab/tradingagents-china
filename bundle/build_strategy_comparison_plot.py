#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from strategy_baselines import STRATEGY_LABELS


ORDER = ["buy_hold_100", "macd", "kdj_rsi", "zmr", "sma", "agent"]


def _find_report(backtests_dir: Path, strategy: str) -> Path:
    matches = sorted((backtests_dir / strategy).glob("qlib_signal_backtest_report_*.csv"))
    if not matches:
        raise FileNotFoundError(f"report csv not found for strategy={strategy} in {backtests_dir / strategy}")
    return matches[-1]


def build_strategy_comparison_plot(
    *,
    comparison_csv: str | Path,
    backtests_dir: str | Path,
    output_dir: str | Path | None = None,
    ticker: str | None = None,
) -> dict[str, str]:
    comparison_csv = Path(comparison_csv).expanduser().resolve()
    backtests_dir = Path(backtests_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve() if output_dir else comparison_csv.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    cmp_df = pd.read_csv(comparison_csv)
    cmp_df["strategy"] = cmp_df["strategy"].astype(str)
    cmp_df["order"] = cmp_df["strategy"].map({name: idx for idx, name in enumerate(ORDER)}).fillna(999)
    cmp_df = cmp_df.sort_values(["order", "strategy"]).reset_index(drop=True)
    ticker = ticker or comparison_csv.stem.replace("comparison_", "")

    png_path = output_dir / f"strategy_plot_{ticker}.png"
    md_path = output_dir / f"strategy_plot_{ticker}.md"

    fig, ax = plt.subplots(figsize=(11.5, 6.8))
    for _, row in cmp_df.iterrows():
        strategy = row["strategy"]
        report_path = _find_report(backtests_dir, strategy)
        report = pd.read_csv(report_path, index_col=0)
        report.index = pd.to_datetime(report.index)
        if "account" not in report.columns or report.empty:
            continue
        curve = report["account"].astype(float) / float(report["account"].iloc[0])
        label = STRATEGY_LABELS.get(strategy, strategy)
        lw = 2.4 if strategy == "agent" else 1.8
        alpha = 0.95 if strategy == "agent" else 0.85
        ax.plot(curve.index, curve.values, label=label, linewidth=lw, alpha=alpha)

    ax.set_title(f"Strategy Comparison - Cumulative Returns for {ticker}", fontsize=16)
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative Return")
    ax.grid(True, linestyle="--", alpha=0.35)
    legend = ax.legend(title="Strategies", loc="best", frameon=True)
    for text in legend.get_texts():
        if text.get_text() == "TradingAgents":
            text.set_weight("bold")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(png_path, dpi=220, bbox_inches="tight")
    plt.close(fig)

    md_lines = [
        f"# {ticker} Strategy Plot",
        "",
        f"![strategy plot]({png_path})",
        "",
        "- All curves are normalized to the first trading day of each backtest report.",
        "- TradingAgents is drawn with a thicker line for easier comparison.",
    ]
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return {"png": str(png_path), "md": str(md_path)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a cumulative-return comparison figure from baseline backtests.")
    parser.add_argument("--comparison-csv", required=True)
    parser.add_argument("--backtests-dir", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--ticker", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs = build_strategy_comparison_plot(
        comparison_csv=args.comparison_csv,
        backtests_dir=args.backtests_dir,
        output_dir=args.output_dir or None,
        ticker=args.ticker,
    )
    print("Strategy comparison plot built")
    for key, value in outputs.items():
        print(f"{key:10}: {value}")


if __name__ == "__main__":
    main()
