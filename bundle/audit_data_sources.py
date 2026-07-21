from __future__ import annotations

import argparse
import json
from pathlib import Path

from tradingagents.utils.data_source_audit import audit_data_sources


ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract structured data-source records from run artifacts.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-name", help="Run name under outputs/runs/")
    group.add_argument("--run-dir", help="Explicit run directory")
    parser.add_argument("--output-dir", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = Path(args.run_dir) if args.run_dir else ROOT / "outputs" / "runs" / args.run_name
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    output_dir = Path(args.output_dir) if args.output_dir else run_dir / "data_source_audit"
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    result = audit_data_sources(run_dir, output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
