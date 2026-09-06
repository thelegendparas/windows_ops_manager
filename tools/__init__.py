"""Tool registration.

Windows-only tools (services, event log) are registered only when the
agent actually runs on Windows, so the whole project imports and runs
fine on the Mac dev machine — that's how we test it.
"""

from __future__ import annotations

import sys

from agent import permissions


def register_all(agent) -> list[str]:
    """Register every tool on the given Agent; returns the tool names."""
    from tools import eventlog, filesystem, gitops, logs, networking, processes, system

    modules = [system, processes, networking, filesystem, logs, gitops]
    if sys.platform == "win32":
        from tools import windows_services

        modules += [windows_services, eventlog]

    registered = []
    for module in modules:
        for tool in module.TOOLS:
            agent.tool_plain(tool)
            registered.append(tool.__name__)

    # the tier 2 confirmation gate is itself a tool
    agent.tool_plain(permissions.confirm_action)
    registered.append("confirm_action")
    return registered