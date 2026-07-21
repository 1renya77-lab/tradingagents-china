from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd


def infer_ticker_from_signal(path: Path) -> str:
    match = re.search(r"signals_([^_]+)_", path.name)
    if not match:
        raise ValueError(f"Cannot infer ticker from signal filename: {path.name}")
    return match.group(1)


def format_instrument(ticker: str) -> str:
    ticker = str(ticker).upper().strip()
    if ticker.startswith(("SH", "SZ")):
        return ticker
    if len(ticker) == 6 and ticker.isdigit():
        return f"SH{ticker}" if ticker.startswith(("5", "6", "9")) else f"SZ{ticker}"
    return ticker


def _weight_column(positions: pd.DataFrame, ticker: str) -> str:
    preferred = f"{format_instrument(ticker)}.weight"
    if preferred in positions.columns:
        return preferred
    candidates = [col for col in positions.columns if col.endswith(".weight")]
    if not candidates:
        raise ValueError("positions CSV does not contain a *.weight column")
    return candidates[0]


def _build_execution_aligned_rows(
    *,
    signals: pd.DataFrame,
    positions: pd.DataFrame,
    weight_col: str,
    tolerance_pct_point: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if positions.empty:
        return rows

    matched_signal_dates: set[pd.Timestamp] = set()
    previous_dt: pd.Timestamp | None = None

    for _, execution in positions.iterrows():
        execution_dt = pd.Timestamp(execution["datetime"])
        if previous_dt is None:
            previous_dt = execution_dt
            continue

        interval_signals = signals[
            (signals["date"] >= previous_dt) & (signals["date"] < execution_dt)
        ].sort_values("date")
        if interval_signals.empty:
            previous_dt = execution_dt
            continue

        signal = interval_signals.iloc[-1]
        signal_dt = pd.Timestamp(signal["date"])
        matched_signal_dates.add(signal_dt)
        target = float(signal["target_position"])
        actual = float(execution[weight_col])
        diff = (actual - target) * 100.0
        rows.append(
            {
                "signal_date": signal_dt.strftime("%Y-%m-%d"),
                "execution_date": execution_dt.strftime("%Y-%m-%d"),
                "status": "checked",
                "action": signal.get("action", ""),
                "target_position": target,
                "actual_weight": actual,
                "diff_pct_point": diff,
                "flag_abs_diff_gt_tolerance": abs(diff) > tolerance_pct_point,
                "signal_window_start": previous_dt.strftime("%Y-%m-%d"),
                "signal_window_end": execution_dt.strftime("%Y-%m-%d"),
            }
        )
        previous_dt = execution_dt

    for _, signal in signals.iterrows():
        signal_dt = pd.Timestamp(signal["date"])
        if signal_dt in matched_signal_dates:
            continue
        future_positions = positions[positions["datetime"] > signal_dt]
        status = "skipped_no_future_execution_window" if future_positions.empty else "skipped_superseded_in_window"
        row: dict[str, Any] = {
            "signal_date": signal_dt.strftime("%Y-%m-%d"),
            "status": status,
            "target_position": float(signal["target_position"]),
            "action": signal.get("action", ""),
        }
        if not future_positions.empty:
            row["next_position_date"] = pd.Timestamp(future_positions.iloc[0]["datetime"]).strftime("%Y-%m-%d")
        rows.append(row)

    rows.sort(
        key=lambda row: (
            row.get("signal_date", ""),
            row.get("execution_date", ""),
            row.get("status", ""),
        )
    )
    return rows


def audit_position_alignment(
    *,
    signals_path: Path,
    positions_path: Path,
    output_dir: Path,
    tolerance_pct_point: float = 2.0,
    ticker: str | None = None,
) -> dict[str, Any]:
    signals_path = Path(signals_path)
    positions_path = Path(positions_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ticker = ticker or infer_ticker_from_signal(signals_path)

    signals = pd.read_csv(signals_path)
    if "target_position" not in signals.columns:
        raise ValueError("signals CSV must include target_position")
    if "date" not in signals.columns:
        raise ValueError("signals CSV must include date")

    if "status" in signals.columns:
        signals = signals[signals["status"].fillna("ok").astype(str).str.lower().eq("ok")]
    signals = signals.copy()
    signals["date"] = pd.to_datetime(signals["date"])
    signals["target_position"] = pd.to_numeric(signals["target_position"], errors="coerce")
    signals = signals.dropna(subset=["date", "target_position"]).sort_values("date")

    positions = pd.read_csv(positions_path)
    if "datetime" not in positions.columns:
        raise ValueError("positions CSV must include datetime")
    weight_col = _weight_column(positions, ticker)
    positions = positions.copy()
    positions["datetime"] = pd.to_datetime(positions["datetime"])
    positions[weight_col] = pd.to_numeric(positions[weight_col], errors="coerce").fillna(0.0)
    positions = positions.sort_values("datetime")

    rows = _build_execution_aligned_rows(
        signals=signals,
        positions=positions,
        weight_col=weight_col,
        tolerance_pct_point=tolerance_pct_point,
    )

    details = pd.DataFrame(rows)
    checked = details[details["status"].eq("checked")] if not details.empty else pd.DataFrame()
    flagged = int(checked["flag_abs_diff_gt_tolerance"].sum()) if not checked.empty else 0
    max_abs = float(checked["diff_pct_point"].abs().max()) if not checked.empty else 0.0
    verdict = "pass" if flagged == 0 and not checked.empty else ("fail" if flagged else "warn")

    details_path = output_dir / "position_alignment_details.csv"
    summary_path = output_dir / "position_alignment_summary.csv"
    report_path = output_dir / "position_alignment.md"
    details.to_csv(details_path, index=False)
    summary = pd.DataFrame(
        [
            {
                "verdict": verdict,
                "ticker": ticker,
                "signals_path": str(signals_path),
                "positions_path": str(positions_path),
                "checked_rows": len(checked),
                "flagged_rows": flagged,
                "tolerance_pct_point": tolerance_pct_point,
                "max_abs_diff_pct_point": max_abs,
            }
        ]
    )
    summary.to_csv(summary_path, index=False)

    lines = [
        "# Position Alignment Audit",
        "",
        f"- Verdict: **{verdict.upper()}**",
        f"- Ticker: `{ticker}`",
        f"- Signals: `{signals_path}`",
        f"- Positions: `{positions_path}`",
        f"- Checked rows: {len(checked)}",
        f"- Flagged rows: {flagged}",
        f"- Tolerance: {tolerance_pct_point:.2f} percentage points",
        f"- Max absolute diff: {max_abs:.4f} percentage points",
        "",
        "Rule: for each Qlib execution interval, use the last valid signal inside that interval and compare its `target_position` against the actual stock weight on that execution day.",
    ]
    superseded = details[details["status"].eq("skipped_superseded_in_window")] if not details.empty else pd.DataFrame()
    if not superseded.empty:
        lines.extend(
            [
                "",
                "## Superseded Signals",
                "",
                "These signals were followed by a newer signal before the next executable position snapshot, so they were not the effective signal used by Qlib for alignment.",
                "",
            ]
        )
        for _, row in superseded.iterrows():
            lines.append(
                f"- {row['signal_date']}: superseded before next execution snapshot"
            )
    if flagged:
        lines.extend(["", "## Flagged Rows", ""])
        for _, row in checked[checked["flag_abs_diff_gt_tolerance"]].iterrows():
            lines.append(
                f"- {row['signal_date']} [{row['signal_window_start']} -> {row['signal_window_end']}] -> {row['execution_date']}: "
                f"target={row['target_position']:.2%}, actual={row['actual_weight']:.2%}, "
                f"diff={row['diff_pct_point']:.2f}pp"
            )
    report_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "verdict": verdict,
        "checked_rows": int(len(checked)),
        "flagged_rows": flagged,
        "max_abs_diff_pct_point": max_abs,
        "summary_csv": str(summary_path),
        "details_csv": str(details_path),
        "report_md": str(report_path),
    }
