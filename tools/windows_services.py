"""Windows service tools — registered only when running on Windows.

Queries are tier 1 (autonomous). start/stop/restart are tier 2 AND
restricted to ALLOWED_SERVICES from .env — both enforced:
- allowlist_check runs before a proposal is even created (fail fast),
- the function body re-checks (defense in depth).

Service control uses `sc.exe`, so start/stop typically needs the agent
to run in an elevated (Administrator) terminal.
"""

from __future__ import annotations

import subprocess
import time

import psutil

from agent.config import get_settings
from agent.permissions import tier1, tier2


def _find_service(name: str) -> str | None:
    """Return the canonical short service name for a fuzzy (short or display) match, or None."""
    needle = name.lower().strip()
    try:
        for svc in psutil.win_service_iter():
            if needle in (svc.name().lower(), (svc.display_name() or "").lower()):
                return svc.name()
    except psutil.Error:
        pass
    return None


def _status(canon: str) -> str:
    try:
        return psutil.win_service_get(canon).status() or "unknown"
    except psutil.NoSuchProcess:
        return "not installed"


def _sc(*args: str) -> str:
    result = subprocess.run(["sc", *args], capture_output=True, text=True, timeout=30)
    return ((result.stdout or "") + (result.stderr or "")).strip()


def _wait_status(canon: str, target: str, timeout_s: int = 30) -> str:
    deadline = time.time() + timeout_s
    status = _status(canon)
    while time.time() < deadline and status != target:
        time.sleep(1.0)
        status = _status(canon)
    return status


def _svc_allowlist(name: str) -> str | None:
    """Pre-check: reject anything not in ALLOWED_SERVICES before creating a proposal."""
    canon = _find_service(name)
    if canon is None:
        return f"no service matching '{name}' found"
    allowed = {a.lower() for a in get_settings().allowed_services}
    if canon.lower() not in allowed:
        return (
            f"service '{canon}' is not in ALLOWED_SERVICES={sorted(allowed)}. "
            "Add it to .env to permit control of this service."
        )
    return None


@tier1
def list_services(name_filter: str = "") -> str:
    """List Windows services (optionally filtered by substring): short name, display name, status, start type."""
    needle = name_filter.lower().strip()
    rows = []
    try:
        iterator = psutil.win_service_iter()
    except psutil.Error as exc:
        return f"ERROR: cannot enumerate services: {exc}"
    for svc in iterator:
        d = svc.as_dict()
        if needle and needle not in d["name"].lower() and needle not in (d["display_name"] or "").lower():
            continue
        rows.append(f"{d['name']}  [{d['display_name']}]  status={d['status']}  start={d['start_type']}")
        if len(rows) >= 60:
            rows.append("... (truncated at 60; use name_filter to narrow)")
            break
    return "\n".join(rows) if rows else f"no services matching '{name_filter}'"


@tier1
def get_service_status(name: str) -> str:
    """Detailed status of one Windows service (short or display name): status, pid, start type, binary path."""
    canon = _find_service(name)
    if canon is None:
        return f"ERROR: no service matching '{name}' found"
    try:
        d = psutil.win_service_get(canon).as_dict()
    except psutil.Error as exc:
        return f"ERROR: cannot query '{canon}': {exc}"
    return (
        f"name        : {d['name']}\n"
        f"display     : {d['display_name']}\n"
        f"status      : {d['status']}\n"
        f"start type  : {d['start_type']}\n"
        f"pid         : {d.get('pid')}\n"
        f"binary      : {d.get('binpath')}\n"
        f"description : {(d.get('description') or '')[:150]}"
    )


@tier2
def start_service(name: str) -> str:
    """Start a Windows service. Only services in ALLOWED_SERVICES can be started. Requires user approval."""
    error = _svc_allowlist(name)
    if error:
        raise ValueError(error)
    canon = _find_service(name) or name
    out = _sc("start", canon)
    final = _wait_status(canon, "running")
    return f"start '{canon}': status now '{final}'. sc output: {out[:200]}"


@tier2
def stop_service(name: str) -> str:
    """Stop a Windows service. Only services in ALLOWED_SERVICES can be stopped. Requires user approval."""
    error = _svc_allowlist(name)
    if error:
        raise ValueError(error)
    canon = _find_service(name) or name
    out = _sc("stop", canon)
    final = _wait_status(canon, "stopped")
    return f"stop '{canon}': status now '{final}'. sc output: {out[:200]}"


@tier2
def restart_service(name: str) -> str:
    """Restart a Windows service (stop, wait, start). Only services in ALLOWED_SERVICES. Requires user approval."""
    error = _svc_allowlist(name)
    if error:
        raise ValueError(error)
    canon = _find_service(name) or name
    _sc("stop", canon)
    _wait_status(canon, "stopped", timeout_s=20)
    _sc("start", canon)
    final = _wait_status(canon, "running")
    return f"restart '{canon}': status now '{final}'"


start_service.allowlist_check = _svc_allowlist  # type: ignore[attr-defined]
stop_service.allowlist_check = _svc_allowlist  # type: ignore[attr-defined]
restart_service.allowlist_check = _svc_allowlist  # type: ignore[attr-defined]

TOOLS = [list_services, get_service_status, start_service, stop_service, restart_service]