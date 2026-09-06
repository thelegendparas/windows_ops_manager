"""Process inspection (tier 1) and termination (tier 2, allowlisted)."""

from __future__ import annotations

import os
import time

import psutil

from agent.config import get_settings
from agent.permissions import tier1, tier2
from tools.system import _human_bytes


@tier1
def get_top_processes(n: int = 10) -> str:
    """Top processes ranked by CPU usage with RAM as tiebreaker (samples CPU over ~0.7s)."""
    procs = list(psutil.process_iter())
    for p in procs:
        try:
            p.cpu_percent(interval=None)  # prime the sampler
        except psutil.Error:
            continue
    time.sleep(0.7)
    rows = []
    for p in procs:
        try:
            rows.append((p.cpu_percent(interval=None), p.memory_info().rss, p.pid, p.name()))
        except psutil.Error:
            continue
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    count = max(1, min(int(n), 50))
    lines = [f"{'pid':>7}  {'cpu%':>5}  {'ram':>9}  name"]
    for cpu, rss, pid, name in rows[:count]:
        lines.append(f"{pid:>7}  {cpu:>5.0f}  {_human_bytes(rss):>9}  {name}")
    return "\n".join(lines)


@tier1
def find_processes(name: str, limit: int = 15) -> str:
    """Find running processes whose name contains `name` (case-insensitive): pid, RAM, command line."""
    needle = name.lower()
    rows = []
    for p in psutil.process_iter(["pid", "name", "memory_info", "cmdline"]):
        pname = p.info["name"] or ""
        if needle not in pname.lower():
            continue
        try:
            rss = p.info["memory_info"].rss if p.info["memory_info"] else 0
            cmdline = " ".join(p.info["cmdline"] or [])[:120]
            rows.append(f"pid {p.info['pid']}  {pname}  ram {_human_bytes(rss)}  cmd: {cmdline or '(n/a)'}")
        except psutil.Error:
            continue
        if len(rows) >= max(1, min(int(limit), 100)):
            break
    return "\n".join(rows) if rows else f"no processes matching '{name}'"


def _kill_allowlist(pid: int) -> str | None:
    """Pre-check for kill_process: reject before a proposal is even created."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return f"pid must be an integer, got {pid!r}"
    if pid <= 4:
        return "refusing to kill system/critical processes (pid <= 4)"
    if pid == os.getpid():
        return "refusing to kill the agent's own process"
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return f"no such process pid={pid}"
    allowed = {a.lower() for a in get_settings().allowed_kill_names}
    if proc.name().lower() not in allowed:
        return f"process '{proc.name()}' (pid {pid}) is not in ALLOWED_KILL_NAMES={sorted(allowed)}"


@tier2
def kill_process(pid: int) -> str:
    """Terminate a process by PID. Only names in ALLOWED_KILL_NAMES can be killed. Requires user approval."""
    error = _kill_allowlist(pid)
    if error:
        raise ValueError(error)
    proc = psutil.Process(int(pid))
    name = proc.name()
    proc.terminate()
    try:
        proc.wait(timeout=10)
        outcome = "terminated"
    except psutil.TimeoutExpired:
        outcome = "did not exit within 10s (may still be running)"
    return f"process '{name}' (pid {pid}): {outcome}"


kill_process.allowlist_check = _kill_allowlist  # type: ignore[attr-defined]

TOOLS = [get_top_processes, find_processes, kill_process]