#!/usr/bin/env python3
"""Extract mechanism-level attribution from TradingAgents audit artifacts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


REPORT_KEYS = {
    "market_report": "market",
    "fundamentals_report": "fundamentals",
    "news_report": "news",
    "sentiment_report": "social",
}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def infer_direction(text: str) -> str:
    content = _text(text).lower()
    bullish_words = ["看涨", "买入", "上涨", "多头", "bull", "bullish", "提高仓位", "进攻"]
    bearish_words = ["看跌", "卖出", "下跌", "空头", "bear", "bearish", "降低仓位", "回避"]
    bull_score = sum(word in content for word in bullish_words)
    bear_score = sum(word in content for word in bearish_words)
    if bull_score > bear_score:
        return "bullish"
    if bear_score > bull_score:
        return "bearish"
    if bull_score or bear_score:
        return "mixed"
    return "unknown"


def extract_position(text: str) -> float | None:
    content = _text(text).replace("％", "%")
    patterns = [
        r"target_position\s*[:：]\s*(\d+(?:\.\d+)?)\s*%",
        r"目标仓位\s*[:：]?\s*(\d+(?:\.\d+)?)\s*%",
        r"Target Position\*\*:\s*(\d+(?:\.\d+)?)\s*%",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, flags=re.I)
        if match:
            value = float(match.group(1))
            return value / 100.0 if value > 1 else value
    return None


def evidence_count(reasoning: str) -> int:
    content = _text(reasoning)
    signals = ["均线", "MACD", "RSI", "布林", "ROE", "PE", "PB", "新闻", "情绪", "催化", "风险", "支撑", "压力"]
    return sum(1 for item in signals if item in content)


def report_availability(input_state: dict[str, Any]) -> str:
    available = []
    for key, label in REPORT_KEYS.items():
        text = _text(input_state.get(key))
        if text.strip() and text.strip() != "无":
            available.append(label)
    return ",".join(available)


def missing_flags(input_state: dict[str, Any]) -> str:
    flags = []
    for key, label in REPORT_KEYS.items():
        text = _text(input_state.get(key))
        if not text.strip() or "缺失" in text or "获取失败" in text or "无具备" in text:
            flags.append(label)
    return ",".join(flags)


def _load_feedback(run_dir: Path) -> dict[str, dict[str, Any]]:
    path = run_dir / "feedback_windows.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    if "signal_date" not in df.columns:
        return {}
    return {str(row["signal_date"]): row.to_dict() for _, row in df.iterrows()}


def _feedback_winning_side(feedback: dict[str, Any]) -> str:
    try:
        stock_return = float(feedback.get("stock_return", 0.0))
        target_position = float(feedback.get("target_position", 0.0))
    except (TypeError, ValueError):
        return "unknown"
    if stock_return > 0.03:
        return "bullish"
    if stock_return < -0.03:
        return "bearish" if target_position <= 0.5 else "safe"
    return "neutral"


def build_attribution_rows(run_dir: Path, *, experiment_mode: str = "") -> list[dict[str, Any]]:
    audit_dir = run_dir / "audit_reports"
    if not audit_dir.exists():
        return []
    feedback_by_date = _load_feedback(run_dir)
    rows = []
    for audit_path in sorted(audit_dir.glob("audit_*.json")):
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        meta = payload.get("meta", {})
        input_state = payload.get("input_state", {})
        investment = payload.get("investment_debate", {})
        risk = payload.get("risk_debate", {})
        final = payload.get("final_decision", {})
        parsed = final.get("parsed_decision", {}) if isinstance(final.get("parsed_decision"), dict) else {}
        trade_date = str(meta.get("trade_date", ""))
        mode = experiment_mode or meta.get("experiment_mode") or ""
        final_position = parsed.get("target_position")
        if final_position is None:
            final_position = extract_position(_text(final.get("llm_output")))

        pm_position = extract_position(_text(investment.get("judge_decision")))
        risk_position = extract_position(_text(risk.get("judge_decision")))
        feedback = feedback_by_date.get(trade_date, {})

        rows.append(
            {
                "experiment_mode": mode,
                "ticker": meta.get("company_of_interest", ""),
                "signal_date": trade_date,
                "audit_file": str(audit_path),
                "analyst_reports_available": report_availability(input_state),
                "data_missing_flags": missing_flags(input_state),
                "final_action": parsed.get("action", ""),
                "final_position": final_position,
                "pm_position_before_risk": pm_position,
                "risk_position": risk_position,
                "bull_direction": infer_direction(_text(investment.get("bull_history"))),
                "bear_direction": infer_direction(_text(investment.get("bear_history"))),
                "risky_direction": infer_direction(_text(risk.get("risky_history"))),
                "safe_direction": infer_direction(_text(risk.get("safe_history"))),
                "neutral_direction": infer_direction(_text(risk.get("neutral_history"))),
                "debate_changed_position": (
                    pm_position is not None
                    and final_position is not None
                    and abs(float(pm_position) - float(final_position)) > 0.05
                ),
                "debate_change_helped": bool(feedback and feedback.get("decision_quality_score", 0) >= 0.5),
                "winning_side": _feedback_winning_side(feedback) if feedback else "unknown",
                "case_type": feedback.get("case_type", ""),
                "explanation_quality": evidence_count(parsed.get("reasoning", "")),
            }
        )
    return rows


def write_mechanism_attribution(run_dir: Path, output_path: Path, *, experiment_mode: str = "") -> Path:
    rows = build_attribution_rows(run_dir, experiment_mode=experiment_mode)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build mechanism attribution from audit reports.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--experiment-mode", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = write_mechanism_attribution(
        Path(args.run_dir),
        Path(args.output),
        experiment_mode=args.experiment_mode,
    )
    print(f"mechanism_attribution: {path}")


if __name__ == "__main__":
    main()
