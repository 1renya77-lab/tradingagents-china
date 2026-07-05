"""Append-only markdown decision log for TradingAgents."""

from __future__ import annotations

import re
from pathlib import Path

from tradingagents.agents.utils.rating import parse_rating


class TradingMemoryLog:
    """Append-only markdown log of final decisions and outcome reflections."""

    _SEPARATOR = "\n\n<!-- ENTRY_END -->\n\n"
    _DECISION_RE = re.compile(r"DECISION:\n(.*?)(?=\nREFLECTION:|\Z)", re.DOTALL)
    _REFLECTION_RE = re.compile(r"REFLECTION:\n(.*?)$", re.DOTALL)

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self._log_path = None
        if not cfg.get("memory_log_enabled", True):
            return

        path = cfg.get("memory_log_path")
        if path:
            self._log_path = Path(path).expanduser()
            self._log_path.parent.mkdir(parents=True, exist_ok=True)

        self._max_entries = cfg.get("memory_log_max_entries")

    def store_decision(
        self,
        ticker: str,
        trade_date: str,
        final_trade_decision: str,
    ) -> None:
        """Append a pending decision entry without calling the LLM."""
        if not self._log_path:
            return

        if self._log_path.exists():
            raw = self._log_path.read_text(encoding="utf-8")
            for line in raw.splitlines():
                if line.startswith(f"[{trade_date} | {ticker} |") and line.endswith("| pending]"):
                    return

        rating = parse_rating(final_trade_decision)
        tag = f"[{trade_date} | {ticker} | {rating} | pending]"
        entry = f"{tag}\n\nDECISION:\n{final_trade_decision}{self._SEPARATOR}"
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(entry)

    def load_entries(self) -> list[dict]:
        """Parse all entries from the markdown log."""
        if not self._log_path or not self._log_path.exists():
            return []

        text = self._log_path.read_text(encoding="utf-8")
        raw_entries = [e.strip() for e in text.split(self._SEPARATOR) if e.strip()]
        entries = []
        for raw in raw_entries:
            parsed = self._parse_entry(raw)
            if parsed:
                entries.append(parsed)
        return entries

    def get_pending_entries(self) -> list[dict]:
        return [e for e in self.load_entries() if e.get("pending")]

    def get_past_context(self, ticker: str, n_same: int = 5, n_cross: int = 3) -> str:
        """Return compact prior lessons for prompt injection."""
        entries = [e for e in self.load_entries() if not e.get("pending")]
        if not entries:
            return ""

        same, cross = [], []
        for entry in reversed(entries):
            if len(same) >= n_same and len(cross) >= n_cross:
                break
            if entry["ticker"] == ticker and len(same) < n_same:
                same.append(entry)
            elif entry["ticker"] != ticker and len(cross) < n_cross:
                cross.append(entry)

        if not same and not cross:
            return ""

        parts = []
        if same:
            parts.append(f"Past analyses of {ticker} (most recent first):")
            parts.extend(self._format_full(e) for e in same)
        if cross:
            parts.append("Recent cross-ticker lessons:")
            parts.extend(self._format_reflection_only(e) for e in cross)
        return "\n\n".join(parts)

    def update_with_outcome(
        self,
        ticker: str,
        trade_date: str,
        raw_return: float,
        alpha_return: float,
        holding_days: int,
        reflection: str,
    ) -> None:
        self.batch_update_with_outcomes([
            {
                "ticker": ticker,
                "trade_date": trade_date,
                "raw_return": raw_return,
                "alpha_return": alpha_return,
                "holding_days": holding_days,
                "reflection": reflection,
            }
        ])

    def batch_update_with_outcomes(self, updates: list[dict]) -> None:
        """Resolve pending entries with known outcomes using an atomic rewrite."""
        if not self._log_path or not self._log_path.exists() or not updates:
            return

        text = self._log_path.read_text(encoding="utf-8")
        blocks = text.split(self._SEPARATOR)
        update_map = {(u["trade_date"], u["ticker"]): u for u in updates}

        new_blocks = []
        for block in blocks:
            stripped = block.strip()
            if not stripped:
                new_blocks.append(block)
                continue

            lines = stripped.splitlines()
            tag_line = lines[0].strip()
            matched = False

            for (trade_date, ticker), update in list(update_map.items()):
                pending_prefix = f"[{trade_date} | {ticker} |"
                if tag_line.startswith(pending_prefix) and tag_line.endswith("| pending]"):
                    fields = [f.strip() for f in tag_line[1:-1].split("|")]
                    rating = fields[2]
                    raw_pct = f"{update['raw_return']:+.1%}"
                    alpha_pct = f"{update['alpha_return']:+.1%}"
                    new_tag = (
                        f"[{trade_date} | {ticker} | {rating}"
                        f" | {raw_pct} | {alpha_pct} | {update['holding_days']}d]"
                    )
                    rest = "\n".join(lines[1:])
                    new_blocks.append(
                        f"{new_tag}\n\n{rest.lstrip()}\n\nREFLECTION:\n{update['reflection']}"
                    )
                    del update_map[(trade_date, ticker)]
                    matched = True
                    break

            if not matched:
                new_blocks.append(block)

        new_blocks = self._apply_rotation(new_blocks)
        new_text = self._SEPARATOR.join(new_blocks)
        tmp_path = self._log_path.with_suffix(".tmp")
        tmp_path.write_text(new_text, encoding="utf-8")
        tmp_path.replace(self._log_path)

    def _apply_rotation(self, blocks: list[str]) -> list[str]:
        if not self._max_entries or self._max_entries <= 0:
            return blocks

        tagged = []
        for block in blocks:
            stripped = block.strip()
            if not stripped:
                tagged.append((block, False))
                continue
            tag_line = stripped.splitlines()[0].strip()
            is_resolved = (
                tag_line.startswith("[")
                and tag_line.endswith("]")
                and not tag_line.endswith("| pending]")
            )
            tagged.append((block, is_resolved))

        resolved_count = sum(1 for _, is_resolved in tagged if is_resolved)
        if resolved_count <= self._max_entries:
            return blocks

        to_drop = resolved_count - self._max_entries
        kept = []
        for block, is_resolved in tagged:
            if is_resolved and to_drop > 0:
                to_drop -= 1
                continue
            kept.append(block)
        return kept

    def _parse_entry(self, raw: str) -> dict | None:
        lines = raw.strip().splitlines()
        if not lines:
            return None

        tag_line = lines[0].strip()
        if not (tag_line.startswith("[") and tag_line.endswith("]")):
            return None

        fields = [f.strip() for f in tag_line[1:-1].split("|")]
        if len(fields) < 4:
            return None

        body = "\n".join(lines[1:]).strip()
        decision_match = self._DECISION_RE.search(body)
        reflection_match = self._REFLECTION_RE.search(body)
        return {
            "date": fields[0],
            "ticker": fields[1],
            "rating": fields[2],
            "pending": fields[3] == "pending",
            "raw": fields[3] if fields[3] != "pending" else None,
            "alpha": fields[4] if len(fields) > 4 else None,
            "holding": fields[5] if len(fields) > 5 else None,
            "decision": decision_match.group(1).strip() if decision_match else "",
            "reflection": reflection_match.group(1).strip() if reflection_match else "",
        }

    def _format_full(self, entry: dict) -> str:
        tag = (
            f"[{entry['date']} | {entry['ticker']} | {entry['rating']}"
            f" | {entry['raw'] or 'n/a'} | {entry['alpha'] or 'n/a'}"
            f" | {entry['holding'] or 'n/a'}]"
        )
        parts = [tag, f"DECISION:\n{entry['decision']}"]
        if entry["reflection"]:
            parts.append(f"REFLECTION:\n{entry['reflection']}")
        return "\n\n".join(parts)

    def _format_reflection_only(self, entry: dict) -> str:
        tag = f"[{entry['date']} | {entry['ticker']} | {entry['rating']} | {entry['raw'] or 'n/a'}]"
        if entry["reflection"]:
            return f"{tag}\n{entry['reflection']}"
        text = entry["decision"][:300]
        suffix = "..." if len(entry["decision"]) > 300 else ""
        return f"{tag}\n{text}{suffix}"
