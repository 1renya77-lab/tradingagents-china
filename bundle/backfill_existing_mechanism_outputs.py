#!/usr/bin/env python3
"""Backfill mechanism-study artifacts from existing TradingAgents runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from build_feedback_windows import build_feedback_windows
from build_mechanism_attribution import write_mechanism_attribution
from compare_baselines import infer_from_signal_filename


PROJECT_DIR = Path(__file__).resolve().parent


def parse_run_spec(raw: str) -> tuple[str, str]:
    if ":" in raw:
        name, mode = raw.split(":", 1)
        return name.strip(), mode.strip()
    return raw.strip(), "multi_agent_full_debate"


def parse_mapping(items: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Expected KEY=VALUE mapping, got: {item}")
        key, value = item.split("=", 1)
        mapping[key.strip()] = value.strip()
    return mapping


def find_single(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No file matching {pattern} in {directory}")
    return matches[-1]


def load_signal_metadata(signal_path: Path) -> dict[str, str]:
    ticker, start, end = infer_from_signal_filename(signal_path)
    if not ticker or not start or not end:
        raise ValueError(f"Could not infer ticker/start/end from signal file: {signal_path}")
    return {"ticker": ticker, "start": start, "end": end}


def extract_report_excerpt(report_path: Path, limit: int = 700) -> str:
    if not report_path.exists():
        return "报告缺失"
    text = report_path.read_text(encoding="utf-8", errors="ignore").strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def load_audit_decision(audit_path: Path) -> str:
    if not audit_path.exists():
        return "审计缺失"
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    return str(payload.get("final_decision", {}).get("llm_output", "")).strip()


def build_case_studies(run_dir: Path, output_path: Path) -> Path:
    feedback_path = run_dir / "feedback_windows.csv"
    if not feedback_path.exists():
        raise FileNotFoundError(f"feedback_windows.csv not found in {run_dir}")

    df = pd.read_csv(feedback_path)
    if df.empty:
        output_path.write_text("# Case Studies\n\n无可用窗口。\n", encoding="utf-8")
        return output_path

    sections: list[str] = ["# Case Studies", ""]
    case_order = [
        ("success_attack", "成功进攻"),
        ("success_defense", "成功避险"),
        ("missed_upside", "踏空案例"),
        ("wrong_exposure", "错误暴露"),
    ]

    for case_key, case_title in case_order:
        subset = df[df["case_type"] == case_key].copy()
        if subset.empty:
            continue
        if case_key in {"missed_upside", "wrong_exposure"}:
            sort_col = "missed_upside" if "missed_upside" in subset.columns else "wrong_exposure"
            subset = subset.sort_values(sort_col, ascending=False)
        else:
            subset = subset.sort_values("decision_quality_score", ascending=False)
        row = subset.iloc[0]
        signal_date = str(row["signal_date"])
        ticker = str(row["ticker"])
        report_path = run_dir / "reports" / f"report_{ticker}_{signal_date}.md"
        audit_path = run_dir / "audit_reports" / f"audit_{ticker}_{signal_date}.json"
        sections.extend(
            [
                f"## {case_title}",
                "",
                f"- 信号日: {signal_date}",
                f"- 目标仓位: {float(row['target_position']):.2%}",
                f"- 个股窗口收益: {float(row['stock_return']):.2%}",
                f"- 策略窗口收益: {float(row['agent_return']):.2%}",
                f"- 基准窗口收益: {float(row['benchmark_return']):.2%}",
                f"- 决策质量分: {float(row['decision_quality_score']):.3f}",
                "",
                "### 最终决策摘要",
                "",
                load_audit_decision(audit_path) or "无",
                "",
                "### 报告节选",
                "",
                extract_report_excerpt(report_path),
                "",
            ]
        )

    if len(sections) == 2:
        sections.extend(["暂无可归类案例。", ""])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(sections), encoding="utf-8")
    return output_path


def build_summary_markdown(summary_df: pd.DataFrame) -> str:
    lines = [
        "# TradingAgents A-share Mechanism Study Summary",
        "",
        "| run_name | mode | ticker | period | agent_return | buy_hold_return | excess_vs_buy_hold | agent_sharpe | buy_hold_sharpe | mean_quality | missed_upside_cases | wrong_exposure_cases |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in summary_df.iterrows():
        lines.append(
            "| {run_name} | {experiment_mode} | {ticker} | {start} -> {end} | {agent_return:.2%} | {buy_hold_return:.2%} | {gap:.2%} | {agent_sharpe:.2f} | {buy_hold_sharpe:.2f} | {mean_quality:.3f} | {missed_upside_cases} | {wrong_exposure_cases} |".format(
                run_name=row["run_name"],
                experiment_mode=row["experiment_mode"],
                ticker=row["ticker"],
                start=row["start"],
                end=row["end"],
                agent_return=float(row["agent_total_return"]),
                buy_hold_return=float(row["buy_hold_total_return"]),
                gap=float(row["agent_total_return"]) - float(row["buy_hold_total_return"]),
                agent_sharpe=float(row["agent_sharpe"]),
                buy_hold_sharpe=float(row["buy_hold_sharpe"]),
                mean_quality=float(row["mean_decision_quality"]),
                missed_upside_cases=int(row["missed_upside_cases"]),
                wrong_exposure_cases=int(row["wrong_exposure_cases"]),
            )
        )
    return "\n".join(lines) + "\n"


def backfill_one_run(
    run_name: str,
    experiment_mode: str,
    provider_uri: str,
    comparison_dir: Path,
) -> dict[str, Any]:
    run_dir = PROJECT_DIR / "outputs" / "runs" / run_name
    signal_path = find_single(run_dir / "signals", "*.csv")
    meta = load_signal_metadata(signal_path)
    report_path = find_single(comparison_dir / "backtests" / "agent", "qlib_signal_backtest_report_*.csv")
    comparison_csv = find_single(comparison_dir, "comparison_*.csv")

    feedback_path = run_dir / "feedback_windows.csv"
    attribution_path = run_dir / "mechanism_attribution.csv"
    case_studies_path = run_dir / "case_studies.md"

    build_feedback_windows(
        signals_path=signal_path,
        report_path=report_path,
        provider_uri=str((PROJECT_DIR / provider_uri).resolve()) if not Path(provider_uri).is_absolute() else provider_uri,
        ticker=meta["ticker"],
        start=meta["start"],
        end=meta["end"],
        output_path=feedback_path,
        run_name=run_name,
        experiment_mode=experiment_mode,
    )
    write_mechanism_attribution(run_dir, attribution_path, experiment_mode=experiment_mode)
    build_case_studies(run_dir, case_studies_path)

    feedback_df = pd.read_csv(feedback_path)
    comparison_df = pd.read_csv(comparison_csv)
    agent_row = comparison_df[comparison_df["strategy"] == "agent"].iloc[0]
    hold_row = comparison_df[comparison_df["strategy"] == "buy_hold_100"].iloc[0]

    return {
        "run_name": run_name,
        "experiment_mode": experiment_mode,
        "ticker": meta["ticker"],
        "start": meta["start"],
        "end": meta["end"],
        "provider_uri": provider_uri,
        "comparison_dir": str(comparison_dir),
        "signal_path": str(signal_path),
        "feedback_path": str(feedback_path),
        "attribution_path": str(attribution_path),
        "case_studies_path": str(case_studies_path),
        "agent_total_return": float(agent_row["total_return"]),
        "buy_hold_total_return": float(hold_row["total_return"]),
        "agent_sharpe": float(agent_row["sharpe"]),
        "buy_hold_sharpe": float(hold_row["sharpe"]),
        "mean_decision_quality": float(feedback_df["decision_quality_score"].mean()) if not feedback_df.empty else 0.0,
        "missed_upside_cases": int((feedback_df["case_type"] == "missed_upside").sum()) if not feedback_df.empty else 0,
        "wrong_exposure_cases": int((feedback_df["case_type"] == "wrong_exposure").sum()) if not feedback_df.empty else 0,
        "success_attack_cases": int((feedback_df["case_type"] == "success_attack").sum()) if not feedback_df.empty else 0,
        "success_defense_cases": int((feedback_df["case_type"] == "success_defense").sum()) if not feedback_df.empty else 0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill mechanism outputs from existing runs without rerunning LLMs.")
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        help="Run spec: RUN_NAME or RUN_NAME:EXPERIMENT_MODE",
    )
    parser.add_argument(
        "--provider-uri-map",
        action="append",
        default=[],
        help="Ticker-to-provider mapping, e.g. 300308=data/qlib_cn_300308",
    )
    parser.add_argument(
        "--comparison-dir-map",
        action="append",
        default=[],
        help="Run-to-comparison-dir mapping, e.g. 300308_weekly_2026q2=outputs/baseline_comparisons/300308_weekly_2026q2",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/mechanism_study_existing",
        help="Directory for global summary outputs",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    provider_map = parse_mapping(args.provider_uri_map)
    comparison_dir_map = parse_mapping(args.comparison_dir_map)

    rows = []
    for raw_run in args.run:
        run_name, experiment_mode = parse_run_spec(raw_run)
        signal_path = find_single(PROJECT_DIR / "outputs" / "runs" / run_name / "signals", "*.csv")
        meta = load_signal_metadata(signal_path)
        provider_uri = provider_map.get(meta["ticker"])
        if not provider_uri:
            raise ValueError(f"Missing provider uri for ticker {meta['ticker']}. Use --provider-uri-map.")
        comparison_dir = comparison_dir_map.get(
            run_name,
            f"outputs/baseline_comparisons/{run_name}",
        )
        rows.append(
            backfill_one_run(
                run_name=run_name,
                experiment_mode=experiment_mode,
                provider_uri=provider_uri,
                comparison_dir=(PROJECT_DIR / comparison_dir).resolve()
                if not Path(comparison_dir).is_absolute()
                else Path(comparison_dir),
            )
        )

    summary_df = pd.DataFrame(rows).sort_values(["ticker", "run_name"])
    output_dir = (PROJECT_DIR / args.output_dir).resolve() if not Path(args.output_dir).is_absolute() else Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_csv = output_dir / "summary.csv"
    summary_md = output_dir / "summary.md"
    summary_df.to_csv(summary_csv, index=False, encoding="utf-8")
    summary_md.write_text(build_summary_markdown(summary_df), encoding="utf-8")

    print(f"summary_csv: {summary_csv}")
    print(f"summary_md : {summary_md}")
    print(f"runs       : {len(summary_df)}")


if __name__ == "__main__":
    main()
