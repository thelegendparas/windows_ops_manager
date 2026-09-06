"""Append-only JSONL audit log of every agent action.

Every tool call — successful or not — is recorded with a timestamp, the
tier it belongs to, its arguments and a result summary. This is what
makes the agent trustworthy and debuggable on a production box.
"""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()
_log_dir: Path | None = None


def configure(log_dir: Path | str) -> None:
    """Point the audit log at a directory (called once at startup)."""
    global _log_dir
    _log_dir = Path(log_dir)
    _log_dir.mkdir(parents=True, exist_ok=True)


class _Logger:
    def __init__(self, log_dir: Path) -> None:
        self._log_dir = log_dir

    def record(
        self,
        *,
        tool: str,
        tier: str,
        args: str = "",
        status: str = "",
        duration_ms: int | None = None,
        summary: str = "",
    ) -> None:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "tool": tool,
            "tier": tier,
            "args": args,
            "status": status,
            "duration_ms": duration_ms,
            "summary": summary,
        }
        path = self._log_dir / f"audit-{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with _lock:
            path.open("a", encoding="utf-8").write(json.dumps(event, ensure_ascii=False) + "\n")
        print(f"[audit] {tool} -> {status}", file=sys.stderr)


def get() -> _Logger:
    """Return the logger, configuring a default ./logs dir if needed."""
    global _log_dir
    if _log_dir is None:
        configure(Path("logs"))
    assert _log_dir is not None
    return _Logger(_log_dir)