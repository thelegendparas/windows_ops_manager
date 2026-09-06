"""Tier 1 file access with the security guard.

The guard is the critical part: the agent must never be able to read
secrets (.env, private keys, .ssh, .aws, .gnupg, .git) even though file
reading is "read-only". A read-only tool that can read .env would leak
API keys straight into the model's context and the audit log.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from agent.config import get_settings
from agent.permissions import tier1


def resolve_path(path: str) -> Path:
    """Resolve `path` (relative paths resolve against APP_DIR) and enforce the security policy.

    Raises PermissionError if the path:
    - matches FORBIDDEN_GLOBS (secrets filenames like .env, *.pem, id_rsa*)
    - lives under FORBIDDEN_PATH_PARTS (.ssh, .aws, .gnupg, .git)
    - is outside ALLOWED_ROOTS (when configured)
    """
    settings = get_settings()
    base = Path(settings.app_dir).expanduser()
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = base / p
    p = p.resolve()

    name = p.name.lower()
    for glob in settings.forbidden_globs:
        if fnmatch.fnmatch(name, glob.lower()):
            raise PermissionError(f"'{p.name}' matches blocked pattern '{glob}' (secrets policy)")

    lowered_parts = {part.lower() for part in p.parts}
    for part in settings.forbidden_path_parts:
        if part.lower() in lowered_parts:
            raise PermissionError(f"path is under '{part}', which is blocked (secrets policy)")

    if settings.allowed_roots:
        roots = [Path(r).expanduser().resolve() for r in settings.allowed_roots]
        if not any(_is_within(p, root) for root in roots):
            raise PermissionError("path is outside ALLOWED_ROOTS")
    return p


def _is_within(p: Path, root: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


@tier1
def list_dir(path: str = ".") -> str:
    """List a directory's contents (default APP_DIR). Directories end with '/'."""
    p = resolve_path(path)
    if not p.exists():
        return f"ERROR: {p} does not exist"
    if not p.is_dir():
        return f"ERROR: {p} is not a directory"
    entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    lines = []
    for entry in entries[:200]:
        if entry.is_dir():
            lines.append(f"{entry.name}/")
        else:
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            lines.append(f"{entry.name}  ({size} bytes)")
    if len(entries) > 200:
        lines.append(f"... ({len(entries) - 200} more entries)")
    body = "\n".join(lines) if lines else "(empty)"
    return f"{p}\n{body}"


@tier1
def read_file(path: str, max_bytes: int = 4000) -> str:
    """Read the first `max_bytes` of a text file. Secret files (.env, keys, etc.) are blocked."""
    p = resolve_path(path)
    if not p.exists():
        return f"ERROR: {p} does not exist"
    if p.is_dir():
        return f"ERROR: {p} is a directory; use list_dir"
    limit = max(100, min(int(max_bytes), 20000))
    data = p.open("rb").read(limit + 1)
    total = p.stat().st_size
    text = data[:limit].decode("utf-8", errors="replace")
    note = "" if total <= limit else f"\n[truncated: showing first {limit} of {total} bytes]"
    return text + note


TOOLS = [list_dir, read_file]