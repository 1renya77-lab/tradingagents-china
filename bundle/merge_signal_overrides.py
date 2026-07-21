#!/usr/bin/env python3
"""Merge one or more override signal CSVs into a base signal CSV by date/ticker."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def merge_signal_overrides(base: pd.DataFrame, overrides: list[pd.DataFrame]) -> pd.DataFrame:
    out = base.copy()
    if "date" not in out.columns or "ticker" not in out.columns:
        raise ValueError("base signals must include date and ticker columns")
    out["date"] = out["date"].astype(str)
    out["ticker"] = out["ticker"].astype(str)

    for override in overrides:
        if "date" not in override.columns or "ticker" not in override.columns:
            raise ValueError("override signals must include date and ticker columns")
        cur = override.copy()
        cur["date"] = cur["date"].astype(str)
        cur["ticker"] = cur["ticker"].astype(str)

        for _, row in cur.iterrows():
            mask = (out["date"] == row["date"]) & (out["ticker"] == row["ticker"])
            if mask.any():
                for col in cur.columns:
                    out.loc[mask, col] = row[col]
            else:
                out = pd.concat([out, pd.DataFrame([row])], ignore_index=True)

    if "date" in out.columns:
        out = out.sort_values(["date", "ticker"]).reset_index(drop=True)
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge override signal rows into a base signal CSV.")
    parser.add_argument("--base", required=True)
    parser.add_argument("--override", action="append", required=True, help="Override signal CSV; may be passed multiple times.")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base = pd.read_csv(args.base)
    overrides = [pd.read_csv(path) for path in args.override]
    merged = merge_signal_overrides(base, overrides)
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output, index=False)
    print(f"wrote: {output}")


if __name__ == "__main__":
    main()
