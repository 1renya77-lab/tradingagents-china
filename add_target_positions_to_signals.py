#!/usr/bin/env python3
"""Add executable target_position values to an existing TradingAgents signal CSV."""

from __future__ import annotations

import argparse
from pathlib import Path

from signal_positioning import add_target_positions


def main() -> None:
    parser = argparse.ArgumentParser(description="Derive target_position from existing TradingAgents outputs.")
    parser.add_argument("--signals", required=True, help="Path to signals_*.csv")
    parser.add_argument("--output", default=None, help="Output CSV path. Defaults to *_position.csv")
    parser.add_argument("--audit-dir", default=None, help="Directory containing audit_*.json files")
    args = parser.parse_args()

    output = add_target_positions(
        signals_path=Path(args.signals),
        output_path=Path(args.output) if args.output else None,
        audit_dir=Path(args.audit_dir) if args.audit_dir else None,
    )
    print(f"wrote: {output}")


if __name__ == "__main__":
    main()
