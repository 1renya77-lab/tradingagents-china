#!/usr/bin/env python3
"""Patch existing markdown reports so their header matches executable positions."""

from __future__ import annotations

import argparse
from pathlib import Path

from signal_positioning import update_reports_from_position_signals


def main() -> None:
    parser = argparse.ArgumentParser(description="Update report_*.md headers with target_position semantics.")
    parser.add_argument("--signals", required=True, help="Path to a *_position.csv signal file")
    parser.add_argument("--reports-dir", default=None, help="Report directory. Defaults to sibling reports directory")
    args = parser.parse_args()

    count = update_reports_from_position_signals(
        Path(args.signals),
        Path(args.reports_dir) if args.reports_dir else None,
    )
    print(f"updated reports: {count}")


if __name__ == "__main__":
    main()
