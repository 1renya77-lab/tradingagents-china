from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SECRET_KEYS = ("api_key", "token", "secret", "password", "auth")


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if any(secret in str(key).lower() for secret in SECRET_KEYS):
                out[key] = "<redacted>" if item else ""
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def git_snapshot(project_dir: Path) -> dict[str, str]:
    def run_git(args: list[str]) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=project_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    return {
        "commit": run_git(["rev-parse", "HEAD"]),
        "branch": run_git(["branch", "--show-current"]),
        "dirty_status": run_git(["status", "--short"]),
    }


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_collection_manifest(
    *,
    project_dir: Path,
    run_name: str | None,
    ticker: str,
    start_date: str,
    end_date: str,
    frequency: str,
    selected_analysts: list[str],
    config: dict[str, Any],
    signal_path: Path,
    started_at: str,
    ended_at: str,
    rows_total: int,
    rows_ok: int,
    rows_error: int,
    resumed: bool,
    data_sources: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "tradingagents_signal_collection",
        "run_name": run_name,
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "frequency": frequency,
        "selected_analysts": selected_analysts,
        "signal_path": str(signal_path),
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": (
            datetime.fromisoformat(ended_at.replace("Z", ""))
            - datetime.fromisoformat(started_at.replace("Z", ""))
        ).total_seconds(),
        "rows_total": rows_total,
        "rows_ok": rows_ok,
        "rows_error": rows_error,
        "resume": resumed,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "argv": sys.argv,
        "git": git_snapshot(project_dir),
        "config": redact(config),
        "data_sources": data_sources or {},
    }
