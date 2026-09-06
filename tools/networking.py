"""Tier 1 networking: who is listening on which ports."""

from __future__ import annotations

import socket

import psutil

from agent.permissions import tier1

# psutil.SOCK_STREAM is POSIX-only (missing on Windows — found in field
# testing); socket constants have the same values and exist everywhere.
_LISTEN_STATUS = getattr(psutil, "CONN_LISTEN", "LISTEN")


@tier1
def get_open_ports() -> str:
    """All listening internet ports: port, protocol, pid, process name.

    Note: resolving pid->process name for other users' processes may
    require the agent to run as Administrator.
    """
    seen: dict[tuple[int, str], tuple[int, str]] = {}
    for conn in psutil.net_connections(kind="inet"):
        if conn.laddr is None:
            continue
        is_stream = conn.type == socket.SOCK_STREAM
        is_listening = (is_stream and conn.status == _LISTEN_STATUS) or conn.type == socket.SOCK_DGRAM
        if not is_listening:
            continue
        proto = "tcp" if is_stream else "udp"
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