from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


HEADER_RE = re.compile(r"^(DATA_[A-Z_]+|ROWS|CUTOFF_DATE|TEMPORAL_RULE|WARNING):\s*(.*)$")
TIME_LINE_RE = re.compile(
    r"^(?:-\s*)?(Published|Disclosure Date|publish_time|pubDate|公告日期|发布日期|披露日期):\s*(.+)$",
    flags=re.I,
)
INFER_SOURCE_PATTERNS = (
    ("a-stock-data", "a-stock-data", r"\ba-stock-data\b"),
    ("AkShare", "AkShare", r"AkShare|AKShare"),
    ("BaoStock", "BaoStock", r"BaoStock|baostock|Bao stock"),
    ("EastMoney", "东方财富", r"EastMoney|东方财富"),
    ("CNInfo", "巨潮资讯|CNInfo", r"CNInfo|巨潮资讯|巨潮"),
    ("Sina", "新浪|Sina", r"Sina|新浪"),
)


def _date_from_name(path: Path) -> str | None:
    match = re.search(r"_(20\d{2}-\d{2}-\d{2})\.", path.name)
    return match.group(1) if match else None


def _flatten_strings(value: Any, prefix: str = "") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(prefix, value)]
    if isinstance(value, dict):
        out: list[tuple[str, str]] = []
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            out.extend(_flatten_strings(item, child))
        return out
    if isinstance(value, list):
        out: list[tuple[str, str]] = []
        for i, item in enumerate(value):
            out.extend(_flatten_strings(item, f"{prefix}[{i}]"))
        return out
    return []


def _component_from_field(field_path: str, text: str) -> str:
    lowered = f"{field_path}\n{text[:800]}".lower()
    if "market_report" in lowered or "technical" in lowered or "技术" in lowered:
        return "market"
    if "news_report" in lowered or "news" in lowered or "新闻" in lowered or "announcement" in lowered:
        return "news"
    if "fundamentals_report" in lowered or "fundamental" in lowered or "基本面" in lowered or "财务" in lowered:
        return "fundamentals"
    if "sentiment_report" in lowered or "sentiment" in lowered or "social" in lowered or "情绪" in lowered:
        return "social"
    return "unknown"


def _parse_headers(text: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in text.splitlines():
        match = HEADER_RE.match(line.strip().strip("`"))
        if not match:
            continue
        key, value = match.groups()
        headers[key.lower()] = value.strip()
    if "rows" in headers and "data_rows" not in headers:
        headers["data_rows"] = headers["rows"]
    if "cutoff_date" in headers and "data_cutoff_date" not in headers:
        headers["data_cutoff_date"] = headers["cutoff_date"]
    return headers


def _parse_time_evidence(text: str) -> list[dict[str, str]]:
    evidence = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        match = TIME_LINE_RE.match(line.strip())
        if not match:
            continue
        kind, raw_value = match.groups()
        parsed = pd.to_datetime(raw_value, errors="coerce")
        evidence.append(
            {
                "kind": kind,
                "raw_value": raw_value.strip(),
                "parsed_time": "" if pd.isna(parsed) else pd.Timestamp(parsed).strftime("%Y-%m-%d %H:%M:%S"),
                "line": line_no,
            }
        )
    return evidence


def _infer_sources(text: str) -> list[dict[str, str]]:
    out = []
    seen = set()
    for source, vendor, pattern in INFER_SOURCE_PATTERNS:
        match = re.search(pattern, text, flags=re.I)
        if not match or source in seen:
            continue
        seen.add(source)
        snippet = re.sub(r"\s+", " ", text[max(0, match.start() - 60) : match.end() + 60]).strip()
        out.append({"source": source, "vendor": vendor, "evidence": snippet})
    return out


def _records_from_artifact(path: Path) -> list[dict[str, Any]]:
    signal_date = _date_from_name(path)
    if path.suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return [
                {
                    "source_file": str(path),
                    "signal_date": signal_date,
                    "component": "unknown",
                    "status": "parse_error",
                    "error_message": str(exc),
                }
            ]
        text_items = _flatten_strings(payload)
    else:
        text_items = [("report", path.read_text(encoding="utf-8", errors="ignore"))]

    rows: list[dict[str, Any]] = []
    for field_path, text in text_items:
        headers = _parse_headers(text)
        time_evidence = _parse_time_evidence(text)
        inferred_sources = _infer_sources(text) if not headers else []
        if not headers and not time_evidence and not inferred_sources:
            continue
        component = _component_from_field(field_path, text)
        if headers or time_evidence:
            rows.append(
                {
                    "source_file": str(path),
                    "signal_date": signal_date,
                    "field_path": field_path,
                    "component": component,
                    "status": "structured" if headers else "time_evidence_only",
                    "evidence_level": "tool_header" if headers else "timestamp_line",
                    "ok": headers.get("data_quality", ""),
                    "source": headers.get("data_source", ""),
                    "vendor": headers.get("data_vendor", ""),
                    "rows": headers.get("data_rows", ""),
                    "cutoff_date": headers.get("data_cutoff_date", ""),
                    "retrieved_at": headers.get("data_retrieved_at", ""),
                    "temporal_rule": headers.get("temporal_rule", ""),
                    "warning": headers.get("data_warning") or headers.get("warning", ""),
                    "time_evidence": time_evidence,
                }
            )
        for item in inferred_sources:
            rows.append(
                {
                    "source_file": str(path),
                    "signal_date": signal_date,
                    "field_path": field_path,
                    "component": component,
                    "status": "inferred",
                    "evidence_level": "artifact_text_mention",
                    "ok": "",
                    "source": item["source"],
                    "vendor": item["vendor"],
                    "rows": "",
                    "cutoff_date": "",
                    "retrieved_at": "",
                    "temporal_rule": "",
                    "warning": "Source inferred from final artifact text; not a tool-call log.",
                    "time_evidence": [],
                    "evidence": item["evidence"],
                }
            )
    return rows


def collect_run_provenance(run_dir: Path, output_dir: Path | None = None) -> dict[str, Any]:
    run_dir = Path(run_dir)
    output_dir = Path(output_dir) if output_dir else run_dir / "provenance"
    output_dir.mkdir(parents=True, exist_ok=True)

    artifacts = sorted(
        list((run_dir / "audit_reports").glob("audit_*.json"))
        + list((run_dir / "reports").glob("report_*.md"))
    )
    records: list[dict[str, Any]] = []
    for path in artifacts:
        records.extend(_records_from_artifact(path))

    by_component: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_component.setdefault(str(record.get("component") or "unknown"), []).append(record)

    for component in ["market", "news", "fundamentals", "social", "unknown"]:
        path = output_dir / f"{component}_sources.json"
        path.write_text(
            json.dumps(by_component.get(component, []), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    flat_rows = []
    for record in records:
        flat_rows.append(
            {
                key: value
                for key, value in record.items()
                if key != "time_evidence"
            }
            | {"time_evidence_count": len(record.get("time_evidence") or [])}
        )
    details_path = output_dir / "provenance_details.csv"
    pd.DataFrame(flat_rows).to_csv(details_path, index=False)

    summary_rows = []
    for component, group in sorted(by_component.items()):
        structured = [r for r in group if r.get("status") == "structured"]
        inferred = [r for r in group if r.get("status") == "inferred"]
        sources = sorted({str(r.get("source")) for r in group if r.get("source")})
        vendors = sorted({str(r.get("vendor")) for r in group if r.get("vendor")})
        summary_rows.append(
            {
                "component": component,
                "records": len(group),
                "structured_records": len(structured),
                "inferred_records": len(inferred),
                "time_evidence_records": sum(1 for r in group if r.get("time_evidence")),
                "sources": "; ".join(sources),
                "vendors": "; ".join(vendors),
            }
        )
    summary_path = output_dir / "provenance_summary.csv"
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(summary_path, index=False)

    report_lines = [
        "# Provenance Summary",
        "",
        f"- Run directory: `{run_dir}`",
        f"- Artifacts checked: {len(artifacts)}",
        f"- Provenance records: {len(records)}",
        "",
        "## Component Summary",
        "",
    ]
    report_lines.append(summary.to_markdown(index=False) if not summary.empty else "No provenance records found.")
    report_lines.extend(
        [
            "",
            "## Reading Rule",
            "",
            "- `structured_records` come from machine-readable DATA_* headers in agent input artifacts.",
            "- `inferred_records` are only text mentions in existing artifacts; they are weaker than tool headers.",
            "- `time_evidence_records` count explicit publish/disclosure timestamp lines found in the same artifacts.",
            "- This file records evidence availability; future-information violations are judged by temporal_audit.",
        ]
    )
    report_path = output_dir / "provenance_summary.md"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "run_dir": str(run_dir),
        "artifacts_checked": len(artifacts),
        "records": len(records),
        "details_csv": str(details_path),
        "summary_csv": str(summary_path),
        "summary_md": str(report_path),
        "component_files": {
            component: str(output_dir / f"{component}_sources.json")
            for component in ["market", "news", "fundamentals", "social", "unknown"]
        },
    }
    manifest_path = output_dir / "provenance_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
