"""Tier 1 networking: who is listening on which ports."""

from __future__ import annotations

import psutil

from agent.permissions import tier1


@tier1
def get_open_ports() -> str:
    """All listening internet ports: port, protocol, pid, process name.

    Note: on Windows, resolving pid->process name for other users'
    processes may require the agent to run as Administrator.
    """
    seen: dict[tuple[int, str], tuple[int, str]] = {}
    for conn in psutil.net_connections(kind="inet"):
        if conn.laddr is None:
            continue
        is_listening = (
            conn.type == psutil.SOCK_STREAM and conn.status == psutil.CONN_LISTEN
        ) or conn.type == psutil.SOCK_DGRAM
        if not is_listening:
            continue
        proto = "tcp" if conn.type == psutil.SOCK_STREAM else "udp"
        key = (conn.laddr.port, proto)
        if key in seen:
            continue
        pid = conn.pid or 0
        name = "(unknown)"
        if pid:
            try:
                name = psutil.Process(pid).name()
            except psutil.Error:
                name = "(unknown pid)"
        seen[key] = (pid, name)

    lines = [f"{'port':>6} {'proto':<5} {'pid':>7}  process"]
    for (port, proto), (pid, name) in sorted(seen.items()):
        lines.append(f"{port:>6} {proto:<5} {pid:>7}  {name}")
    if len(lines) > 120:
        lines = lines[:120] + ["... (truncated)"]
    lines.append(f"total: {len(seen)} listening sockets")
    return "\n".join(lines)


TOOLS = [get_open_ports]