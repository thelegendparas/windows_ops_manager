
"""Tests for the tier 2 proposal/confirmation gate and audit logging.

These run fine on the Mac dev machine — the permission machinery is
platform-independent (that's why it lives in agent/, not tools/).
"""

import re

import agent.permissions as permissions
from agent import audit


def test_tier2_requires_confirmation(tmp_path):
    audit.configure(tmp_path)
    permissions._pending.clear()
    executed = []

    @permissions.tier2
    def restart_bot(name: str) -> str:
        """Restart the bot (test double)."""
        executed.append(name)
        return f"restarted {name}"

    out = restart_bot("MyBot")
    assert executed == [], "tier 2 tool must NOT execute on first call"
    assert "PROPOSAL" in out and "MyBot" in out

    token = re.search(r"token : ([0-9a-f]{12})", out).group(1)
    result = permissions.confirm_action(token)
    assert executed == ["MyBot"]
    assert result == "restarted MyBot"

    # a used token cannot be replayed
    assert permissions.confirm_action(token).startswith("ERROR")


def test_allowlist_check_rejects_before_proposal(tmp_path):
    audit.configure(tmp_path)
    permissions._pending.clear()
    executed = []

    @permissions.tier2
    def restart_svc(name: str) -> str:
        """Restart a service (test double)."""
        executed.append(name)
        return f"restarted {name}"

    restart_svc.allowlist_check = lambda name: (
        None if name == "Allowed" else f"service '{name}' is not in ALLOWED_SERVICES"
    )

    out = restart_svc("NotAllowed")
    assert executed == []
    assert "not allowed" in out
    assert "PROPOSAL" not in out
    assert permissions._pending == {}

    proposal = restart_svc("Allowed")
    assert "PROPOSAL" in proposal


def test_expired_token(tmp_path, monkeypatch):
    audit.configure(tmp_path)
    permissions._pending.clear()

    import time as time_mod

    @permissions.tier2
    def action() -> str:
        """Do something (test double)."""
        return "done"

    out = action()
    token = re.search(r"token : ([0-9a-f]{12})", out).group(1)

    real_time = time_mod.time
    monkeypatch.setattr(time_mod, "time", lambda: real_time() + 9999)
    assert permissions.confirm_action(token).startswith("ERROR")


def test_auto_approve(tmp_path):
    audit.configure(tmp_path)
    permissions._pending.clear()
    permissions.set_auto_approve(True)
    try:

        @permissions.tier2
        def deploy() -> str:
            """Deploy (test double)."""
            return "deployed"

        assert deploy() == "deployed"
    finally:
        permissions.set_auto_approve(False)


def test_tier1_executes_and_audits(tmp_path):
    audit.configure(tmp_path)

    @permissions.tier1
    def read_cpu() -> str:
        """CPU (test double)."""
        return "12%"

    assert read_cpu() == "12%"
    files = list(tmp_path.glob("audit-*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().splitlines()
    assert any('"tool": "read_cpu"' in line for line in lines)
    assert any('"status": "ok"' in line for line in lines)