
"""Windows-side stress/verification runner.

Runs every capability of the ops agent DIRECTLY as Python functions
(no model / API key needed) and verifies:

  A. tier-1 tools execute and return sane output
  B. the secrets guard blocks sensitive paths (real Windows paths)
  C. tier-2 tools REFUSE without allowlists, and create proposals
     WITHOUT executing (the gate must hold)
  D. confirm_action rejects bogus tokens; nothing ever mutates

Safe by construction: read-only tools + rejection/proposal paths only.
No service control, no process kills, no confirmations. Windows-only
sections are skipped on other platforms.

Usage:  uv run python tests/stress_windows.py
Exit code 0 = no FAILs.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import audit, permissions
from agent.config import get_settings
from tools import filesystem as t_fs
from tools import gitops as t_git
from tools import logs as t_logs
from tools import networking as t_net
from tools import processes as t_proc
from tools import system as t_sys

IS_WINDOWS = sys.platform == "win32"
results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str) -> None:
    results.append((name, status, detail))
    mark = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️ ", "SKIP": "⏭️ "}.get(status, "  ")
    print(f"{mark} [{status}] {name}")
    if status != "PASS":
        print(f"      {detail[:160]}")


def run_tool(name: str, fn, *args, expect_error: str | None = None, allow_error: bool = False) -> str:
    """Call a tool wrapper; classify PASS/WARN/FAIL."""
    try:
        out = fn(*args)
    except Exception as exc:  # noqa: BLE001
        record(name, "FAIL", f"uncaught exception: {exc}")
        return ""
    out = out if isinstance(out, str) else str(out)
    if expect_error is not None:
        if expect_error.lower() in out.lower():
            record(name, "PASS", f"refused as expected: {out[:120]}")
        else:
            record(name, "FAIL", f"expected refusal '{expect_error}', got: {out[:120]}")
        return out
    if out.startswith("ERROR"):
        record(name, "WARN" if allow_error else "FAIL", out[:160])
    else:
        record(name, "PASS", out[:120].replace("\n", " | "))
    return out


def main() -> int:
    get_settings.cache_clear()
    audit.configure(get_settings().audit_dir)
    home = Path.home()
    print(f"=== Windows Ops Agent — stress run ===")
    print(f"platform: {sys.platform} | user: {home} | app_dir: {get_settings().app_dir}")
    print(f"allowlists: services={get_settings().allowed_services} kill={get_settings().allowed_kill_names}\n")

    # ---------- A. tier 1: system inspection ----------
    print("--- A. tier 1 read-only tools ---")
    run_tool("get_system_info", t_sys.get_system_info)
    run_tool("get_cpu_usage", t_sys.get_cpu_usage)
    run_tool("get_memory_usage", t_sys.get_memory_usage)
    run_tool("get_disk_usage", t_sys.get_disk_usage)
    run_tool("get_top_processes", t_proc.get_top_processes, 5)
    run_tool("find_processes", t_proc.find_processes, "win" if IS_WINDOWS else "sys", 5)
    run_tool("get_open_ports", t_net.get_open_ports, allow_error=True)
    run_tool("list_dir", t_fs.list_dir, ".")
    run_tool("read_file", t_fs.read_file, "README.md", 200)
    run_tool("get_git_status", t_git.get_git_status, allow_error=True)

    # temp log for tail/search
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False, encoding="utf-8") as f:
        for i in range(1, 101):
            f.write(f"event {i} severity=info\n")
        tmp_log = f.name
    run_tool("tail_log", t_logs.tail_log, tmp_log, 3)
    run_tool("search_log", t_logs.search_log, tmp_log, r"event 9\d")
    Path(tmp_log).unlink(missing_ok=True)

    # ---------- Windows-only tier 1 ----------
    print("\n--- A2. Windows-only tier 1 (services, event log) ---")
    if IS_WINDOWS:
        from tools import eventlog as t_evl
        from tools import windows_services as t_svc

        out = run_tool("list_services", t_svc.list_services, "spooler")
        if "spooler" not in out.lower():
            record("list_services", "WARN", "spooler not found in output (unexpected on Windows)")
        run_tool("get_service_status", t_svc.get_service_status, "spooler")
        run_tool("get_recent_event_log_errors", t_evl.get_recent_event_log_errors, 24, 10, allow_error=True)
    else:
        record("list_services", "SKIP", "not on Windows")
        record("get_service_status", "SKIP", "not on Windows")
        record("get_recent_event_log_errors", "SKIP", "not on Windows")

    # ---------- B. secrets guard (real host paths) ----------
    print("\n--- B. secrets guard must block these ---")
    probes = {
        "read .ssh/config": str(home / ".ssh" / "config"),
        "read id_rsa (fake)": str(home / "id_rsa"),
        "read .env (fake)": str(home / ".env"),
        "read app.pem (fake)": str(home / "app.pem"),
    }
    for label, target in probes.items():
        out = run_tool(label, t_fs.read_file, target, 100, expect_error="blocked")
        if not out.startswith("ERROR"):
            record(label, "FAIL", f"GUARD BYPASSED — got: {out[:120]}")

    # ---------- C. tier 2 gate: refuse / propose / never execute ----------
    print("\n--- C. tier 2 gate ---")
    if IS_WINDOWS:
        from tools import windows_services as t_svc

        run_tool("restart_service(not allowed)", t_svc.restart_service, "spooler",
                 expect_error="not in ALLOWED_SERVICES")
        run_tool("start_service(not allowed)", t_svc.start_service, "spooler",
                 expect_error="not in ALLOWED_SERVICES")
        run_tool("stop_service(not allowed)", t_svc.stop_service, "spooler",
                 expect_error="not in ALLOWED_SERVICES")
    else:
        record("service control rejections", "SKIP", "not on Windows")

    run_tool("kill_process(not allowlisted pid)", t_proc.kill_process, 31337,
             expect_error="not allowed")

    git_status_before = t_git.get_git_status()
    pending_before = len(permissions._pending)
    out = run_tool("git_pull creates proposal", t_git.git_pull, expect_error="PROPOSAL CREATED")
    if "PROPOSAL" in out:
        got_new = len(permissions._pending) > pending_before
        status_unchanged = t_git.get_git_status() == git_status_before
        if got_new and status_unchanged:
            record("git_pull did NOT execute", "PASS", "pending +1, git state unchanged")
        else:
            record("git_pull did NOT execute", "FAIL",
                   f"pending+{len(permissions._pending) - pending_before}, status changed: {not status_unchanged}")
    run_tool("confirm_action(bogus token)", permissions.confirm_action, "deadbeef0000",
             expect_error="unknown confirmation token")

    # ---------- D. summary ----------
    counts = {s: sum(1 for _, st, _ in results if st == s) for s in ("PASS", "FAIL", "WARN", "SKIP")}
    print("\n=== SUMMARY ===")
    print(f"PASS {counts['PASS']} | WARN {counts['WARN']} | FAIL {counts['FAIL']} | SKIP {counts['SKIP']}")
    print(f"audit log: {get_settings().audit_dir}/audit-{time.strftime('%Y-%m-%d')}.jsonl")
    if counts["FAIL"]:
        print("\nFAILURES:")
        for name, st, detail in results:
            if st == "FAIL":
                print(f"  - {name}: {detail}")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())