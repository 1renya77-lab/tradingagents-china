"""Evaluate TradingAgents signal CSV files with forward returns and alpha."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


bundle_root = Path(__file__).parent
DEFAULT_OUTPUT_DIR = bundle_root / "outputs" / "evaluations"


def _format_stock_code(ticker: str) -> str:
    raw = str(ticker).strip().upper()
    if raw.startswith(("SH", "SZ")):
        return raw
    if raw.endswith(".SH"):
        return f"SH{raw[:-3]}"
    if raw.endswith(".SZ"):
        return f"SZ{raw[:-3]}"
    if raw.isdigit() and len(raw) == 6:
        return f"SH{raw}" if raw.startswith(("5", "6", "9")) else f"SZ{raw}"
    return raw


def load_price_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Load A-share daily close prices via the existing baostock provider."""
    from tradingagents.dataflows.baostock_provider import get_kline_data

    df = get_kline_data(
        _format_stock_code(ticker),
        start_date,
        end_date,
        freq="d",
        adjust="qfq",
    )
    if df is None or df.empty:
        raise ValueError(f"No price data for {ticker} from {start_date} to {end_date}")

    out = df.rename(columns={"date": "date", "close": "close"}).copy()
    out["date"] = pd.to_datetime(out["date"])
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out = out.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    return out[["date", "close"]]


def _forward_return(price_df: pd.DataFrame, signal_date: str, holding_days: int) -> tuple[float | None, int | None]:
    trade_dt = pd.to_datetime(signal_date)
    available = price_df[price_df["date"] >= trade_dt].reset_index(drop=True)
    if len(available) < 2:
        return None, None
    actual_days = min(holding_days, len(available) - 1)
    start_price = float(available["close"].iloc[0])
    end_price = float(available["close"].iloc[actual_days])
    if start_price <= 0:
        return None, None
    return (end_price - start_price) / start_price, actual_days


def attach_forward_returns(
    signals: pd.DataFrame,
    holding_days: int = 1,
    benchmark: str = "SH000905",
    hold_alpha_band: float = 0.01,
) -> pd.DataFrame:
    """Attach forward return, benchmark return, alpha and actual holding days."""
    required = {"date", "ticker"}
    missing = required - set(signals.columns)
    if missing:
        raise ValueError(f"Signal CSV missing required columns: {sorted(missing)}")

    df = signals.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    min_date = pd.to_datetime(df["date"]).min()
    max_date = pd.to_datetime(df["date"]).max() + timedelta(days=holding_days + 14)
    start = min_date.strftime("%Y-%m-%d")
    end = max_date.strftime("%Y-%m-%d")

    result_frames = []
    for ticker, group in df.groupby("ticker", sort=False):
        stock_prices = load_price_data(str(ticker), start, end)
        bench_prices = load_price_data(benchmark, start, end)
        group = group.copy()
        forward_returns = []
        benchmark_returns = []
        alphas = []
        actual_holding_days = []

        for signal_date in group["date"]:
            stock_ret, stock_days = _forward_return(stock_prices, signal_date, holding_days)
            bench_ret, bench_days = _forward_return(bench_prices, signal_date, holding_days)
            if stock_ret is None or bench_ret is None:
                forward_returns.append(None)
                benchmark_returns.append(None)
                alphas.append(None)
                actual_holding_days.append(None)
                continue
            actual_days = min(stock_days or 0, bench_days or 0)
            forward_returns.append(stock_ret)
            benchmark_returns.append(bench_ret)
            alphas.append(stock_ret - bench_ret)
            actual_holding_days.append(actual_days)

        group["forward_return"] = forward_returns
        group["benchmark_return"] = benchmark_returns
        group["alpha"] = alphas
        group["actual_holding_days"] = actual_holding_days
        group = attach_decision_metrics(group, hold_alpha_band=hold_alpha_band)
        result_frames.append(group)

    return pd.concat(result_frames, ignore_index=True)


def _action_kind(action: str) -> str:
    text = str(action or "").strip().lower()
    if any(word in text for word in ("买入", "建仓", "加仓", "buy", "overweight")):
        return "buy"
    if any(word in text for word in ("卖出", "清仓", "减仓", "sell", "underweight")):
        return "sell"
    return "hold"


def attach_decision_metrics(df: pd.DataFrame, hold_alpha_band: float = 0.01) -> pd.DataFrame:
    """Add action-aware signal quality metrics based on alpha direction."""
    out = df.copy()
    decision_alpha = []
    directional_hit = []
    for _, row in out.iterrows():
        alpha = pd.to_numeric(row.get("alpha"), errors="coerce")
        if pd.isna(alpha):
            decision_alpha.append(None)
            directional_hit.append(None)
            continue

        action = _action_kind(row.get("action", ""))
        if action == "buy":
            decision_alpha.append(float(alpha))
            directional_hit.append(bool(alpha > 0))
        elif action == "sell":
            decision_alpha.append(float(-alpha))
            directional_hit.append(bool(alpha < 0))
        else:
            decision_alpha.append(float(-abs(alpha)))
            directional_hit.append(bool(abs(alpha) <= hold_alpha_band))

    out["decision_alpha"] = decision_alpha
    out["directional_hit"] = directional_hit
    return out


def _compound_return(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return float("nan")
    return float((1.0 + values).prod() - 1.0)


def _max_drawdown(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return float("nan")
    equity = (1.0 + values).cumprod()
    peak = equity.cummax()
    drawdown = equity / peak - 1.0
    return float(drawdown.min())


def build_summary(df: pd.DataFrame, name: str = "signals") -> dict:
    """Build aggregate signal and forward-return metrics."""
    numeric = df.copy()
    for col in [
        "confidence",
        "risk_score",
        "score",
        "forward_return",
        "benchmark_return",
        "alpha",
        "decision_alpha",
    ]:
        if col in numeric.columns:
            numeric[col] = pd.to_numeric(numeric[col], errors="coerce")

    returns = numeric.get("forward_return", pd.Series(dtype=float))
    alpha = numeric.get("alpha", pd.Series(dtype=float))
    decision_alpha = numeric.get("decision_alpha", pd.Series(dtype=float))
    directional_hit = numeric.get("directional_hit", pd.Series(dtype=object)).dropna()

    return {
        "name": name,
        "rows": int(len(df)),
        "action_counts": df.get("action", pd.Series(dtype=str)).fillna("N/A").value_counts().to_dict(),
        "avg_confidence": float(numeric["confidence"].mean()) if "confidence" in numeric else float("nan"),
        "avg_risk_score": float(numeric["risk_score"].mean()) if "risk_score" in numeric else float("nan"),
        "avg_score": float(numeric["score"].mean()) if "score" in numeric else float("nan"),
        "avg_forward_return": float(returns.mean()) if not returns.empty else float("nan"),
        "avg_benchmark_return": float(numeric["benchmark_return"].mean()) if "benchmark_return" in numeric else float("nan"),
        "avg_alpha": float(alpha.mean()) if not alpha.empty else float("nan"),
        "avg_decision_alpha": float(decision_alpha.mean()) if not decision_alpha.empty else float("nan"),
        "cumulative_return": _compound_return(returns),
        "max_drawdown": _max_drawdown(returns),
        "win_rate": float((returns > 0).mean()) if not returns.empty else float("nan"),
        "directional_hit_rate": float(directional_hit.astype(bool).mean()) if not directional_hit.empty else float("nan"),
    }


def _pct(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value:+.2%}"


def _num(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value:.4f}"


def format_markdown_summary(summaries: list[dict]) -> str:
    """Format summaries as a markdown table."""
    lines = [
        "# TradingAgents Signal Evaluation",
        "",
        "| name | rows | actions | avg_confidence | avg_risk | avg_score | avg_return | avg_benchmark | avg_alpha | decision_alpha | directional_hit | cumulative_return | max_drawdown | win_rate |",
        "|:---|---:|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summaries:
        actions = ", ".join(f"{k}:{v}" for k, v in item["action_counts"].items())
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item["name"]),
                    str(item["rows"]),
                    actions,
                    _num(item["avg_confidence"]),
                    _num(item["avg_risk_score"]),
                    _num(item["avg_score"]),
                    _pct(item["avg_forward_return"]),
                    _pct(item["avg_benchmark_return"]),
                    _pct(item["avg_alpha"]),
                    _pct(item["avg_decision_alpha"]),
                    _pct(item["directional_hit_rate"]),
                    _pct(item["cumulative_return"]),
                    _pct(item["max_drawdown"]),
                    _pct(item["win_rate"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate TradingAgents signal CSV files.")
    parser.add_argument("--signals", nargs="+", required=True, help="One or more signal CSV paths")
    parser.add_argument("--holding-days", type=int, default=1, help="Forward holding days for evaluation")
    parser.add_argument("--benchmark", default="SH000905", help="A-share benchmark, default SH000905")
    parser.add_argument("--hold-alpha-band", type=float, default=0.01, help="Abs alpha band treated as correct for Hold")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = bundle_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    for signal_path_str in args.signals:
        signal_path = Path(signal_path_str)
        if not signal_path.is_absolute():
            signal_path = bundle_root / signal_path

        signals = pd.read_csv(signal_path)
        evaluated = attach_forward_returns(
            signals,
            holding_days=args.holding_days,
            benchmark=args.benchmark,
            hold_alpha_band=args.hold_alpha_band,
        )
        name = signal_path.stem
        evaluated_path = output_dir / f"{name}_evaluated.csv"
        evaluated.to_csv(evaluated_path, index=False, encoding="utf-8")
        summaries.append(build_summary(evaluated, name=name))
        print(f"saved detail: {evaluated_path}")

    summary_text = format_markdown_summary(summaries)
    summary_path = output_dir / "signal_evaluation_summary.md"
    summary_path.write_text(summary_text, encoding="utf-8")
    print(f"saved summary: {summary_path}")
    print(summary_text)


if __name__ == "__main__":
    main()
