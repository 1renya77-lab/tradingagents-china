#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from strategy_baselines import STRATEGY_LABELS


CATEGORY_MAP = {
    "buy_hold_100": "Market",
    "macd": "Rule-based",
    "kdj_rsi": "Rule-based",
    "zmr": "Rule-based",
    "sma": "Rule-based",
    "agent": "Ours",
}

ORDER = ["buy_hold_100", "macd", "kdj_rsi", "zmr", "sma", "agent"]


def _fmt_pct_points(value: float) -> str:
    return f"{float(value) * 100:.2f}"


def _fmt_sharpe(value: float) -> str:
    return f"{float(value):.2f}"


def _fmt_mdd(value: float) -> str:
    return f"{abs(float(value)) * 100:.2f}"


def _fmt_optional_pct_points(value: float) -> str:
    if pd.isna(value):
        return "-"
    return f"{float(value) * 100:.2f}"


def _load_table_frame(comparison_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(comparison_csv)
    df["strategy"] = df["strategy"].astype(str)
    df["order"] = df["strategy"].map({name: idx for idx, name in enumerate(ORDER)}).fillna(999)
    df = df.sort_values(["order", "strategy"]).reset_index(drop=True)
    df["Category"] = df["strategy"].map(CATEGORY_MAP).fillna("Other")
    df["Models"] = df["strategy"].map(STRATEGY_LABELS).fillna(df["strategy"])
    df["CR%↑"] = df["total_return"].map(_fmt_pct_points)
    df["ARR%↑"] = df["annual_return"].map(_fmt_pct_points)
    df["SR↑"] = df["sharpe"].map(_fmt_sharpe)
    if "win_rate" in df.columns:
        df["WR%↑"] = df["win_rate"].map(_fmt_optional_pct_points)
    else:
        df["WR%↑"] = "-"
    df["MDD%↓"] = df["max_drawdown"].map(_fmt_mdd)
    return df


def _improvement_row(df: pd.DataFrame) -> dict[str, str]:
    baselines = df[df["strategy"] != "agent"].copy()
    ours = df[df["strategy"] == "agent"]
    if baselines.empty or ours.empty:
        return {"Category": "", "Models": "Improvement(%)", "CR%↑": "-", "ARR%↑": "-", "SR↑": "-", "WR%↑": "-", "MDD%↓": "-"}
    ours_row = ours.iloc[0]
    best_cr = baselines["total_return"].max()
    best_arr = baselines["annual_return"].max()
    best_sr = baselines["sharpe"].max()
    best_wr = baselines["win_rate"].max() if "win_rate" in baselines.columns else None
    best_mdd = baselines["max_drawdown"].abs().min()
    ours_mdd = abs(float(ours_row["max_drawdown"]))
    mdd_improve = best_mdd - ours_mdd
    wr_improve = None
    if best_wr is not None and not pd.isna(best_wr) and "win_rate" in ours_row:
        wr_improve = float(ours_row["win_rate"]) - float(best_wr)
    return {
        "Category": "",
        "Models": "Improvement(%)",
        "CR%↑": f"{(float(ours_row['total_return']) - float(best_cr)) * 100:.2f}",
        "ARR%↑": f"{(float(ours_row['annual_return']) - float(best_arr)) * 100:.2f}",
        "SR↑": f"{float(ours_row['sharpe']) - float(best_sr):.2f}",
        "WR%↑": f"{wr_improve * 100:.2f}" if wr_improve is not None else "-",
        "MDD%↓": f"{mdd_improve * 100:.2f}" if mdd_improve > 0 else "-",
    }


def build_strategy_comparison_table(
    *,
    comparison_csv: str | Path,
    output_dir: str | Path | None = None,
    ticker: str | None = None,
) -> dict[str, str]:
    comparison_csv = Path(comparison_csv).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve() if output_dir else comparison_csv.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    df = _load_table_frame(comparison_csv)
    ticker = ticker or comparison_csv.stem.replace("comparison_", "")

    view = df[["Category", "Models", "CR%↑", "ARR%↑", "SR↑", "WR%↑", "MDD%↓"]].copy()
    view = pd.concat([view, pd.DataFrame([_improvement_row(df)])], ignore_index=True)

    md_path = output_dir / f"strategy_table_{ticker}.md"
    png_path = output_dir / f"strategy_table_{ticker}.png"
    csv_path = output_dir / f"strategy_table_{ticker}.csv"
    view.to_csv(csv_path, index=False)
    md_lines = [
        f"# {ticker} Strategy Table",
        "",
        view.to_markdown(index=False),
        "",
        "- `CR%` = total return",
        "- `ARR%` = annualized return",
        "- `SR` = Sharpe ratio",
        "- `WR%` = daily win rate, excluding flat return days",
        "- `MDD%` = absolute max drawdown percentage",
    ]
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    fig, ax = plt.subplots(figsize=(10.5, 2.8 + 0.28 * len(view)))
    ax.axis("off")
    table = ax.table(
        cellText=view.values,
        colLabels=view.columns,
        loc="center",
        cellLoc="center",
        colLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1, 1.5)

    metric_keys = ["CR%↑", "ARR%↑", "SR↑", "WR%↑", "MDD%↓"]
    baseline_df = df[df["strategy"] != "agent"].copy()
    best_values = {
        "CR%↑": baseline_df["total_return"].max() if not baseline_df.empty else None,
        "ARR%↑": baseline_df["annual_return"].max() if not baseline_df.empty else None,
        "SR↑": baseline_df["sharpe"].max() if not baseline_df.empty else None,
        "WR%↑": baseline_df["win_rate"].max() if not baseline_df.empty and "win_rate" in baseline_df.columns else None,
        "MDD%↓": baseline_df["max_drawdown"].abs().min() if not baseline_df.empty else None,
    }

    col_index = {name: idx for idx, name in enumerate(view.columns)}
    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#f5f5f5")
            continue
        model = view.iloc[row - 1]["Models"]
        if model == "TradingAgents":
            cell.set_text_props(weight="bold")
        if view.iloc[row - 1]["Models"] == "Improvement(%)":
            cell.set_facecolor("#fafafa")

    for metric in metric_keys:
        source_col = {
            "CR%↑": "total_return",
            "ARR%↑": "annual_return",
            "SR↑": "sharpe",
            "WR%↑": "win_rate",
            "MDD%↓": "max_drawdown",
        }[metric]
        for ridx, raw in df.reset_index(drop=True).iterrows():
            display_row = ridx + 1
            cell = table[(display_row, col_index[metric])]
            if source_col not in raw or pd.isna(raw[source_col]):
                continue
            value = abs(float(raw[source_col])) if metric == "MDD%↓" else float(raw[source_col])
            target = best_values[metric]
            is_best = value == target if target is not None else False
            if raw["strategy"] == "agent":
                cell.get_text().set_color("#0b8f3a")
                cell.get_text().set_weight("bold")
            elif is_best:
                cell.get_text().set_color("#0b8f3a")
                cell.get_text().set_weight("bold")

    fig.suptitle(f"{ticker} Strategy Comparison", fontsize=16, y=0.98)
    fig.tight_layout()
    fig.savefig(png_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return {"csv": str(csv_path), "md": str(md_path), "png": str(png_path)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a paper-style strategy comparison table from comparison CSV.")
    parser.add_argument("--comparison-csv", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--ticker", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs = build_strategy_comparison_table(
        comparison_csv=args.comparison_csv,
        output_dir=args.output_dir or None,
        ticker=args.ticker,
    )
    print("Strategy comparison table built")
    for key, value in outputs.items():
        print(f"{key:10}: {value}")


if __name__ == "__main__":
    main()
