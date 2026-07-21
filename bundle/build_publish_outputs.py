#!/usr/bin/env python3
"""Build a compact human-facing publish layer from verbose experiment outputs."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"


def _copy(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _first_file(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern))
    return files[0] if files else None


def _read_signals_summary(signals_path: Path | None) -> list[str]:
    if signals_path is None or not signals_path.exists():
        return ["- signals: not found"]
    df = pd.read_csv(signals_path)
    lines = [
        f"- signals: `{signals_path.name}`",
        f"- rows: `{len(df)}`",
    ]
    for col in ["ticker", "experiment_mode", "status"]:
        if col in df.columns:
            values = [str(v) for v in df[col].dropna().astype(str).unique()[:5]]
            if values:
                lines.append(f"- {col}: `{', '.join(values)}`")
    if "target_position" in df.columns and not df.empty:
        positions = pd.to_numeric(df["target_position"], errors="coerce").dropna()
        if not positions.empty:
            lines.append(
                "- target_position: "
                f"min `{positions.min() * 100:.1f}%`, "
                f"mean `{positions.mean() * 100:.1f}%`, "
                f"max `{positions.max() * 100:.1f}%`"
            )
    return lines


def _combine_reports(reports_dir: Path, output_path: Path) -> int:
    reports = sorted(reports_dir.glob("report_*.md")) if reports_dir.exists() else []
    if not reports:
        return 0

    lines = [
        "# Combined Signal Reports",
        "",
        "This file merges per-signal Markdown reports into one readable artifact.",
        "",
        "## Table of Contents",
        "",
    ]
    for report in reports:
        title = report.stem.replace("report_", "")
        anchor = title.lower().replace("_", "-").replace(".", "")
        lines.append(f"- [{title}](#{anchor})")
    lines.append("")

    for report in reports:
        content = report.read_text(encoding="utf-8").strip()
        lines.extend(["---", "", content, ""])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return len(reports)


def _build_run_publish(run_dir: Path, publish_dir: Path) -> dict:
    run_name = run_dir.name
    target_dir = publish_dir / run_name
    target_dir.mkdir(parents=True, exist_ok=True)

    signals_path = _first_file(run_dir / "signals", "*_position.csv") or _first_file(run_dir / "signals", "*.csv")
    copied: list[str] = []
    if signals_path and _copy(signals_path, target_dir / "signals.csv"):
        copied.append("signals.csv")

    manifest_path = _first_file(run_dir / "manifests", "*.json")
    if manifest_path and _copy(manifest_path, target_dir / "manifest.json"):
        copied.append("manifest.json")

    preflight_md = run_dir / "data_preflight" / "preflight_data_quality.md"
    if _copy(preflight_md, target_dir / "data_quality.md"):
        copied.append("data_quality.md")

    reports_count = _combine_reports(run_dir / "reports", target_dir / "reports_combined.md")
    if reports_count:
        copied.append("reports_combined.md")

    comparison_dir = OUTPUTS / "baseline_comparisons" / run_name
    comparison_md = _first_file(comparison_dir, "comparison_*.md")
    if comparison_md and _copy(comparison_md, target_dir / "comparison_vs_buy_hold.md"):
        copied.append("comparison_vs_buy_hold.md")

    nav_png = _first_file(comparison_dir / "figures", "*.png")
    if nav_png and _copy(nav_png, target_dir / nav_png.name):
        copied.append(nav_png.name)

    backtest_dir = OUTPUTS / "backtests" / run_name
    metrics_csv = _first_file(backtest_dir, "*metrics*.csv")
    if metrics_csv and _copy(metrics_csv, target_dir / "backtest_metrics.csv"):
        copied.append("backtest_metrics.csv")

    trades_csv = _first_file(backtest_dir, "*trades*.csv")
    if trades_csv and _copy(trades_csv, target_dir / "backtest_trades.csv"):
        copied.append("backtest_trades.csv")

    summary_lines = [
        f"# {run_name}",
        "",
        "## What To Read",
        "",
        "- `signals.csv`: final executable target-position signals.",
        "- `comparison_vs_buy_hold.md`: agent strategy vs one-time 100% buy-and-hold, when available.",
        "- `backtest_metrics.csv`: Qlib metric table, when available.",
        "- `reports_combined.md`: merged per-signal agent reports.",
        "- `data_quality.md`: preflight data quality summary.",
        "",
        "## Signal Summary",
        "",
        *_read_signals_summary(signals_path),
        "",
        "## Files In This Publish Folder",
        "",
        *[f"- `{name}`" for name in sorted(copied)],
        "",
        "## Full Engineering Artifacts",
        "",
        f"- Source run directory: `{run_dir.relative_to(ROOT)}`",
    ]
    (target_dir / "summary.md").write_text("\n".join(summary_lines).strip() + "\n", encoding="utf-8")
    copied.append("summary.md")
    return {"run_name": run_name, "publish_dir": target_dir, "files": sorted(set(copied)), "reports": reports_count}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build compact publish artifacts from outputs/runs.")
    parser.add_argument("--run-name", action="append", default=[], help="Run name to publish. Can be repeated.")
    parser.add_argument("--output-dir", default=str(OUTPUTS / "publish"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runs_root = OUTPUTS / "runs"
    publish_dir = Path(args.output_dir).expanduser().resolve()
    run_dirs = [runs_root / name for name in args.run_name] if args.run_name else sorted(p for p in runs_root.iterdir() if p.is_dir())
    run_dirs = [p for p in run_dirs if p.exists()]

    results = [_build_run_publish(run_dir, publish_dir) for run_dir in run_dirs]
    index_lines = [
        "# Publish Outputs",
        "",
        "Compact, human-facing artifacts generated from verbose experiment outputs.",
        "",
        "| run | files | reports | path |",
        "| --- | ---: | ---: | --- |",
    ]
    for item in results:
        rel = item["publish_dir"].relative_to(ROOT)
        index_lines.append(f"| {item['run_name']} | {len(item['files'])} | {item['reports']} | `{rel}` |")
    publish_dir.mkdir(parents=True, exist_ok=True)
    (publish_dir / "README.md").write_text("\n".join(index_lines).strip() + "\n", encoding="utf-8")

    print(f"published runs: {len(results)}")
    print(f"publish_dir   : {publish_dir}")


if __name__ == "__main__":
    main()
