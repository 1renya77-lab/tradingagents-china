"""Deterministic data audit node before analyst execution.

The auditor reads the preflight quality table for the current run/date and
marks analysts whose inputs are empty. It does not call an LLM or infer trading
signals from missing data.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import pandas as pd

from tradingagents.agents.utils.data_availability import build_skipped_analyst_report
from tradingagents.dataflows.astock_data_provider import NEWS_LOOKBACK_DAYS, count_baostock_financial_rows
from tradingagents.utils.logging_init import get_logger
from tradingagents.dataflows.local_prefetch_cache import (
    NEWS_SOURCE_CNINFO,
    NEWS_SOURCE_EASTMONEY,
    load_json_data,
    load_market_data,
    load_news_items,
)


logger = get_logger("agents.data_auditor")


_REPORT_FIELDS = {
    "market": "market_report",
    "fundamentals": "fundamentals_report",
    "news": "news_report",
    "social": "sentiment_report",
}


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _preflight_path(config: dict[str, Any]) -> Path | None:
    run_name = config.get("run_name")
    project_dir = config.get("project_dir")
    if not run_name or not project_dir:
        return None
    return (
        Path(project_dir)
        / "outputs"
        / "runs"
        / str(run_name)
        / "data_preflight"
        / "preflight_data_quality.csv"
    )


def _load_preflight_row(config: dict[str, Any], trade_date: str) -> tuple[dict[str, str] | None, Path | None]:
    path = _preflight_path(config)
    if path is None or not path.exists():
        return None, path

    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("signal_date") == trade_date:
                return row, path
    return None, path


def _missing_reasons(row: dict[str, str], selected_analysts: list[str]) -> dict[str, str]:
    reasons: dict[str, str] = {}
    checks = {
        "market": ("market_ok", "market_rows", "market rows are below the minimum audited window"),
        "fundamentals": ("fundamentals_ok", "fundamentals_rows", "fundamentals rows are empty"),
        "news": ("news_ok", "news_rows", "news or announcement rows are empty"),
        "social": ("social_discussion_ok", "social_discussion_rows", "public social discussion rows are empty"),
    }
    for analyst in selected_analysts:
        if analyst not in checks:
            continue
        ok_col, rows_col, reason = checks[analyst]
        if not _truthy(row.get(ok_col)):
            rows = row.get(rows_col, "")
            reasons[analyst] = f"preflight {ok_col}=false; {rows_col}={rows}; {reason}"
    return reasons


def _cutoff_ts(trade_date: str) -> pd.Timestamp:
    return pd.to_datetime(f"{trade_date} 19:30:00")


def _has_intraday_time(value: object) -> bool:
    return bool(re.search(r"\d{1,2}:\d{2}", str(value or "")))


def _parse_time(value: object) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed


def _passes_cutoff(item: dict[str, Any], trade_date: str, time_keys: tuple[str, ...]) -> bool:
    cutoff = _cutoff_ts(trade_date)
    for key in time_keys:
        raw_value = item.get(key)
        parsed = _parse_time(raw_value)
        if parsed is None:
            continue
        if parsed > cutoff:
            return False
        if not _has_intraday_time(raw_value) and parsed.normalize() == cutoff.normalize():
            return False
        return True
    return False


def _passes_recent_cutoff(
    item: dict[str, Any],
    trade_date: str,
    time_keys: tuple[str, ...],
    lookback_days: int = NEWS_LOOKBACK_DAYS,
) -> bool:
    cutoff = _cutoff_ts(trade_date)
    lower_bound = cutoff - pd.Timedelta(days=int(lookback_days))
    for key in time_keys:
        raw_value = item.get(key)
        parsed = _parse_time(raw_value)
        if parsed is None:
            continue
        if parsed > cutoff or parsed < lower_bound:
            return False
        if not _has_intraday_time(raw_value) and parsed.normalize() == cutoff.normalize():
            return False
        return True
    return False


def _text_len(*values: object) -> int:
    return max((len(str(value or "").strip()) for value in values), default=0)


def _audit_market_evidence(ticker: str, trade_date: str) -> dict[str, Any]:
    df = load_market_data(ticker)
    if df is not None and not df.empty:
        cutoff = pd.to_datetime(trade_date)
        df = df[df["Date"] <= cutoff].copy()
    rows = 0 if df is None else len(df)
    return {
        "usable_rows": rows,
        "ok": rows >= 20,
        "first_date": "" if df is None or df.empty else df["Date"].min().strftime("%Y-%m-%d"),
        "last_date": "" if df is None or df.empty else df["Date"].max().strftime("%Y-%m-%d"),
        "rule": "market Date <= signal_date and at least 20 rows",
    }


def _audit_news_evidence(ticker: str, trade_date: str) -> dict[str, Any]:
    eastmoney = load_news_items(ticker, NEWS_SOURCE_EASTMONEY, snapshot_date=trade_date)
    cninfo = load_news_items(ticker, NEWS_SOURCE_CNINFO, snapshot_date=trade_date)
    eastmoney = eastmoney or []
    cninfo = cninfo or []
    usable_news = [
        item
        for item in eastmoney
        if _passes_recent_cutoff(item, trade_date, ("time", "publish_time", "date"))
    ]
    usable_announcements = [
        item
        for item in cninfo
        if _passes_recent_cutoff(item, trade_date, ("date", "publish_time"))
    ]
    text_rows = sum(
        1
        for item in usable_news
        if _text_len(item.get("title"), item.get("content")) >= 20
    ) + sum(
        1
        for item in usable_announcements
        if _text_len(item.get("title"), item.get("text_excerpt")) >= 20
    )
    usable_rows = len(usable_news) + len(usable_announcements)
    return {
        "usable_rows": usable_rows,
        "text_rows": text_rows,
        "raw_rows": len(eastmoney) + len(cninfo),
        "ok": usable_rows > 0,
        "rule": f"signal-date snapshot only; publish/disclosure time within {NEWS_LOOKBACK_DAYS} days and <= signal_date 19:30; same-day date-only rows excluded",
    }


def _audit_fundamentals_evidence(ticker: str, trade_date: str) -> dict[str, Any]:
    company = load_json_data(ticker, "fundamentals", "eastmoney_company_info")
    statements = load_json_data(ticker, "fundamentals", "sina_statements")
    baostock_financials = load_json_data(ticker, "fundamentals", "baostock_financial_indicators")
    cninfo = load_news_items(ticker, NEWS_SOURCE_CNINFO, snapshot_date=trade_date)
    if cninfo is None:
        cninfo = load_news_items(ticker, NEWS_SOURCE_CNINFO)
    cninfo = cninfo or []
    usable_announcements = [
        item
        for item in cninfo
        if _passes_cutoff(item, trade_date, ("date", "publish_time"))
    ]
    statement_rows = 0
    if isinstance(statements, dict):
        statement_rows = sum(len(value) for value in statements.values() if isinstance(value, list))
    baostock_rows = count_baostock_financial_rows(
        baostock_financials if isinstance(baostock_financials, dict) else {},
        trade_date,
    )
    value_keys = ("price", "mcap", "float_mcap", "total_shares", "float_shares", "pe", "pb")
    company_rows = (
        1
        if isinstance(company, dict)
        and any(str(company.get(key, "")).strip() not in {"", "None", "nan"} for key in value_keys)
        else 0
    )
    usable_rows = company_rows + statement_rows + baostock_rows
    return {
        "usable_rows": usable_rows,
        "company_rows": company_rows,
        "announcement_rows": len(usable_announcements),
        "statement_rows": statement_rows,
        "baostock_financial_rows": baostock_rows,
        "ok": usable_rows > 0,
        "rule": "fundamentals require valuation fields, audited statement rows, or BaoStock financial indicators disclosed by pubDate; announcements are supplementary only",
    }


def _audit_social_evidence(ticker: str, trade_date: str) -> dict[str, Any]:
    payload = load_json_data(ticker, "social", f"sentiment_{trade_date}") or {}
    if not isinstance(payload, dict):
        payload = {}
    forum = payload.get("forum_sentiment", {}) if isinstance(payload.get("forum_sentiment"), dict) else {}
    xueqiu = payload.get("xueqiu_sentiment", {}) if isinstance(payload.get("xueqiu_sentiment"), dict) else {}
    irm = payload.get("irm_sentiment", {}) if isinstance(payload.get("irm_sentiment"), dict) else {}
    news = payload.get("news_sentiment", {}) if isinstance(payload.get("news_sentiment"), dict) else {}
    cninfo = payload.get("cninfo_sentiment", {}) if isinstance(payload.get("cninfo_sentiment"), dict) else {}
    forum_rows = int(forum.get("discussion_count", 0) or 0)
    xueqiu_rows = int(xueqiu.get("post_count", 0) or 0)
    irm_rows = int(irm.get("irm_count", 0) or 0)
    discussion_rows = forum_rows + xueqiu_rows + irm_rows
    return {
        "usable_rows": discussion_rows,
        "forum_rows": forum_rows,
        "xueqiu_rows": xueqiu_rows,
        "irm_rows": irm_rows,
        "news_rows": int(news.get("news_count", 0) or 0),
        "cninfo_event_rows": int(cninfo.get("event_count", 0) or 0),
        "snapshot_cache_present": bool(payload),
        "ok": discussion_rows > 0,
        "rule": "EastMoney Guba, Xueqiu, and CNInfo IRM rows count as social evidence; announcements remain news/fundamentals evidence",
    }


def _audit_all_evidence(ticker: str, trade_date: str, selected_analysts: list[str]) -> dict[str, dict[str, Any]]:
    auditors = {
        "market": _audit_market_evidence,
        "news": _audit_news_evidence,
        "fundamentals": _audit_fundamentals_evidence,
        "social": _audit_social_evidence,
    }
    results: dict[str, dict[str, Any]] = {}
    for analyst in selected_analysts:
        auditor = auditors.get(analyst)
        if auditor is None:
            continue
        try:
            results[analyst] = auditor(ticker, trade_date)
        except Exception as exc:
            results[analyst] = {
                "usable_rows": 0,
                "ok": False,
                "error": str(exc),
                "rule": "evidence audit failed",
            }
    return results


def _merge_evidence_reasons(
    reasons: dict[str, str],
    evidence: dict[str, dict[str, Any]],
    selected_analysts: list[str],
) -> dict[str, str]:
    merged = dict(reasons)
    for analyst in selected_analysts:
        detail = evidence.get(analyst)
        if not detail or detail.get("ok"):
            continue
        rows = detail.get("usable_rows", 0)
        reason = f"evidence audit failed; usable_evidence_rows={rows}; {detail.get('rule', '')}"
        if detail.get("error"):
            reason += f"; error={detail['error']}"
        if analyst in merged:
            merged[analyst] = f"{merged[analyst]}; {reason}"
        else:
            merged[analyst] = reason
    return merged


def create_data_auditor(config: dict[str, Any] | None = None, selected_analysts: list[str] | None = None):
    """Create a LangGraph node that marks empty analyst inputs before analysis."""

    config = config or {}
    selected_analysts = list(selected_analysts or [])

    def data_auditor_node(state):
        ticker = state["company_of_interest"]
        trade_date = state["trade_date"]
        row, path = _load_preflight_row(config, trade_date)

        if row is None:
            report = (
                "Data Auditor\n"
                f"TICKER: {ticker}\n"
                f"CUTOFF_DATE: {trade_date}\n"
                f"PREFLIGHT_PATH: {path or '<not configured>'}\n"
                "RESULT: no preflight row found; no analyst skip marks were added."
            )
            logger.info("[Data Auditor] no preflight row found for %s @ %s", ticker, trade_date)
            return {"data_audit_report": report, "data_evidence_audit": {}, "skip_analysts": {}}

        evidence_audit = _audit_all_evidence(ticker, trade_date, selected_analysts)
        skip_analysts = _merge_evidence_reasons(
            _missing_reasons(row, selected_analysts),
            evidence_audit,
            selected_analysts,
        )
        updates: dict[str, Any] = {
            "skip_analysts": skip_analysts,
            "data_evidence_audit": evidence_audit,
            "data_audit_report": (
                "Data Auditor\n"
                f"TICKER: {ticker}\n"
                f"CUTOFF_DATE: {trade_date}\n"
                f"PREFLIGHT_PATH: {path}\n"
                f"SKIPPED: {', '.join(skip_analysts) if skip_analysts else 'none'}\n"
                f"EVIDENCE_AUDIT: {evidence_audit}"
            ),
        }

        for analyst, reason in skip_analysts.items():
            report_field = _REPORT_FIELDS.get(analyst)
            if report_field:
                updates[report_field] = build_skipped_analyst_report(
                    analyst=analyst,
                    ticker=ticker,
                    current_date=trade_date,
                    reason=reason,
                    raw_payload=updates["data_audit_report"],
                )

        logger.info(
            "[Data Auditor] %s @ %s skipped analysts: %s",
            ticker,
            trade_date,
            sorted(skip_analysts),
        )
        return updates

    return data_auditor_node
