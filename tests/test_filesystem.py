"""Tests for the path security guard (secrets must be unreadable) and log tools."""

from pathlib import Path

import pytest

from agent.config import get_settings


@pytest.fixture()
def fresh_settings():
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


def test_guard_blocks_secret_files(tmp_path, fresh_settings):
    from tools.filesystem import resolve_path

    blocked = [".env", "id_rsa", "server.pem", "app.key", "app.secret", "credentials.json"]
    for name in blocked:
        f = tmp_path / name
        f.write_text("SHOULD_NOT_LEAK")
        with pytest.raises(PermissionError):
            resolve_path(str(f))

    ok_file = tmp_path / "app.log"
    ok_file.write_text("hello")
    assert resolve_path(str(ok_file)) == ok_file.resolve()


def test_guard_blocks_sensitive_directories(tmp_path, fresh_settings):
    from tools.filesystem import resolve_path

    for d in (".ssh", ".aws", ".gnupg"):
        f = tmp_path / d / "config"
        f.parent.mkdir()
        f.write_text("x")
        with pytest.raises(PermissionError):
            resolve_path(str(f))


def test_allowed_roots(tmp_path, fresh_settings, monkeypatch):
    from tools.filesystem import resolve_path

    inside = tmp_path / "inside"
    inside.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    monkeypatch.setenv("ALLOWED_ROOTS", str(inside))
    get_settings.cache_clear()

    with pytest.raises(PermissionError):
        resolve_path(str(outside))
    ok = inside / "log.txt"
    ok.write_text("x")
    assert resolve_path(str(ok)) == ok.resolve()


def test_relative_paths_resolve_against_app_dir(tmp_path, fresh_settings, monkeypatch):
    from tools.filesystem import resolve_path

    monkeypatch.setenv("APP_DIR", str(tmp_path))
    get_settings.cache_clear()

    f = tmp_path / "logs" / "bot.log"
    f.parent.mkdir()
    f.write_text("x")

    assert resolve_path("logs/bot.log") == f.resolve()


def test_tail_log_and_search_log(tmp_path, fresh_settings):
    from agent import audit

    audit.configure(tmp_path / "audit")
    from tools.logs import search_log, tail_log

    f = tmp_path / "app.log"
    f.write_text("\n".join(f"line {i}" for i in range(1, 51)))

    out = tail_log(str(f), lines=3)
    assert "line 50" in out and "line 49" in out and "line 48" in out
    assert "line 47" not in out

    found = search_log(str(f), r"line 4\d")
    assert "line 49" in found
    assert "line 50" not in found