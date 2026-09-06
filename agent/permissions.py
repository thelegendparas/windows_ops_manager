"""Permission tiers for agent tools.

Tier 1 (autonomous, read-only): executes immediately, fully audited.
Tier 2 (mutating actions): does NOT execute immediately. Returns a
    PROPOSAL with a confirmation token. The action only runs when the
    user approves and `confirm_action(token)` is called.
Tier 3 (destructive actions: deleting files, dropping data, firewall /
    user changes): intentionally NOT implemented as tools at all.

Headless/automated mode: `set_auto_approve(True)` makes tier 2 tools
execute directly (audited as `auto_approved`). Only enable this for
trusted scripted runs (`--yes`).
"""

from __future__ import annotations

import functools
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from agent import audit
from agent.config import get_settings

_AUTO_APPROVE = False
_MAX_PENDING = 16


@dataclass
class PendingAction:
    token: str
    tool: str
    description: str
    fn: Callable[..., str]
    args: tuple
    kwargs: dict
    created_at: float


_pending: dict[str, PendingAction] = {}


def set_auto_approve(value: bool) -> None:
    """Enable/disable auto-approval of tier 2 actions (headless mode only)."""
    global _AUTO_APPROVE
    _AUTO_APPROVE = value


def _fmt_args(args: tuple, kwargs: dict) -> str:
    rendered = ", ".join([repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()])
    return rendered[:400]


def _execute(fn: Callable[..., str], tool: str, tier: str, args: tuple, kwargs: dict) -> str:
    """Run a tool, audit it, and always return a string (errors included)."""
    started = time.time()
    try:
        result = fn(*args, **kwargs)
        result = result if isinstance(result, str) else str(result)
    except Exception as exc:  # noqa: BLE001 — errors are surfaced to the model as text
        audit.get().record(
            tool=tool, tier=tier, args=_fmt_args(args, kwargs), status="error",
            duration_ms=int((time.time() - started) * 1000), summary=f"ERROR: {exc}"[:300],
        )
        return f"ERROR: {exc}"
    audit.get().record(
        tool=tool, tier=tier, args=_fmt_args(args, kwargs), status="ok",
        duration_ms=int((time.time() - started) * 1000), summary=result[:300],
    )
    return result


def tier1(func: Callable[..., str]) -> Callable[..., str]:
    """Decorator: register a tool as tier 1 (autonomous, read-only)."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        return _execute(func, func.__name__, "tier1", args, kwargs)

    return wrapper


def tier2(func: Callable[..., str]) -> Callable[..., str]:
    """Decorator: register a tool as tier 2 (mutating; requires approval).

    The wrapped tool does NOT run immediately — it returns a proposal
    with a confirmation token, and only runs via `confirm_action(token)`.

    If the decorated function carries an `allowlist_check(*args, **kwargs)`
    attribute (returning an error string or None), it is evaluated
    BEFORE a proposal is created, so disallowed requests fail fast.
    Tools attach it AFTER decoration: `my_tool.allowlist_check = ...`,
    so the wrapper looks it up on itself, not on `func`.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        check: Callable[..., str | None] | None = getattr(wrapper, "allowlist_check", None)
        if check is not None:
            error = check(*args, **kwargs)
            if error:
                audit.get().record(
                    tool=func.__name__, tier="tier2", args=_fmt_args(args, kwargs),
                    status="rejected", summary=error[:300],
                )
                return f"ERROR (not allowed): {error}"

        if _AUTO_APPROVE:
            audit.get().record(
                tool=func.__name__, tier="tier2", args=_fmt_args(args, kwargs),
                status="auto_approved", summary="",
            )
            return _execute(func, func.__name__, "tier2", args, kwargs)

        token = uuid.uuid4().hex[:12]
        if len(_pending) >= _MAX_PENDING:
            oldest = min(_pending.values(), key=lambda p: p.created_at)
            _pending.pop(oldest.token)
        _pending[token] = PendingAction(
            token=token,
            tool=func.__name__,
            description=f"{func.__name__}({_fmt_args(args, kwargs)})",
            fn=func, args=args, kwargs=kwargs, created_at=time.time(),
        )
        ttl = get_settings().confirm_ttl_seconds
        audit.get().record(
            tool=func.__name__, tier="tier2", args=_fmt_args(args, kwargs),
            status="proposal_created", summary="awaiting user approval",
        )
        return (
            "PROPOSAL CREATED (this action has NOT run yet and will not run until the user approves it)\n"
            f"  action: {func.__name__}({_fmt_args(args, kwargs)})\n"
            f"  token : {token}  (expires in {ttl}s)\n"
            "Explain to the user exactly what this will do, then wait for their explicit approval.\n"
            f"If (and only if) the user approves, call confirm_action(token='{token}') to execute it.\n"
            f"Do not call {func.__name__} again — that would create a duplicate proposal."
        )

    return wrapper


def confirm_action(token: str) -> str:
    """Execute a previously proposed tier 2 action. Call only after the user explicitly approved it.

    Args:
        token: The confirmation token from the proposal.
    """
    action = _pending.get(token)
    if action is None:
        return (
            "ERROR: unknown confirmation token. It may have already been executed or expired. "
            "Create a new proposal by calling the original tool again."
        )
    if time.time() - action.created_at > get_settings().confirm_ttl_seconds:
        _pending.pop(token, None)
        return "ERROR: this proposal has expired. Create a new proposal by calling the original tool again."
    _pending.pop(token, None)
    audit.get().record(
        tool="confirm_action", tier="confirm", args=f"token={token}, {action.tool}",
        status="approved", summary=f"executing {action.description}",
    )
    return _execute(action.fn, action.tool, "tier2", action.args, action.kwargs)