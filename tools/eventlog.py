"""Tier 1 Windows Event Log access — registered only when running on Windows.

Half of "why is it down" lives in the Windows Event Log (Application
log errors, crashes, service start failures), not just in app logs.
"""

from __future__ import annotations

import subprocess

from agent.permissions import tier1


@tier1
def get_recent_event_log_errors(hours: int = 24, max_events: int = 20) -> str:
    """Recent ERROR and WARNING events from the Windows 'Application' event log, as JSON."""
    hours = max(1, min(int(hours), 720))
    max_events = max(1, min(int(max_events), 100))
    script = (
        f"$e = Get-WinEvent -FilterHashtable @{{LogName='Application'; Level=2,3; "
        f"StartTime=(Get-Date).AddHours(-{hours})}} -MaxEvents {max_events} -ErrorAction SilentlyContinue "
        f"| Select-Object TimeCreated, ProviderName, Id, LevelDisplayName, Message; "
        f"if ($e) {{ $e | ConvertTo-Json -Depth 2 }} else {{ 'NO_EVENTS' }}"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        return "ERROR: powershell.exe not found (expected on Windows)"
    if result.returncode != 0:
        return f"ERROR: Get-WinEvent failed: {(result.stderr or '').strip()[:300]}"
    stdout = (result.stdout or "").strip()
    if "NO_EVENTS" in stdout:
        return f"No error/warning 'Application' events in the last {hours}h."
    return stdout[:6000]


TOOLS = [get_recent_event_log_errors]