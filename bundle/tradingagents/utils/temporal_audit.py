from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


DATE_RE = re.compile(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})")
AUDITED_LINE_PATTERNS = (
    "CUTOFF_DATE",
    "Published:",
    "Disclosure Date:",
    "披露",
    "公告日期",
    "发布日期",
    "publish_time",
    "pubDate",
)
IGNORE_LINE_PATTERNS = (
    "Retrieved on",
    "报告生成时间",
    "generated_at",
    "Generated at",
)
MISSING_TIMESTAMP_PATTERNS = (
    "undated rows are excluded",
    "无明确发布时间",
    "缺少发布时间",
    "missing publish_time",
    "without publish_time",
    "not disclosure_date",
    "report_period_only",
)
TEMPORAL_RULE_PATTERNS = (
    "TEMPORAL_RULE",
    "Temporal rule",
    "时间戳审计",
    "only publish_time/disclosure_date <= cutoff",
    "only rows with explicit disclosure/report date <= cutoff",
)


def _date_from_name(path: Path) -> str | None:
    match = re.search(r"_(20\d{2}-\d{2}-\d{2})\.", path.name)
    return match.group(1) if match else None


def _parse_dates_from_line(line: str) -> list[pd.Timestamp]:
    out = []
    for year, month, day in DATE_RE.findall(line):
        parsed = pd.to_datetime(f"{year}-{int(month):02d}-{int(day):02d}", errors="coerce")
        if not pd.isna(parsed):
            out.append(parsed)
    return out


def _scan_text_for_temporal_issues(text: str, signal_date: str, source_file: Path) -> list[dict[str, Any]]:
    cutoff = pd.to_datetime(signal_date)
    issues: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if any(token in line for token in IGNORE_LINE_PATTERNS):
            continue
        if not any(token in line for token in AUDITED_LINE_PATTERNS):
            continue
        for parsed in _parse_dates_from_line(line):
            if parsed > cutoff:
                issues.append(
                    {
                        "source_file": str(source_file),
                        "signal_date": signal_date,
                        "line": line_no,
                        "issue": "future_timestamp",
                        "found_date": parsed.strftime("%Y-%m-%d"),
                        "evidence": line.strip()[:500],
                    }
                )
    return issues


def _scan_text_for_temporal_stats(text: str) -> dict[str, int]:
    missing_timestamp = 0
    temporal_rule = 0
    for line in text.splitlines():
        if any(token in line for token in MISSING_TIMESTAMP_PATTERNS):
            missing_timestamp += 1
        if any(token in line for token in TEMPORAL_RULE_PATTERNS):
            temporal_rule += 1
    return {
        "missing_timestamp_mentions": missing_timestamp,
        "temporal_rule_mentions": temporal_rule,
    }


def _flatten_text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_flatten_text_values(item))
        return out
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_flatten_text_values(item))
        return out
    return []


def audit_temporal_integrity(run_dir: Path, output_dir: Path | None = None) -> dict[str, Any]:
    run_dir = Path(run_dir)
    output_dir = Path(output_dir) if output_dir else run_dir / "temporal_audit"
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    issue_rows: list[dict[str, Any]] = []
    files = sorted(
        list((run_dir / "audit_reports").glob("audit_*.json"))
        + list((run_dir / "reports").glob("report_*.md"))
    )
    for path in files:
        signal_date = _date_from_name(path)
        if not signal_date:
            continue
        text_parts: list[str]
        if path.suffix == ".json":
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
                text_parts = _flatten_text_values(obj)
            except Exception as exc:
                rows.append(
                    {
                        "source_file": str(path),
                        "signal_date": signal_date,
                        "status": "error",
                        "issue_count": 1,
                        "notes": f"json parse failed: {exc}",
                    }
                )
                continue
        else:
            text_parts = [path.read_text(encoding="utf-8", errors="ignore")]

        issues: list[dict[str, Any]] = []
        stats = {"missing_timestamp_mentions": 0, "temporal_rule_mentions": 0}
        for text in text_parts:
            issues.extend(_scan_text_for_temporal_issues(text, signal_date, path))
            text_stats = _scan_text_for_temporal_stats(text)
            stats["missing_timestamp_mentions"] += text_stats["missing_timestamp_mentions"]
            stats["temporal_rule_mentions"] += text_stats["temporal_rule_mentions"]
        issue_rows.extend(issues)
        rows.append(
            {
                "source_file": str(path),
                "signal_date": signal_date,
                "status": "pass" if not issues else "fail",
                "issue_count": len(issues),
                "missing_timestamp_mentions": stats["missing_timestamp_mentions"],
                "temporal_rule_mentions": stats["temporal_rule_mentions"],
                "notes": "",
            }
        )

    summary = pd.DataFrame(rows)
    details = pd.DataFrame(issue_rows)
    summary_path = output_dir / "temporal_audit_summary.csv"
    details_path = output_dir / "temporal_audit_details.csv"
    summary.to_csv(summary_path, index=False)
    details.to_csv(details_path, index=False)

    total_files = len(summary)
    failed_files = int(summary["status"].eq("fail").sum()) if not summary.empty else 0
    issue_count = len(details)
    missing_timestamp_mentions = (
        int(summary["missing_timestamp_mentions"].fillna(0).sum()) if not summary.empty else 0
    )
    temporal_rule_mentions = (
        int(summary["temporal_rule_mentions"].fillna(0).sum()) if not summary.empty else 0
    )
    verdict = "pass" if issue_count == 0 else "fail"
    report = [
        "# Temporal Integrity Audit",
        "",
        f"- Run directory: `{run_dir}`",
        f"- Files checked: {total_files}",
        f"- Files with future timestamp issues: {failed_files}",
        f"- Total issues: {issue_count}",
        f"- Missing timestamp / undated-data mentions: {missing_timestamp_mentions}",
        f"- Temporal rule mentions: {temporal_rule_mentions}",
        f"- Verdict: **{verdict.upper()}**",
        "",
        "Rule: audited evidence lines such as `Published`, `Disclosure Date`, `CUTOFF_DATE`, `公告日期`, `发布日期`, `publish_time`, and `pubDate` must not be later than the signal date.",
        "Data without explicit publish/disclosure time should be excluded before entering prompts; this audit records explicit missing-time mentions but cannot reconstruct filtered rows unless provenance logs are present.",
    ]
    if issue_count:
        report.extend(["", "## Issues", ""])
        for _, row in details.head(50).iterrows():
            report.append(
                f"- `{row['signal_date']}` {row['source_file']}:{row['line']} "
                f"found `{row['found_date']}` -> {row['evidence']}"
            )
    report_path = output_dir / "temporal_audit.md"
    report_path.write_text("\n".join(report), encoding="utf-8")

    return {
        "verdict": verdict,
        "files_checked": total_files,
        "issue_count": issue_count,
        "missing_timestamp_mentions": missing_timestamp_mentions,
        "temporal_rule_mentions": temporal_rule_mentions,
        "summary_csv": str(summary_path),
        "details_csv": str(details_path),
        "report_md": str(report_path),
    }
