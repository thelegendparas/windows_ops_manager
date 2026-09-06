"""Tier 1 log tools: tail and regex search, with the same security guard as file reads."""

from __future__ import annotations

import re

from agent.permissions import tier1
from tools.filesystem import resolve_path

# only ever read the last 4MB of huge files
_TAIL_READ_LIMIT = 4_000_000


def _read_tail(p) -> tuple[str, int]:
    size = p.stat().st_size
    with p.open("rb") as f:
        if size > _TAIL_READ_LIMIT:
            f.seek(-_TAIL_READ_LIMIT, 2)
        data = f.read()
    return data.decode("utf-8", errors="replace"), size


@tier1
def tail_log(path: str, lines: int = 200) -> str:
    """Show the last N lines of a log/text file (reads at most the final 4MB of huge files)."""
    p = resolve_path(path)
    if not p.exists():
        return f"ERROR: {p} does not exist"
    if not p.is_file():
        return f"ERROR: {p} is not a file"
    text, size = _read_tail(p)
    all_lines = text.splitlines()
    n = max(1, min(int(lines), 1000))
    tail = all_lines[-n:]
    header = f"--- last {len(tail)} lines of {p.name} (file {size} bytes"
    if size > _TAIL_READ_LIMIT:
        header += ", scanned final 4MB only"
    header += ") ---"
    out = "\n".join(tail)
    return header + "\n" + out[:8000]


@tier1
def search_log(path: str, pattern: str, last_lines: int = 2000) -> str:
    """Search the last N lines of a log for a regex `pattern`; returns up to 25 matches with line numbers."""
    p = resolve_path(path)
    if not p.exists():
        return f"ERROR: {p} does not exist"
    if not p.is_file():
        return f"ERROR: {p} is not a file"
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        return f"ERROR: invalid regex: {exc}"
    text, _size = _read_tail(p)
    all_lines = text.splitlines()
    window = all_lines[-max(1, min(int(last_lines), 20000)):]
    offset = len(all_lines) - len(window)
    matches = [
        f"line {offset + i + 1}: {line[:300]}"
        for i, line in enumerate(window)
        if rx.search(line)
    ]
    if not matches:
        return f"no matches for /{pattern}/ in the last {len(window)} lines of {p.name}"
    output = "\n".join(matches[:25])
    if len(matches) > 25:
        output += f"\n... ({len(matches) - 25} more matches)"
    return output


TOOLS = [tail_log, search_log]