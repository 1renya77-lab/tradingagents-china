"""Utilities for skipping analysts when their input data is absent.

These helpers only decide whether an analyst has usable evidence. They do not
convert missing data into a trading signal.
"""

from __future__ import annotations


_MISSING_MARKERS = (
    "DATA_QUALITY: ok=false",
    "ROWS: 0",
    "No audited stock news",
    "No audited company announcements",
    "No audited fundamentals",
    "Company profile unavailable",
    "截止日前无可用新闻",
    "前未获取到稳定新闻",
    "无可用新闻",
    "未检索到符合条件的新闻",
    "截止日前无具备可解析发布时间的新闻",
    "unavailable",
    "<unavailable>",
    "数据获取失败",
    "新闻获取失败",
    "情绪数据获取失败",
    "no StockTwits messages found",
    "no Reddit posts found",
    "no posts found mentioning",
)


MISSING_DATA_INTERPRETATION_RULE = """数据缺失解释约束：
- news/social 数据缺失只表示该信息源在本次 A 股场景下不可用或未通过时间戳审核，不是利空证据。
- fundamentals 数据缺失或覆盖不足只表示无法完成基本面估值，不是公司基本面恶化的证据；如果没有可审计财报或有效估值字段，应跳过基本面分析，而不是输出看空结论。
- 不得把新闻/社交缺失描述为红色警报、信息黑箱、缺乏催化剂导致看空，除非已有其他可观察证据支持。
- 可以把缺失信息作为证据覆盖不足来降低结论置信度，或要求更多确认，但不能单独推出卖出、减仓或降低仓位。
- 负面结论必须来自实际负面证据，例如价格/量能恶化、财务指标恶化、公告利空、风险事件或可验证的行业压力。"""


def is_missing_data_payload(payload: object) -> bool:
    """Return True when a data payload has no usable analyst evidence."""
    if payload is None:
        return True

    text = str(payload).strip()
    if not text:
        return True

    if "DATA_QUALITY: ok=true" in text:
        return False

    return any(marker in text for marker in _MISSING_MARKERS)


def has_failed_data_quality(payload: object) -> bool:
    """Return True when a payload explicitly declares failed data quality."""
    if payload is None:
        return True
    return "DATA_QUALITY: ok=false" in str(payload)


def build_skipped_analyst_report(
    *,
    analyst: str,
    ticker: str,
    current_date: str,
    reason: str,
    raw_payload: object = "",
) -> str:
    """Build an explicit report for downstream agents when an analyst is skipped."""
    lines = [
        f"## {analyst} 数据审核结果",
        "",
        f"- 标的: {ticker}",
        f"- 截止日期: {current_date} 19:30",
        "- 状态: 该分析师本次跳过",
        f"- 原因: {reason}",
        "- 决策影响: 本分析师因缺少可审计输入数据被跳过；不要把缺失数据解读为利好、利空或中性信号。",
        "",
        "说明: 详细的数据路径、逐条证据审核和内部字段已保留在 audit/provenance 文件中，复盘报告不展开这些调试信息。",
    ]
    return "\n".join(lines)
