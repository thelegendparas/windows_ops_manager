"""Tier 1 read-only tools: system overview, CPU, memory, disk."""

from __future__ import annotations

import platform
import socket
import time
from datetime import datetime

import psutil

from agent.permissions import tier1


def _human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{int(n)}B" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _human_duration(seconds: float) -> str:
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m {secs}s"


@tier1
def get_system_info() -> str:
    """One-glance host overview: hostname, OS, CPU cores, total RAM, uptime."""
    vm = psutil.virtual_memory()
    boot = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M")
    return (
        f"host      : {socket.gethostname()}\n"
        f"os        : {platform.platform()}\n"
        f"cpu cores : {psutil.cpu_count(logical=True)}\n"
        f"ram total : {_human_bytes(vm.total)}\n"
        f"booted    : {boot} (uptime {_human_duration(time.time() - psutil.boot_time())})"
    )


@tier1
def get_cpu_usage() -> str:
    """Current CPU usage: overall plus per-core percentages, sampled over ~1 second."""
    overall = psutil.cpu_percent(interval=1.0)
    per_core = psutil.cpu_percent(percpu=True)
    lines = [f"cpu overall: {overall:.0f}%"]
    if per_core:
        lines.append("per-core  : " + ", ".join(f"c{i}={v:.0f}%" for i, v in enumerate(per_core)))
    return "\n".join(lines)


@tier1
def get_memory_usage() -> str:
    """RAM usage: used/total/available with percentages, plus swap usage."""
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    return (
        f"ram : {_human_bytes(vm.used)} used / {_human_bytes(vm.total)} total "
        f"({vm.percent}%) | available {_human_bytes(vm.available)}\n"
        f"swap: {_human_bytes(sm.used)} used / {_human_bytes(sm.total)} total ({sm.percent}%)"
    )


@tier1
def get_disk_usage() -> str:
    """Disk usage per local drive, plus the drive holding APP_DIR."""
    from agent.config import get_settings

    seen: set[str] = set()
    lines = []
    for part in psutil.disk_partitions(all=False):
        if part.device in seen:
            continue
        seen.add(part.device)
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        label = part.device or part.mountpoint
        lines.append(
            f"{label} ({part.fstype}): {_human_bytes(usage.used)} used / "
            f"{_human_bytes(usage.total)} total ({usage.percent}%), free {_human_bytes(usage.free)}"
        )
    app_dir = get_settings().app_dir.resolve()
    return "\n".join(lines) + f"\nAPP_DIR: {app_dir}"


TOOLS = [get_system_info, get_cpu_usage, get_memory_usage, get_disk_usage]