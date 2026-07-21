"""Helpers for resolving experiment artifact paths."""

from __future__ import annotations

import re
from pathlib import Path


def sanitize_run_name(run_name: str | None) -> str:
    """Return a filesystem-safe experiment run name."""
    if not run_name:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(run_name).strip())
    return cleaned.strip("._-")


def resolve_artifact_dir(project_dir: str | Path, dirname: str, run_name: str | None = None) -> Path:
    """Resolve an output directory, optionally isolated under outputs/runs."""
    base_dir = Path(project_dir).resolve()
    safe_run_name = sanitize_run_name(run_name)
    if safe_run_name:
        return base_dir / "outputs" / "runs" / safe_run_name / dirname
    return base_dir / "outputs" / dirname
