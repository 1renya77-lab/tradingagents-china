from __future__ import annotations

from datetime import datetime


def data_quality_header(
    *,
    ok: bool,
    source: str,
    rows: int = 0,
    cutoff_date: str | None = None,
    warning: str | None = None,
) -> str:
    """Render a compact, machine-readable quality header for LLM inputs."""
    status = "true" if ok else "false"
    lines = [
        f"DATA_QUALITY: ok={status}",
        f"DATA_SOURCE: {source}",
        f"DATA_ROWS: {max(0, int(rows or 0))}",
        f"DATA_CUTOFF_DATE: {cutoff_date or 'N/A'}",
        f"DATA_RETRIEVED_AT: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    if warning:
        lines.append(f"DATA_WARNING: {warning}")
    if not ok:
        lines.append("DATA_USAGE_RULE: Treat this feed as unavailable. Do not infer missing values or fabricate facts from it.")
    return "\n".join(lines)
