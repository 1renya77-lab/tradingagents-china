from __future__ import annotations

import html
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "outputs" / "runs"
BASELINE_DIR = ROOT / "outputs" / "baseline_comparisons"
AUDIT_BACKTEST_DIR = ROOT / "outputs" / "audits" / "position_alignment_backtests"
OUTPUT_DIR = ROOT / "outputs" / "dashboard"


@dataclass
class RunArtifacts:
    run: str
    signal_path: Path | None
    report_path: Path | None
    positions_path: Path | None
    metrics_path: Path | None
    comparison_path: Path | None
    data_source_json_path: Path | None
    data_source_md_path: Path | None


def rel(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def link(path: Path | None, label: str | None = None) -> str:
    if path is None:
        return ""
    href = html.escape(rel(path))
    text = html.escape(label or path.name)
    return f'<a href="../../{href}" target="_blank">{text}</a>'


def newest(paths: list[Path]) -> Path | None:
    if not paths:
        return None
    return max(paths, key=lambda p: p.stat().st_mtime)


def choose_signal(run_dir: Path) -> Path | None:
    signal_dir = run_dir / "signals"
    if not signal_dir.exists():
        return None
    files = list(signal_dir.glob("*weekly_position*.csv")) or list(signal_dir.glob("signals_*.csv"))
    if not files:
        return None
    corrected = [p for p in files if "audit_corrected" in p.name]
    if corrected:
        return newest(corrected)
    candidates = [p for p in files if "snapshot" not in p.name]
    return newest(candidates or files)


def infer_ticker(path: Path | None) -> str:
    if path is None:
        return ""
    match = re.search(r"signals_([^_]+)_", path.name)
    if match:
        return match.group(1)
    match = re.search(r"(?:report|audit|trajectory)_([^_]+)_", path.name)
    return match.group(1) if match else ""


def read_csv(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def collect_artifacts(run_dir: Path) -> RunArtifacts:
    run = run_dir.name
    signal_path = choose_signal(run_dir)
    ticker = infer_ticker(signal_path)

    audit_dir = AUDIT_BACKTEST_DIR / run / "backtest"
    baseline_agent_dir = BASELINE_DIR / run / "backtests" / "agent"

    report_candidates = []
    positions_candidates = []
    metrics_candidates = []
    for source_dir in [audit_dir, baseline_agent_dir]:
        if source_dir.exists():
            report_candidates.extend(source_dir.glob(f"qlib_signal_backtest_report_{ticker}_*.csv"))
            positions_candidates.extend(source_dir.glob(f"qlib_signal_backtest_positions_{ticker}_*.csv"))
            metrics_candidates.extend(source_dir.glob(f"qlib_signal_backtest_metrics_{ticker}_*.csv"))

    comparison_candidates = list((BASELINE_DIR / run).glob("comparison_*.csv"))
    data_source_dir = run_dir / "data_source_audit"
    return RunArtifacts(
        run=run,
        signal_path=signal_path,
        report_path=newest(report_candidates),
        positions_path=newest(positions_candidates),
        metrics_path=newest(metrics_candidates),
        comparison_path=newest(comparison_candidates),
        data_source_json_path=data_source_dir / "data_source_audit.json"
        if (data_source_dir / "data_source_audit.json").exists()
        else None,
        data_source_md_path=data_source_dir / "data_source_audit.md"
        if (data_source_dir / "data_source_audit.md").exists()
        else None,
    )


def file_counts(run_dir: Path) -> dict[str, int]:
    return {
        "reports": len(list((run_dir / "reports").glob("*.md"))),
        "trajectories": len(list((run_dir / "trajectories").glob("*.json"))),
        "audit_reports": len(list((run_dir / "audit_reports").glob("*.json"))),
        "signals": len(list((run_dir / "signals").glob("*.csv"))),
    }


def artifact_time_span(run_dir: Path) -> tuple[str, str, float | None]:
    files = [p for p in run_dir.rglob("*") if p.is_file() and p.name != ".DS_Store"]
    if not files:
        return "", "", None
    mtimes = [p.stat().st_mtime for p in files]
    start = pd.to_datetime(min(mtimes), unit="s").strftime("%Y-%m-%d %H:%M:%S")
    end = pd.to_datetime(max(mtimes), unit="s").strftime("%Y-%m-%d %H:%M:%S")
    return start, end, (max(mtimes) - min(mtimes)) / 60.0


def load_market_prices(ticker: str) -> pd.DataFrame:
    path = ROOT / "data" / "prefetch" / "market" / f"{ticker}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    date_col = "Date" if "Date" in df.columns else "date"
    close_col = "Close" if "Close" in df.columns else "close"
    if date_col not in df.columns or close_col not in df.columns:
        return pd.DataFrame()
    out = df[[date_col, close_col]].copy()
    out.columns = ["date", "close"]
    out["date"] = pd.to_datetime(out["date"])
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    return out.dropna().sort_values("date")


def price_on_or_after(prices: pd.DataFrame, date: pd.Timestamp) -> float | None:
    if prices.empty:
        return None
    rows = prices[prices["date"] >= date]
    if rows.empty:
        return None
    return float(rows.iloc[0]["close"])


def load_position_prices(path: Path | None, ticker: str) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "datetime" not in df.columns:
        return pd.DataFrame()
    ticker = ticker.upper()
    instrument = ticker if ticker.startswith(("SH", "SZ")) else ("SH" + ticker if ticker.startswith(("5", "6", "9")) else "SZ" + ticker)
    preferred = f"{instrument}.price"
    price_cols = [preferred] if preferred in df.columns else [c for c in df.columns if c.endswith(".price")]
    if not price_cols:
        return pd.DataFrame()
    out = df[["datetime", price_cols[0]]].copy()
    out.columns = ["date", "close"]
    out["date"] = pd.to_datetime(out["date"])
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    return out.dropna().sort_values("date")


def account_on_or_after(report: pd.DataFrame, date: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    rows = report[report["datetime"] >= date]
    if rows.empty:
        return None
    row = rows.iloc[0]
    return pd.Timestamp(row["datetime"]), float(row["account"])


def first_after(report: pd.DataFrame, date: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    rows = report[report["datetime"] > date]
    if rows.empty:
        return None
    row = rows.iloc[0]
    return pd.Timestamp(row["datetime"]), float(row["account"])


def extract_reason(row: pd.Series) -> str:
    for col in ["reasoning", "reasoning_short", "error_message"]:
        value = row.get(col)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def build_case_rows(artifacts: RunArtifacts) -> list[dict[str, Any]]:
    signals = read_csv(artifacts.signal_path)
    report = read_csv(artifacts.report_path)
    if signals.empty or report.empty or "target_position" not in signals.columns:
        return []

    ticker = infer_ticker(artifacts.signal_path)
    prices = load_market_prices(ticker)
    if prices.empty:
        prices = load_position_prices(artifacts.positions_path, ticker)
    signals = signals.copy()
    if "status" in signals.columns:
        signals = signals[signals["status"].fillna("ok").astype(str).str.lower().eq("ok")]
    signals["date"] = pd.to_datetime(signals["date"])
    signals["target_position"] = pd.to_numeric(signals["target_position"], errors="coerce")
    signals = signals.dropna(subset=["date", "target_position"]).sort_values("date").reset_index(drop=True)

    report = report.copy()
    report["datetime"] = pd.to_datetime(report["datetime"])
    report["account"] = pd.to_numeric(report["account"], errors="coerce")
    report = report.dropna(subset=["datetime", "account"]).sort_values("datetime")

    rows: list[dict[str, Any]] = []
    for i, row in signals.iterrows():
        signal_date = pd.Timestamp(row["date"])
        entry = first_after(report, signal_date)
        if entry is None:
            continue
        next_signal_date = pd.Timestamp(signals.iloc[i + 1]["date"]) if i + 1 < len(signals) else pd.Timestamp(report.iloc[-1]["datetime"])
        exit_point = account_on_or_after(report, next_signal_date)
        if exit_point is None:
            continue
        execution_date, account_start = entry
        measure_to, account_end = exit_point
        account_return = account_end / account_start - 1 if account_start else math.nan

        entry_price = price_on_or_after(prices, execution_date)
        exit_price = price_on_or_after(prices, measure_to)
        stock_return = (
            exit_price / entry_price - 1
            if entry_price not in (None, 0) and exit_price is not None
            else math.nan
        )
        target_position = float(row["target_position"])
        missed_upside = max(stock_return, 0.0) * max(1.0 - target_position, 0.0) if not math.isnan(stock_return) else math.nan
        avoided_loss = max(-stock_return, 0.0) * max(1.0 - target_position, 0.0) if not math.isnan(stock_return) else math.nan
        run_dir = RUNS_DIR / artifacts.run
        date_text = signal_date.strftime("%Y-%m-%d")
        report_md = newest(list((run_dir / "reports").glob(f"report_*_{date_text}.md")))
        trajectory = newest(list((run_dir / "trajectories").glob(f"trajectory_*_{date_text}.json")))
        audit_json = newest(list((run_dir / "audit_reports").glob(f"audit_*_{date_text}.json")))
        rows.append(
            {
                "run": artifacts.run,
                "ticker": ticker,
                "signal_date": date_text,
                "execution_date": execution_date.strftime("%Y-%m-%d"),
                "measure_to": measure_to.strftime("%Y-%m-%d"),
                "action": row.get("action", ""),
                "target_position": target_position,
                "account_return": account_return,
                "stock_return": stock_return,
                "missed_upside_proxy": missed_upside,
                "avoided_loss_proxy": avoided_loss,
                "reasoning": extract_reason(row),
                "signal_file": rel(artifacts.signal_path),
                "report_file": rel(report_md),
                "trajectory_file": rel(trajectory),
                "audit_file": rel(audit_json),
            }
        )
    return rows


def pct(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
        return f"{float(value) * 100:.2f}%"
    except Exception:
        return ""


def num(value: Any, digits: int = 2) -> str:
    try:
        if pd.isna(value):
            return ""
        return f"{float(value):.{digits}f}"
    except Exception:
        return ""


def summarize_runs(run_dirs: list[Path], artifacts_by_run: dict[str, RunArtifacts]) -> pd.DataFrame:
    rows = []
    for run_dir in run_dirs:
        artifacts = artifacts_by_run[run_dir.name]
        counts = file_counts(run_dir)
        started, ended, span_min = artifact_time_span(run_dir)
        signals = read_csv(artifacts.signal_path)
        metrics = read_csv(artifacts.metrics_path)
        comparison = read_csv(artifacts.comparison_path)
        data_source = read_json(artifacts.data_source_json_path)
        ticker = infer_ticker(artifacts.signal_path)
        total_return = sharpe = max_drawdown = math.nan
        buy_hold_return = math.nan
        if not metrics.empty:
            total_return = metrics.iloc[0].get("total_return", math.nan)
            sharpe = metrics.iloc[0].get("sharpe", math.nan)
            max_drawdown = metrics.iloc[0].get("max_drawdown", math.nan)
        if not comparison.empty and "strategy" in comparison.columns:
            bh = comparison[comparison["strategy"].astype(str).eq("buy_hold_100")]
            if not bh.empty:
                buy_hold_return = bh.iloc[0].get("total_return", math.nan)
        rows.append(
            {
                "run": run_dir.name,
                "ticker": ticker,
                "signal_rows": len(signals) if not signals.empty else 0,
                "ok_rows": int(signals["status"].fillna("ok").astype(str).str.lower().eq("ok").sum()) if "status" in signals.columns else len(signals),
                "reports": counts["reports"],
                "trajectories": counts["trajectories"],
                "audit_reports": counts["audit_reports"],
                "artifact_start": started,
                "artifact_end": ended,
                "artifact_span_min": span_min,
                "agent_return": total_return,
                "buy_hold_return": buy_hold_return,
                "excess_vs_buy_hold": total_return - buy_hold_return if not pd.isna(total_return) and not pd.isna(buy_hold_return) else math.nan,
                "sharpe": sharpe,
                "max_drawdown": max_drawdown,
                "data_source_files_checked": data_source.get("files_checked", math.nan),
                "data_source_structured_records": data_source.get("structured_records", math.nan),
                "data_source_inferred_records": data_source.get("inferred_records", math.nan),
                "data_source_unstructured_records": data_source.get("unstructured_records", math.nan),
                "signal_file": rel(artifacts.signal_path),
                "report_csv": rel(artifacts.report_path),
                "comparison_file": rel(artifacts.comparison_path),
                "data_source_audit_file": rel(artifacts.data_source_md_path),
            }
        )
    return pd.DataFrame(rows)


def make_low_position_stats(cases: pd.DataFrame) -> pd.DataFrame:
    if cases.empty:
        return pd.DataFrame()
    low = cases[cases["target_position"] <= 0.2].copy()
    if low.empty:
        return pd.DataFrame()
    grouped = []
    for run, df in low.groupby("run"):
        valid = df.dropna(subset=["stock_return"])
        missed = valid[valid["stock_return"] > 0]
        avoided = valid[valid["stock_return"] < 0]
        missed_sum = missed["missed_upside_proxy"].sum()
        avoided_sum = avoided["avoided_loss_proxy"].sum()
        grouped.append(
            {
                "run": run,
                "low_position_cases": len(df),
                "with_stock_return": len(valid),
                "missed_rally_cases": len(missed),
                "avoided_loss_cases": len(avoided),
                "missed_upside_proxy_sum": missed_sum,
                "avoided_loss_proxy_sum": avoided_sum,
                "avoid_to_miss_ratio": avoided_sum / missed_sum if missed_sum > 0 else math.nan,
                "avg_next_stock_return": valid["stock_return"].mean() if len(valid) else math.nan,
            }
        )
    return pd.DataFrame(grouped)


def card(title: str, value: str, note: str = "") -> str:
    return f"""
    <div class="card">
      <div class="card-title">{html.escape(title)}</div>
      <div class="card-value">{html.escape(value)}</div>
      <div class="card-note">{html.escape(note)}</div>
    </div>
    """


def table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "\n".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_dashboard(run_summary: pd.DataFrame, cases: pd.DataFrame, low_stats: pd.DataFrame) -> str:
    total_runs = len(run_summary)
    total_reports = int(run_summary["reports"].sum()) if not run_summary.empty else 0
    total_cases = len(cases)
    low_cases = int((cases["target_position"] <= 0.2).sum()) if not cases.empty else 0
    positive_runs = int((run_summary["agent_return"] > 0).sum()) if "agent_return" in run_summary else 0
    mean_excess = run_summary["excess_vs_buy_hold"].dropna().mean() if "excess_vs_buy_hold" in run_summary else math.nan

    valid_runs = run_summary.dropna(subset=["agent_return"]).copy() if "agent_return" in run_summary else pd.DataFrame()
    best_run = valid_runs.sort_values("agent_return", ascending=False).head(1)
    worst_run = valid_runs.sort_values("agent_return", ascending=True).head(1)

    def run_chip(df: pd.DataFrame, label: str) -> str:
        if df.empty:
            return ""
        row = df.iloc[0]
        tone = "good" if row["agent_return"] >= 0 else "bad"
        return (
            f'<div class="run-chip {tone}">'
            f'<span>{html.escape(label)}</span>'
            f'<strong>{html.escape(str(row["run"]))}</strong>'
            f'<em>{pct(row["agent_return"])} / Sharpe {num(row.get("sharpe"))}</em>'
            f'</div>'
        )

    run_rows = []
    for _, r in run_summary.sort_values("run").iterrows():
        run_rows.append(
            [
                html.escape(str(r["run"])),
                html.escape(str(r.get("ticker", ""))),
                str(int(r.get("ok_rows", 0))),
                str(int(r.get("reports", 0))),
                pct(r.get("agent_return")),
                pct(r.get("buy_hold_return")),
                pct(r.get("excess_vs_buy_hold")),
                num(r.get("sharpe")),
                pct(r.get("max_drawdown")),
                str(int(r["data_source_files_checked"])) if not pd.isna(r.get("data_source_files_checked")) else "",
                str(int(r["data_source_structured_records"])) if not pd.isna(r.get("data_source_structured_records")) else "",
                str(int(r["data_source_inferred_records"])) if not pd.isna(r.get("data_source_inferred_records")) else "",
                str(int(r["data_source_unstructured_records"])) if not pd.isna(r.get("data_source_unstructured_records")) else "",
                num(r.get("artifact_span_min"), 1),
                link(ROOT / r["signal_file"], "signal") if r.get("signal_file") else "",
                link(ROOT / r["comparison_file"], "comparison") if r.get("comparison_file") else "",
                link(ROOT / r["data_source_audit_file"], "data-source") if r.get("data_source_audit_file") else "",
            ]
        )

    worst = cases.nsmallest(8, "account_return") if not cases.empty else pd.DataFrame()
    best = cases.nlargest(8, "account_return") if not cases.empty else pd.DataFrame()

    def case_cards(df: pd.DataFrame, tone: str) -> str:
        cards = []
        for _, r in df.head(4).iterrows():
            report_file = ROOT / r["report_file"] if r.get("report_file") else None
            trajectory_file = ROOT / r["trajectory_file"] if r.get("trajectory_file") else None
            audit_file = ROOT / r["audit_file"] if r.get("audit_file") else None
            cards.append(
                f"""
                <article class="case-card {tone}">
                  <div class="case-top">
                    <span>{html.escape(str(r["ticker"]))}</span>
                    <b>{html.escape(str(r["signal_date"]))}</b>
                  </div>
                  <div class="case-return">{pct(r["account_return"])}</div>
                  <div class="case-meta">
                    <span>{html.escape(str(r["action"]))}</span>
                    <span>仓位 {pct(r["target_position"])}</span>
                    <span>标的 {pct(r["stock_return"])}</span>
                  </div>
                  <p>{html.escape(str(r["reasoning"])[:180])}</p>
                  <div class="case-links">
                    {link(report_file, "report")}
                    {link(trajectory_file, "trajectory")}
                    {link(audit_file, "audit")}
                  </div>
                </article>
                """
            )
        return "\n".join(cards)

    def case_rows(df: pd.DataFrame) -> list[list[str]]:
        out = []
        for _, r in df.iterrows():
            report_file = ROOT / r["report_file"] if r.get("report_file") else None
            trajectory_file = ROOT / r["trajectory_file"] if r.get("trajectory_file") else None
            audit_file = ROOT / r["audit_file"] if r.get("audit_file") else None
            out.append(
                [
                    html.escape(str(r["run"])),
                    html.escape(str(r["signal_date"])),
                    html.escape(str(r["action"])),
                    pct(r["target_position"]),
                    pct(r["account_return"]),
                    pct(r["stock_return"]),
                    html.escape(str(r["reasoning"])[:140]),
                    " ".join(x for x in [link(report_file, "report"), link(trajectory_file, "trajectory"), link(audit_file, "audit")] if x),
                ]
            )
        return out

    low_rows = []
    if not low_stats.empty:
        for _, r in low_stats.sort_values("run").iterrows():
            low_rows.append(
                [
                    html.escape(str(r["run"])),
                    str(int(r["low_position_cases"])),
                    str(int(r["missed_rally_cases"])),
                    str(int(r["avoided_loss_cases"])),
                    pct(r["missed_upside_proxy_sum"]),
                    pct(r["avoided_loss_proxy_sum"]),
                    num(r["avoid_to_miss_ratio"]),
                    pct(r["avg_next_stock_return"]),
                ]
            )

    low_summary_cards = []
    if not low_stats.empty:
        for _, r in low_stats.sort_values("avoid_to_miss_ratio", ascending=False, na_position="last").head(4).iterrows():
            low_summary_cards.append(
                f"""
                <div class="position-card">
                  <span>{html.escape(str(r["run"]))}</span>
                  <strong>{num(r["avoid_to_miss_ratio"])}</strong>
                  <em>避险/踏空比</em>
                  <p>低仓 {int(r["low_position_cases"])} 次，踏空 {int(r["missed_rally_cases"])} 次，避险 {int(r["avoided_loss_cases"])} 次。</p>
                </div>
                """
            )

    generated_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TradingAgents A股实验看板</title>
  <style>
    :root {{
      --ink: #101614;
      --muted: #66706c;
      --paper: #f7f1e4;
      --panel: rgba(255, 252, 244, .88);
      --line: rgba(32, 45, 39, .14);
      --red: #a83d33;
      --green: #26725c;
      --blue: #245b82;
      --gold: #b97924;
      --charcoal: #1a231f;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "PingFang SC", "Hiragino Sans GB", "Songti SC", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 8% 12%, rgba(185, 121, 36, .28), transparent 28rem),
        radial-gradient(circle at 88% 0%, rgba(38, 114, 92, .18), transparent 26rem),
        linear-gradient(135deg, #eee0c4 0%, #faf7ee 44%, #e5efe8 100%);
    }}
    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: .34;
      background-image:
        linear-gradient(rgba(16, 22, 20, .045) 1px, transparent 1px),
        linear-gradient(90deg, rgba(16, 22, 20, .045) 1px, transparent 1px);
      background-size: 42px 42px;
      mask-image: linear-gradient(to bottom, black, transparent 80%);
    }}
    header {{
      min-height: 82vh;
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) 420px;
      gap: 34px;
      align-items: center;
      padding: 64px 7vw 44px;
      position: relative;
    }}
    .eyebrow {{ color: var(--gold); letter-spacing: .22em; text-transform: uppercase; font-size: 12px; font-weight: 800; }}
    h1 {{ font-size: clamp(44px, 6.2vw, 92px); line-height: .92; margin: 18px 0; letter-spacing: -0.06em; max-width: 980px; }}
    .lead {{ font-size: clamp(17px, 1.7vw, 22px); line-height: 1.65; color: #4d5a55; max-width: 820px; }}
    .hero-actions {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 28px; }}
    .button {{ display: inline-flex; align-items: center; gap: 8px; padding: 12px 16px; border-radius: 999px; background: var(--charcoal); color: #fff; text-decoration: none; font-weight: 800; }}
    .button.secondary {{ background: rgba(255,255,255,.55); color: var(--ink); border: 1px solid var(--line); }}
    .hero-panel {{
      background: linear-gradient(180deg, rgba(26,35,31,.96), rgba(26,35,31,.86));
      color: #fff;
      border-radius: 34px;
      padding: 26px;
      box-shadow: 0 30px 80px rgba(31, 45, 38, .24);
      border: 1px solid rgba(255,255,255,.12);
    }}
    .hero-panel h2 {{ margin: 0 0 18px; font-size: 19px; color: #f6dfb7; }}
    .run-chip {{ padding: 16px; border-radius: 20px; background: rgba(255,255,255,.08); margin-bottom: 12px; border: 1px solid rgba(255,255,255,.12); }}
    .run-chip span {{ display: block; color: rgba(255,255,255,.62); font-size: 12px; }}
    .run-chip strong {{ display: block; font-size: 18px; margin: 6px 0; word-break: break-word; }}
    .run-chip em {{ color: rgba(255,255,255,.82); font-style: normal; }}
    .run-chip.good {{ border-left: 5px solid #61c497; }}
    .run-chip.bad {{ border-left: 5px solid #e16b59; }}
    main {{ padding: 10px 7vw 72px; position: relative; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin: -62px 0 34px; position: relative; z-index: 2; }}
    .card {{ background: rgba(255, 252, 244, .92); border: 1px solid var(--line); border-radius: 26px; padding: 20px; box-shadow: 0 18px 50px rgba(82, 62, 32, .10); backdrop-filter: blur(10px); }}
    .card-title {{ color: var(--muted); font-size: 13px; font-weight: 700; }}
    .card-value {{ font-size: 34px; font-weight: 900; margin-top: 9px; letter-spacing: -.04em; }}
    .card-note {{ color: var(--muted); font-size: 12px; margin-top: 8px; min-height: 18px; }}
    section {{ margin-top: 28px; background: var(--panel); border: 1px solid var(--line); border-radius: 32px; padding: 28px; overflow: hidden; box-shadow: 0 20px 70px rgba(82, 62, 32, .08); }}
    h2 {{ font-size: 30px; margin: 0 0 10px; letter-spacing: -.03em; }}
    h3 {{ margin: 0 0 14px; }}
    .section-note {{ color: var(--muted); margin: 0 0 22px; line-height: 1.65; max-width: 920px; }}
    .table-wrap {{ overflow-x: auto; border-radius: 20px; border: 1px solid rgba(23, 35, 31, .10); }}
    table {{ width: 100%; border-collapse: collapse; background: rgba(255,255,255,.46); }}
    th, td {{ padding: 12px 14px; border-bottom: 1px solid rgba(23, 35, 31, .10); vertical-align: top; font-size: 13px; }}
    th {{ text-align: left; color: #3f4a45; background: rgba(216, 201, 173, .42); white-space: nowrap; position: sticky; top: 0; }}
    td {{ max-width: 390px; }}
    a {{ color: var(--blue); text-decoration: none; font-weight: 700; }}
    a:hover {{ text-decoration: underline; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    .warn {{ border-left: 5px solid var(--red); padding: 14px 16px; background: rgba(182, 64, 50, .08); color: #673029; border-radius: 16px; line-height: 1.65; }}
    .insight-grid {{ display: grid; grid-template-columns: 1.1fr .9fr; gap: 18px; }}
    .insight-box {{ background: rgba(26,35,31,.94); color: #fff; border-radius: 26px; padding: 24px; }}
    .insight-box b {{ color: #f3d39d; }}
    .insight-box p {{ color: rgba(255,255,255,.78); line-height: 1.75; }}
    .case-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    .case-card {{ border-radius: 24px; padding: 18px; background: rgba(255,255,255,.55); border: 1px solid var(--line); min-height: 250px; display: flex; flex-direction: column; }}
    .case-card.loss {{ border-top: 6px solid var(--red); }}
    .case-card.win {{ border-top: 6px solid var(--green); }}
    .case-top {{ display: flex; justify-content: space-between; color: var(--muted); font-size: 13px; }}
    .case-return {{ font-size: 36px; font-weight: 900; margin: 12px 0 6px; letter-spacing: -.05em; }}
    .loss .case-return {{ color: var(--red); }}
    .win .case-return {{ color: var(--green); }}
    .case-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }}
    .case-meta span {{ padding: 5px 9px; border-radius: 999px; background: rgba(16,22,20,.07); font-size: 12px; }}
    .case-card p {{ color: #4a5652; line-height: 1.6; font-size: 13px; flex: 1; }}
    .case-links {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .position-strip {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 20px; }}
    .position-card {{ background: rgba(255,255,255,.56); border: 1px solid var(--line); border-radius: 22px; padding: 16px; }}
    .position-card span {{ display: block; color: var(--muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .position-card strong {{ display: block; font-size: 32px; margin: 8px 0 0; }}
    .position-card em {{ color: var(--gold); font-style: normal; font-size: 12px; font-weight: 800; }}
    .position-card p {{ color: var(--muted); line-height: 1.5; font-size: 12px; }}
    footer {{ color: var(--muted); padding: 0 7vw 36px; }}
    @media (max-width: 980px) {{
      header, .insight-grid {{ grid-template-columns: 1fr; }}
      .cards, .grid-2, .case-grid, .position-strip {{ grid-template-columns: 1fr; }}
      .cards {{ margin-top: 0; }}
      header, main, footer {{ padding-left: 20px; padding-right: 20px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <div class="eyebrow">TradingAgents A-Share Evidence Board</div>
      <h1>不是展示一堆表，而是解释 agent 为什么赚、为什么亏、哪里踏空。</h1>
      <p class="lead">这是一张本地实验驾驶舱：从 signals、reports、trajectories、audit_reports 和 Qlib 回测文件自动抽取证据，按“结论 - case - 原始文档”组织。</p>
      <div class="hero-actions">
        <a class="button" href="#cases">看关键 case</a>
        <a class="button secondary" href="#runs">看运行与回测表</a>
        <a class="button secondary" href="#position">看空仓/踏空统计</a>
      </div>
    </div>
    <aside class="hero-panel">
      <h2>当前最该先看的三个结论</h2>
      {run_chip(best_run, "收益最高")}
      {run_chip(worst_run, "收益最低")}
      <div class="run-chip">
        <span>平均相对 Buy&Hold</span>
        <strong>{pct(mean_excess)}</strong>
        <em>负值说明 agent 仓位控制没有稳定跑赢满仓持有。</em>
      </div>
    </aside>
  </header>
  <main>
    <div class="cards">
      {card("Run 数量", str(total_runs), "outputs/runs 下的实验目录")}
      {card("中间报告", str(total_reports), "Markdown reports 总数")}
      {card("可归因决策", str(total_cases), "由 signal + 回测 report 对齐得到")}
      {card("正收益 Run", f"{positive_runs}/{total_runs}", "只统计已有 Qlib 回测的 run")}
    </div>

    <section>
      <h2>研究结论先行</h2>
      <div class="insight-grid">
        <div class="insight-box">
          <b>核心发现</b>
          <p>当前结果不是简单证明 TradingAgents 有效，而是暴露了更具体的问题：agent 能在部分下跌窗口通过低仓位避险，但在强趋势上涨股上容易因为保守仓位踏空，导致相对 Buy&Hold 的超额不稳定。</p>
        </div>
        <div class="warn">口径提醒：运行时间是 artifact 修改时间跨度，低仓/踏空是标的窗口收益代理。严格“大盘下跌时空仓”还需要把指数行情接入同一回测窗口。</div>
      </div>
    </section>

    <section id="cases">
      <h2>亏额较大与涨额较大的 case</h2>
      <p class="section-note">先用卡片看故事，再用下方表格追完整证据。每个 case 都能跳到原始 report、trajectory、audit。</p>
      <div class="grid-2">
        <div>
          <h3>亏损较大</h3>
          <div class="case-grid">{case_cards(worst, "loss")}</div>
        </div>
        <div>
          <h3>盈利较大</h3>
          <div class="case-grid">{case_cards(best, "win")}</div>
        </div>
      </div>
      <div class="table-wrap" style="margin-top: 22px;">{table(["run", "信号日", "动作", "仓位", "账户收益", "标的收益", "摘要", "文档"], case_rows(pd.concat([worst, best]).drop_duplicates() if not cases.empty else pd.DataFrame()))}</div>
    </section>

    <section id="position">
      <h2>空仓/低仓、踏空与避险统计</h2>
      <p class="section-note">当前统计用“标的下一窗口收益”做代理：低仓后标的上涨 = 踏空；低仓后标的下跌 = 避险。严格“大盘跌”需要把指数行情接入同一回测口径，目前不伪造指数结论。</p>
      <div class="position-strip">{"".join(low_summary_cards)}</div>
      <div class="table-wrap">{table(["run", "低仓次数", "踏空次数", "避险次数", "踏空机会损失", "避险损失减少", "避险/踏空比", "平均标的后续收益"], low_rows)}</div>
    </section>

    <section id="runs">
      <h2>Agent 运行时间与产物完整性</h2>
      <p class="section-note">运行时间采用 artifact 修改时间跨度近似，不等同于严格 wall-clock。结构化来源来自机器可读 DATA_SOURCE/DATA_VENDOR 头；推断来源来自旧报告文本中的 AkShare、BaoStock、东方财富、CNInfo 等明确字面线索，只能作为粗审计。</p>
      <div class="table-wrap">{table(["run", "ticker", "ok信号", "报告", "agent收益", "Buy&Hold", "超额", "Sharpe", "最大回撤", "数据源文件", "结构化来源", "推断来源", "非结构化", "artifact跨度(分钟)", "signal", "comparison", "data source"], run_rows)}</div>
    </section>
  </main>
  <footer>Generated at {html.escape(generated_at)} from local files under {html.escape(str(ROOT))}.</footer>
</body>
</html>
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run_dirs = sorted([p for p in RUNS_DIR.iterdir() if p.is_dir()])
    artifacts_by_run = {p.name: collect_artifacts(p) for p in run_dirs}

    run_summary = summarize_runs(run_dirs, artifacts_by_run)
    case_rows: list[dict[str, Any]] = []
    for artifacts in artifacts_by_run.values():
        case_rows.extend(build_case_rows(artifacts))
    cases = pd.DataFrame(case_rows)
    low_stats = make_low_position_stats(cases)

    run_summary.to_csv(OUTPUT_DIR / "run_summary.csv", index=False)
    cases.to_csv(OUTPUT_DIR / "case_studies.csv", index=False)
    low_stats.to_csv(OUTPUT_DIR / "low_position_stats.csv", index=False)

    html_text = render_dashboard(run_summary, cases, low_stats)
    (OUTPUT_DIR / "index.html").write_text(html_text, encoding="utf-8")

    manifest = {
        "run_count": len(run_summary),
        "case_count": len(cases),
        "low_position_run_count": len(low_stats),
        "outputs": {
            "index": rel(OUTPUT_DIR / "index.html"),
            "run_summary": rel(OUTPUT_DIR / "run_summary.csv"),
            "case_studies": rel(OUTPUT_DIR / "case_studies.csv"),
            "low_position_stats": rel(OUTPUT_DIR / "low_position_stats.csv"),
        },
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
