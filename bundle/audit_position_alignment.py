from __future__ import annotations

import argparse
import json
from pathlib import Path

from tradingagents.utils.position_alignment import audit_position_alignment


ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit signal target_position against Qlib actual positions.")
    parser.add_argument("--signals", required=True, help="signals_*.csv with target_position")
    parser.add_argument("--positions", required=True, help="Qlib positions CSV")
    parser.add_argument("--output-dir", default="outputs/audits/position_alignment_manual")
    parser.add_argument("--ticker", default=None)
    parser.add_argument("--tolerance-pct-point", type=float, default=2.0)
    return parser.parse_args()


def resolve(path: str) -> Path:
    out = Path(path)
    return out if out.is_absolute() else ROOT / out


def main() -> None:
    args = parse_args()
    result = audit_position_alignment(
        signals_path=resolve(args.signals),
        positions_path=resolve(args.positions),
        output_dir=resolve(args.output_dir),
        tolerance_pct_point=args.tolerance_pct_point,
        ticker=args.ticker,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
