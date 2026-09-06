
"""Configuration loaded from environment / .env (see env.example).

List fields accept either JSON (["a", "b"]) or plain comma-separated
values (a, b) — NoDecode + a validator handles both, so Windows paths
in .env stay human-readable (no backslash escaping needed).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Filenames the agent must never be able to read, whatever the path.
DEFAULT_FORBIDDEN_GLOBS = [
    ".env", ".env.*", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "id_ecdsa*",
    "*secret*", "*credential*", ".git-credentials", "*.pfx", "*.ppk",
    "*.kdbx", "authorized_keys*", "known_hosts*", "wallet.dat",
]

# Path segments that mark a directory tree as off-limits.
DEFAULT_FORBIDDEN_PATH_PARTS = [".ssh", ".aws", ".gnupg", ".git"]


def _parse_list(value: object) -> object:
    """Accept JSON arrays or comma-separated strings for list settings."""
    if not isinstance(value, str):
        return value
    value = value.strip()
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in value.split(",") if item.strip()]


CSVList = Annotated[list[str], NoDecode, BeforeValidator(_parse_list)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False,
    )

    # ---- model ----
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    model_name: str = "z-ai/glm-4.6"

    # ---- agent scope ----
    app_dir: Path = Path.cwd()  # the app/repo this agent operates on
    audit_dir: Path = Path("logs")
    confirm_ttl_seconds: int = 300

    # ---- security ----
    forbidden_globs: CSVList = DEFAULT_FORBIDDEN_GLOBS
    forbidden_path_parts: CSVList = DEFAULT_FORBIDDEN_PATH_PARTS
    allowed_roots: CSVList = []      # empty = any path except the blocklist
    allowed_services: CSVList = []    # Windows services the agent may control
    allowed_kill_names: CSVList = []  # process names the agent may kill


@lru_cache
def get_settings() -> Settings:
    return Settings()