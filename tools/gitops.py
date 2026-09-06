"""Git tools for APP_DIR: read-only status/log/diff (tier 1) and pull (tier 2)."""

from __future__ import annotations

import subprocess

from agent.config import get_settings
from agent.permissions import tier1, tier2


def _git(*args: str, timeout: int = 120) -> str:
    result = subprocess.run(
        ["git", "-C", str(get_settings().app_dir), *args],
        capture_output=True, text=True, timeout=timeout,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {result.returncode}): {output.strip()[:400]}"
        )
    return output


@tier1
def get_git_status() -> str:
    """Git branch and working-tree status of APP_DIR (porcelain, one line per change)."""
    out = _git("status", "--porcelain=v1", "-b").strip()
    return out[:3000] if out else "clean"


@tier1
def get_recent_commits(max_commits: int = 10) -> str:
    """Recent commit log (one line per commit) for APP_DIR."""
    count = max(1, min(int(max_commits), 50))
    return _git("log", "--oneline", "-n", str(count)).strip()


@tier1
def get_git_diff() -> str:
    """Uncommitted changes in APP_DIR: diffstat plus the first ~2000 chars of the diff."""
    stat = _git("diff", "HEAD", "--stat").strip()
    diff = _git("diff", "HEAD").strip()[:2000]
    return f"diffstat:\n{stat}\n\ndiff (first 2000 chars):\n{diff}"


@tier2
def git_pull() -> str:
    """Run 'git pull --ff-only' in APP_DIR (fast-forward only, no merge commits). Requires user approval."""
    output = _git("pull", "--ff-only").strip()
    head = _git("log", "--oneline", "-n", "1").strip()
    return f"git pull --ff-only:\n{output[:1500]}\n\nnow at: {head}"


TOOLS = [get_git_status, get_recent_commits, get_git_diff, git_pull]