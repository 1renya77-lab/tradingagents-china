"""
Utilities for converting TradingAgents text decisions into executable positions.

The LLM output often says "持有40%-50%仓位" while the coarse action remains "持有".
For backtests, the target position is the executable object; action labels are
too lossy.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _percent_to_float(value: str) -> float:
    return _clamp(float(value) / 100.0)


def _range_midpoint(low: str, high: str) -> float:
    return _clamp((_percent_to_float(low) + _percent_to_float(high)) / 2.0)


def derive_target_position(action: str, text: str) -> float:
    """Derive a long-only target position from action plus Chinese decision text."""
    action = (action or "").strip()
    text = (text or "").replace("％", "%")

    below_match = re.search(r"(?:减持|减仓|降仓|仓位|持仓)[^。\n，,；;]{0,12}?(?:至|到|在|不超过|低于|以下|小于)\s*(\d+(?:\.\d+)?)\s*%\s*(?:以下|以内|内)?", text)
    if below_match:
        return round(_percent_to_float(below_match.group(1)), 4)

    cap_match = re.search(r"(?:仓位上限|上限|不超过|控制在)\s*(\d+(?:\.\d+)?)\s*%", text)
    if cap_match:
        return round(_percent_to_float(cap_match.group(1)), 4)

    target_patterns = (
        r"(?:仓位|持仓|保留仓位|控制仓位|维持仓位|保持仓位|建仓|轻仓|重仓)[^。\n，,；;]{0,12}?(\d+(?:\.\d+)?)\s*%?\s*[-~—至到]\s*(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%?\s*[-~—至到]\s*(\d+(?:\.\d+)?)\s*%[^。\n，,；;]{0,12}?(?:仓位|持仓|建仓)",
    )
    for pattern in target_patterns:
        match = re.search(pattern, text)
        if match:
            return round(_range_midpoint(match.group(1), match.group(2)), 4)

    reduce_range_match = re.search(r"减仓\s*(\d+(?:\.\d+)?)\s*%?\s*[-~—至到]\s*(\d+(?:\.\d+)?)\s*%", text)
    if reduce_range_match:
        reduce_midpoint = _range_midpoint(reduce_range_match.group(1), reduce_range_match.group(2))
        return round(_clamp(1.0 - reduce_midpoint), 4)

    reduce_single_match = re.search(r"减仓\s*(\d+(?:\.\d+)?)\s*%", text)
    if reduce_single_match:
        return round(_clamp(1.0 - _percent_to_float(reduce_single_match.group(1))), 4)

    if re.search(r"清仓|空仓等待|不建仓|不宜建仓|当前不建仓", text) and action == "卖出":
        return 0.0

    action_defaults = {
        "买入": 0.80,
        "持有": 0.50,
        "卖出": 0.00,
    }
    return action_defaults.get(action, 0.50)


def format_position_percent(target_position: float) -> str:
    return f"{_clamp(float(target_position)) * 100:.1f}%"


def execution_summary(action: str, target_position: float) -> str:
    percent = format_position_percent(target_position)
    return (
        f"原始操作={action or 'N/A'}，执行目标仓位={percent}。"
        "回测按目标仓位在下一交易日调仓；"
        "如果原始操作是“持有”，这里表示维持或调整到该仓位，不是简单保持不动。"
    )


def audit_text_for_row(audit_dir: Path, ticker: str, date: str) -> str:
    path = audit_dir / f"audit_{ticker}_{date}.json"
    if not path.exists():
        return ""

    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    final_decision = data.get("final_decision") or {}
    parsed_decision = final_decision.get("parsed_decision") or {}
    parts = [
        str(parsed_decision.get("reasoning") or ""),
        str(final_decision.get("llm_output") or ""),
    ]
    return "\n".join(part for part in parts if part)


def add_target_positions(
    signals_path: Path,
    output_path: Path | None = None,
    audit_dir: Path | None = None,
) -> Path:
    signals_path = signals_path.expanduser().resolve()
    if audit_dir is None:
        audit_dir = signals_path.parent.parent / "audit_reports"

    df = pd.read_csv(signals_path)
    if "date" not in df.columns or "ticker" not in df.columns or "action" not in df.columns:
        raise ValueError("signals CSV must include date, ticker, and action columns")

    positions = []
    for _, row in df.iterrows():
        date = str(row["date"])
        ticker = str(row["ticker"])
        text = "\n".join(
            part
            for part in [
                str(row.get("reasoning") or ""),
                audit_text_for_row(audit_dir, ticker, date),
            ]
            if part
        )
        positions.append(derive_target_position(str(row.get("action") or ""), text))

    out = df.copy()
    out["target_position"] = positions

    if output_path is None:
        output_path = signals_path.with_name(f"{signals_path.stem}_position.csv")
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False, encoding="utf-8")
    return output_path


def update_report_with_position(
    report_path: Path,
    row: pd.Series,
) -> bool:
    report_path = report_path.expanduser().resolve()
    if not report_path.exists():
        return False

    text = report_path.read_text(encoding="utf-8")
    if "## 最终信号" not in text or "## 最终摘要" not in text:
        return False

    action = str(row.get("action") or "N/A")
    target_position = float(row.get("target_position"))
    summary = execution_summary(action, target_position)

    signal_block = "\n".join(
        [
            "## 最终信号",
            "",
            f"- 原始操作: {action}",
            f"- 执行目标仓位: {format_position_percent(target_position)}",
            f"- 执行说明: {summary}",
            f"- 目标价: {row.get('target_price', 'N/A')}",
            f"- 置信度: {row.get('confidence', 'N/A')}",
            f"- 风险得分: {row.get('risk_score', 'N/A')}",
            f"- 原始信号分数: {row.get('score', 'N/A')}",
        ]
    )

    text = re.sub(
        r"## 最终信号\n\n.*?\n\n## 最终摘要",
        signal_block + "\n\n## 最终摘要",
        text,
        count=1,
        flags=re.S,
    )

    execution_block = (
        "### 回测执行口径\n\n"
        f"{summary}\n\n"
        "以下为原始决策摘要："
    )

    if "### 回测执行口径" in text:
        text = re.sub(
            r"### 回测执行口径\n\n.*?\n\n以下为原始决策摘要：",
            execution_block,
            text,
            count=1,
            flags=re.S,
        )
    else:
        text = text.replace(
            "## 最终摘要\n\n",
            "## 最终摘要\n\n"
            f"{execution_block}\n\n",
            1,
        )

    report_path.write_text(text, encoding="utf-8")
    return True


def update_reports_from_position_signals(
    signals_path: Path,
    reports_dir: Path | None = None,
) -> int:
    signals_path = signals_path.expanduser().resolve()
    df = pd.read_csv(signals_path)
    if "target_position" not in df.columns:
        raise ValueError("signals CSV must include target_position")

    if reports_dir is None:
        reports_dir = signals_path.parent.parent / "reports"
    reports_dir = reports_dir.expanduser().resolve()

    count = 0
    for _, row in df.iterrows():
        ticker = str(row["ticker"])
        date = str(row["date"])
        report_path = reports_dir / f"report_{ticker}_{date}.md"
        if update_report_with_position(report_path, row):
            count += 1
    return count
