from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


SOURCE_STACK = {
    "market": [
        "local_prefetch_cache",
        "AkShare A-share OHLCV",
        "BaoStock A-share OHLCV",
        "Qlib provider for backtest execution",
    ],
    "news": [
        "a-stock-data / EastMoney stock news",
        "a-stock-data / CNInfo announcements",
        "AkShare stock_news_em",
        "AkShare news_cctv for market-wide news",
    ],
    "fundamentals": [
        "a-stock-data / EastMoney company profile",
        "a-stock-data / CNInfo announcements",
        "a-stock-data / Sina financial statements gated by audited announcements",
        "AkShare financial abstract/statements",
        "BaoStock profit snapshot with pubDate cutoff",
    ],
    "social": [
        "Unified sentiment/news tools when available",
        "Data-quality header marks unavailable feeds as unusable",
    ],
}


HEADER_KEYS = (
    "DATA_QUALITY",
    "DATA_SOURCE",
    "DATA_VENDOR",
    "DATA_ROWS",
    "ROWS",
    "DATA_CUTOFF_DATE",
    "CUTOFF_DATE",
    "DATA_WARNING",
    "WARNING",
)

INFERENCE_PATTERNS = (
    ("a-stock-data", "a-stock-data", r"\ba-stock-data\b"),
    ("EastMoney", "东方财富", r"EastMoney|东方财富"),
    ("CNInfo", "巨潮资讯|CNInfo", r"CNInfo|巨潮资讯|巨潮"),
    ("Sina", "新浪|Sina", r"Sina|新浪"),
    ("AkShare", "AkShare", r"AkShare|AKShare"),
    ("BaoStock", "BaoStock", r"BaoStock|baostock|Bao stock"),
    ("Tushare", "Tushare", r"Tushare|TuShare|tushare"),
    ("A股新闻空结果", "A股新闻空结果", r"A股新闻空结果"),
    ("情绪分析API", "情绪分析API", r"情绪分析API"),
)


def _date_from_name(path: Path) -> str | None:
    match = re.search(r"_(20\d{2}-\d{2}-\d{2})\.", path.name)
    return match.group(1) if match else None


def _flatten_text_values(value: Any, prefix: str = "") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(prefix, value)]
    if isinstance(value, dict):
        out: list[tuple[str, str]] = []
        for key, item in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.extend(_flatten_text_values(item, child_prefix))
        return out
    if isinstance(value, list):
        out: list[tuple[str, str]] = []
        for i, item in enumerate(value):
            child_prefix = f"{prefix}[{i}]"
            out.extend(_flatten_text_values(item, child_prefix))
        return out
    return []


def _parse_header_lines(text: str) -> dict[str, str]:
    record: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip().strip("`")
        for key in HEADER_KEYS:
            if not stripped.startswith(f"{key}:"):
                continue
            value = stripped.split(":", 1)[1].strip()
            if key == "DATA_QUALITY":
                match = re.search(r"ok\s*=\s*(true|false)", value, flags=re.I)
                if match:
                    record["ok"] = match.group(1).lower()
                record[key.lower()] = value
            else:
                record[key.lower()] = value
    return record


def _evidence_snippet(text: str, start: int, end: int, window: int = 56) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    return re.sub(r"\s+", " ", text[left:right]).strip()


def _infer_source_mentions(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for data_source, vendor, pattern in INFERENCE_PATTERNS:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        key = (data_source, vendor)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "data_source": data_source,
                "data_vendor": vendor,
                "evidence": _evidence_snippet(text, match.start(), match.end()),
            }
        )
    return rows


def _classify_component(field_path: str, text: str) -> str:
    lowered = f"{field_path}\n{text[:500]}".lower()
    if "market_report" in lowered or "technical" in lowered or "行情" in lowered or "技术" in lowered:
        return "market"
    if "news_report" in lowered or "news" in lowered or "新闻" in lowered or "announcement" in lowered:
        return "news"
    if "fundamentals_report" in lowered or "fundamental" in lowered or "基本面" in lowered or "财务" in lowered:
        return "fundamentals"
    if "sentiment_report" in lowered or "sentiment" in lowered or "social" in lowered or "情绪" in lowered:
        return "social"
    return "unknown"


def _records_from_file(path: Path) -> list[dict[str, Any]]:
    signal_date = _date_from_name(path)
    text_items: list[tuple[str, str]] = []
    if path.suffix == ".json":
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            text_items = _flatten_text_values(obj)
        except Exception as exc:
            return [
                {
                    "source_file": str(path),
                    "signal_date": signal_date,
                    "component": "unknown",
                    "status": "parse_error",
                    "warning": str(exc),
                }
            ]
    else:
        text_items = [("report", path.read_text(encoding="utf-8", errors="ignore"))]

    rows: list[dict[str, Any]] = []
    for field_path, text in text_items:
        headers = _parse_header_lines(text)
        if not headers:
            inferred = _infer_source_mentions(text)
            if not inferred:
                continue
            for item in inferred:
                component = _classify_component(field_path, item["evidence"])
                if component == "unknown":
                    component = _classify_component(field_path, text)
                rows.append(
                    {
                        "source_file": str(path),
                        "signal_date": signal_date,
                        "field_path": field_path,
                        "component": component,
                        "ok": "",
                        "data_quality": "",
                        "data_source": item["data_source"],
                        "data_vendor": item["data_vendor"],
                        "rows": "",
                        "cutoff_date": "",
                        "warning": "Inferred from natural-language artifact text; not a structured tool log.",
                        "status": "inferred",
                        "evidence": item["evidence"],
                    }
                )
            continue
        component = _classify_component(field_path, text)
        rows.append(
            {
                "source_file": str(path),
                "signal_date": signal_date,
                "field_path": field_path,
                "component": component,
                "ok": headers.get("ok", ""),
                "data_quality": headers.get("data_quality", ""),
                "data_source": headers.get("data_source", ""),
                "data_vendor": headers.get("data_vendor", ""),
                "rows": headers.get("data_rows") or headers.get("rows", ""),
                "cutoff_date": headers.get("data_cutoff_date") or headers.get("cutoff_date", ""),
                "warning": headers.get("data_warning") or headers.get("warning", ""),
                "status": "structured",
                "evidence": "",
            }
        )
    if not rows:
        rows.append(
            {
                "source_file": str(path),
                "signal_date": signal_date,
                "component": "unknown",
                "status": "unstructured",
                "warning": "No machine-readable DATA_SOURCE/DATA_VENDOR header found in this artifact.",
                "evidence": "",
            }
        )
    return rows


def audit_data_sources(run_dir: Path, output_dir: Path | None = None) -> dict[str, Any]:
    run_dir = Path(run_dir)
    output_dir = Path(output_dir) if output_dir else run_dir / "data_source_audit"
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(
        list((run_dir / "audit_reports").glob("audit_*.json"))
        + list((run_dir / "reports").glob("report_*.md"))
    )
    rows: list[dict[str, Any]] = []
    for path in files:
        rows.extend(_records_from_file(path))

    details = pd.DataFrame(rows)
    details_path = output_dir / "data_source_audit_details.csv"
    details.to_csv(details_path, index=False)

    structured = details[details["status"].eq("structured")] if not details.empty else pd.DataFrame()
    source_like = details[details["status"].isin(["structured", "inferred"])] if not details.empty else pd.DataFrame()
    if source_like.empty:
        summary = pd.DataFrame(
            [
                {
                    "component": "all",
                    "structured_records": 0,
                    "inferred_records": 0,
                    "ok_records": 0,
                    "sources": "",
                    "vendors": "",
                    "cutoff_dates": "",
                    "warnings": "No structured data-source headers found.",
                }
            ]
        )
    else:
        summary_rows = []
        for component, group in source_like.groupby("component"):
            structured_group = group[group["status"].eq("structured")]
            inferred_group = group[group["status"].eq("inferred")]
            summary_rows.append(
                {
                    "component": component,
                    "structured_records": len(structured_group),
                    "inferred_records": len(inferred_group),
                    "ok_records": int(structured_group["ok"].astype(str).str.lower().eq("true").sum()),
                    "sources": "; ".join(sorted(set(str(x) for x in group["data_source"].dropna() if str(x)))),
                    "vendors": "; ".join(sorted(set(str(x) for x in group["data_vendor"].dropna() if str(x)))),
                    "cutoff_dates": "; ".join(sorted(set(str(x) for x in group["cutoff_date"].dropna() if str(x)))),
                    "warnings": "; ".join(sorted(set(str(x) for x in group["warning"].dropna() if str(x)))),
                }
            )
        summary = pd.DataFrame(summary_rows)

    summary_path = output_dir / "data_source_audit_summary.csv"
    summary.to_csv(summary_path, index=False)

    payload = {
        "schema_version": 1,
        "configured_source_stack": SOURCE_STACK,
        "files_checked": len(files),
        "structured_records": int(len(structured)),
        "inferred_records": int(details["status"].eq("inferred").sum()) if not details.empty else 0,
        "unstructured_records": int(details["status"].eq("unstructured").sum()) if not details.empty else 0,
        "summary_csv": str(summary_path),
        "details_csv": str(details_path),
        "summary": summary.to_dict(orient="records"),
    }
    json_path = output_dir / "data_source_audit.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report_lines = [
        "# Data Source Audit",
        "",
        f"- Run directory: `{run_dir}`",
        f"- Files checked: {len(files)}",
        f"- Structured source records: {payload['structured_records']}",
        f"- Inferred source records: {payload['inferred_records']}",
        f"- Unstructured artifacts: {payload['unstructured_records']}",
        "- Inference rule: inferred records are text mentions in old artifacts, not authoritative tool-call logs.",
        "",
        "## Configured Source Stack",
    ]
    for component, sources in SOURCE_STACK.items():
        report_lines.append(f"- **{component}**: " + "; ".join(sources))
    report_lines.extend(["", "## Extracted Source Summary", ""])
    if summary.empty:
        report_lines.append("No source summary available.")
    else:
        report_lines.append(summary.to_markdown(index=False))
    report_path = output_dir / "data_source_audit.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    payload["report_md"] = str(report_path)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
