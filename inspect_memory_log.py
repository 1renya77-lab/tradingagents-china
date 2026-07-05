"""Inspect TradingAgents markdown decision memory."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


bundle_root = Path(__file__).parent
sys.path.insert(0, str(bundle_root))

from tradingagents.agents.utils.memory_log import TradingMemoryLog  # noqa: E402


def _cell(value) -> str:
    text = "n/a" if value in (None, "") else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def format_memory_rows(entries: list[dict]) -> str:
    """Format parsed memory entries as a markdown table."""
    header = (
        "| date | ticker | rating | status | raw | alpha | holding | reflection |\n"
        "|:---|:---|:---|:---|---:|---:|:---:|:---:|"
    )
    rows = [header]
    for entry in entries:
        status = "pending" if entry.get("pending") else "resolved"
        has_reflection = "yes" if entry.get("reflection") else "no"
        rows.append(
            "| "
            + " | ".join(
                [
                    _cell(entry.get("date")),
                    _cell(entry.get("ticker")),
                    _cell(entry.get("rating")),
                    status,
                    _cell(entry.get("raw")),
                    _cell(entry.get("alpha")),
                    _cell(entry.get("holding")),
                    has_reflection,
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect TradingAgents decision memory log.")
    parser.add_argument(
        "--memory-log",
        default=str(bundle_root / "outputs" / "memory" / "decision_memory.md"),
        help="Path to decision_memory.md",
    )
    parser.add_argument("--ticker", default=None, help="Optional ticker filter, e.g. 300269")
    parser.add_argument("--limit", type=int, default=20, help="Show the most recent N entries")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    memory_log = TradingMemoryLog({"memory_log_path": args.memory_log})
    entries = memory_log.load_entries()
    if args.ticker:
        entries = [entry for entry in entries if entry.get("ticker") == args.ticker]
    if args.limit and args.limit > 0:
        entries = entries[-args.limit:]

    if not entries:
        print("No memory entries found.")
        return

    print(format_memory_rows(entries))


if __name__ == "__main__":
    main()
