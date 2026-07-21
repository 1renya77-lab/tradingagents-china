from __future__ import annotations

import re
from typing import Any


HARD_PATTERNS = (
    "DATA_QUALITY",
    "DATA_SOURCE",
    "DATA_VENDOR",
    "ROWS",
    "CUTOFF_DATE",
    "TEMPORAL_RULE",
    "WARNING",
    "report_period_only",
    "No audited",
    "截止日前无可用新闻",
    "数据缺失",
    "不可用",
    "无法获取",
)


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text or "").splitlines() if line.strip()]


def _dedupe_keep_order(lines: list[str]) -> list[str]:
    seen = set()
    out = []
    for line in lines:
        key = re.sub(r"\s+", " ", line)
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out


def _score_line(line: str) -> int:
    score = 0
    if any(pattern in line for pattern in HARD_PATTERNS):
        score += 100
    if re.search(r"MACD|RSI|MA\d+|均线|布林|支撑|压力|成交量|趋势", line, re.I):
        score += 30
    if re.search(r"风险|止损|回撤|缺失|利空|制裁|不确定|约束", line):
        score += 25
    if re.search(r"利好|催化|增长|突破|反弹|强势|改善", line):
        score += 20
    if re.search(r"仓位|买入|卖出|持有|观望|减仓|加仓", line):
        score += 20
    if re.search(r"\d", line):
        score += 10
    return score


def build_evidence_brief(label: str, text: str, max_chars: int = 1600) -> str:
    """Compress a report without dropping audit-critical evidence.

    This is intentionally deterministic: it extracts high-signal lines and never
    introduces new facts or interpretations.
    """
    lines = _clean_lines(text)
    if not lines:
        return f"{label.upper()}_BRIEF: empty"

    hard_lines = [line for line in lines if any(pattern in line for pattern in HARD_PATTERNS)]
    candidate_lines = sorted(lines, key=_score_line, reverse=True)
    selected = _dedupe_keep_order(hard_lines + candidate_lines[:18])

    header = f"{label.upper()}_BRIEF"
    out_lines = [header]
    for line in selected:
        next_line = f"- {line}"
        if len("\n".join(out_lines + [next_line])) > max_chars:
            continue
        out_lines.append(next_line)

    if len(out_lines) == 1:
        snippet = " ".join(lines)[: max_chars - len(header) - 8]
        out_lines.append(f"- {snippet}")
    return "\n".join(out_lines)[:max_chars]


def compressed_report(state: dict[str, Any], report_key: str, brief_key: str, label: str, max_chars: int) -> str:
    existing = state.get(brief_key)
    if existing:
        return str(existing)
    return build_evidence_brief(label, state.get(report_key, ""), max_chars=max_chars)


def compressed_debate_text(text: str, label: str, max_chars: int = 1200) -> str:
    return build_evidence_brief(label, text, max_chars=max_chars)


def use_context_compression(config: dict[str, Any] | None) -> bool:
    return bool((config or {}).get("context_compression_enabled", False))
