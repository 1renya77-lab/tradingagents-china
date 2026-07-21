"""Run reproducible TradingAgents experiments from a JSON config."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

bundle_root = Path(__file__).parent

from collect_daily_signals import build_signal_filename, collect_daily_signals  # noqa: E402
from evaluate_signals import attach_forward_returns, build_summary, format_markdown_summary  # noqa: E402
from tradingagents.utils.artifacts import resolve_artifact_dir  # noqa: E402


DEFAULT_ANALYSTS = ["market", "news", "social", "fundamentals"]


def normalize_experiment_config(raw: dict) -> dict:
    """Apply sensible defaults to an experiment config."""
    cfg = dict(raw)
    cfg.setdefault("provider", "deepseek")
    cfg.setdefault("model", "deepseek-v4-flash")
    cfg.setdefault("quick_model", cfg["model"])
    cfg.setdefault("deep_model", cfg["model"])
    cfg.setdefault("analysts", list(DEFAULT_ANALYSTS))
    cfg.setdefault("max_debate_rounds", 1)
    cfg.setdefault("frequency", "daily")
    cfg.setdefault("benchmark", "SH000905")
    cfg.setdefault("holding_days", 1)
    cfg.setdefault("evaluate", True)
    cfg.setdefault("stocks", [])
    if not cfg.get("run_name"):
        raise ValueError("Experiment config must include run_name")
    if not cfg["stocks"]:
        raise ValueError("Experiment config must include at least one stock in stocks[]")
    return cfg


def build_signal_output_path(
    bundle_root: Path,
    run_name: str,
    ticker: str,
    start_date: str,
    end_date: str,
    frequency: str = "daily",
) -> Path:
    """Build the default signal output path for one experiment stock item."""
    signal_dir = resolve_artifact_dir(bundle_root, "signals", run_name=run_name)
    return signal_dir / build_signal_filename(ticker, start_date, end_date, frequency)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a TradingAgents experiment from JSON config.")
    parser.add_argument("--config", required=True, help="Path to experiment JSON config")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = bundle_root / config_path

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    cfg = normalize_experiment_config(raw)

    run_name = cfg["run_name"]
    manifest_dir = resolve_artifact_dir(bundle_root, "manifests", run_name=run_name)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_name": run_name,
        "provider": cfg["provider"],
        "quick_model": cfg["quick_model"],
        "deep_model": cfg["deep_model"],
        "analysts": cfg["analysts"],
        "max_debate_rounds": cfg["max_debate_rounds"],
        "frequency": cfg["frequency"],
        "benchmark": cfg["benchmark"],
        "holding_days": cfg["holding_days"],
        "stocks": [],
    }

    summaries = []
    for stock in cfg["stocks"]:
        ticker = stock["ticker"]
        start_date = stock["start"]
        end_date = stock["end"]
        signal_output = build_signal_output_path(
            bundle_root=bundle_root,
            run_name=run_name,
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            frequency=cfg["frequency"],
        )

        collect_daily_signals(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            frequency=cfg["frequency"],
            selected_analysts=cfg["analysts"],
            llm_provider=cfg["provider"],
            model=cfg["model"],
            quick_model=cfg["quick_model"],
            deep_model=cfg["deep_model"],
            max_debate_rounds=cfg["max_debate_rounds"],
            output_file=str(signal_output),
            run_name=run_name,
        )

        stock_record = {
            "ticker": ticker,
            "start": start_date,
            "end": end_date,
            "signal_csv": str(signal_output),
        }

        if cfg.get("evaluate", True):
            evaluated = attach_forward_returns(
                signals=pd.read_csv(signal_output),
                holding_days=cfg["holding_days"],
                benchmark=cfg["benchmark"],
            )
            eval_dir = resolve_artifact_dir(bundle_root, "evaluations", run_name=run_name)
            eval_dir.mkdir(parents=True, exist_ok=True)
            evaluated_path = eval_dir / f"{signal_output.stem}_evaluated.csv"
            evaluated.to_csv(evaluated_path, index=False, encoding="utf-8")
            summary = build_summary(evaluated, name=signal_output.stem)
            summaries.append(summary)
            stock_record["evaluation_csv"] = str(evaluated_path)

        manifest["stocks"].append(stock_record)

    manifest_path = manifest_dir / "experiment_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved manifest: {manifest_path}")

    if summaries:
        summary_dir = resolve_artifact_dir(bundle_root, "evaluations", run_name=run_name)
        summary_dir.mkdir(parents=True, exist_ok=True)
        summary_path = summary_dir / "experiment_summary.md"
        summary_path.write_text(format_markdown_summary(summaries), encoding="utf-8")
        print(f"saved summary: {summary_path}")


if __name__ == "__main__":
    main()
