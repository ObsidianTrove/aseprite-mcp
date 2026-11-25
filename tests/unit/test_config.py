import os
from pathlib import Path

import pytest

from aseprite_mcp.config import Settings, find_aseprite, parse_roots


def test_parse_roots_splits_on_pathsep(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    assert parse_roots(f"{a}{os.pathsep}{b}") == [a.resolve(), b.resolve()]


def test_parse_roots_ignores_blank_entries(tmp_path: Path) -> None:
    assert parse_roots(f"{os.pathsep}{tmp_path}{os.pathsep} ") == [tmp_path.resolve()]


def test_parse_roots_defaults_to_home() -> None:
    assert parse_roots("") == [Path.home().resolve()]


def test_aseprite_path_env_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASEPRITE_PATH", "/opt/custom/aseprite")
    assert find_aseprite() == Path("/opt/custom/aseprite")


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ASEPRITE_PATH", str(tmp_path / "aseprite"))
    monkeypatch.setenv("ASEPRITE_MCP_ROOTS", str(tmp_path))
    monkeypatch.setenv("ASEPRITE_TIMEOUT", "30")
    monkeypatch.setenv("ASEPRITE_MCP_ALLOW_LUA", "1")
    s = Settings.from_env()
    assert s.aseprite == tmp_path / "aseprite"
    assert s.roots == [tmp_path.resolve()]
    assert s.timeout == 30
    assert s.allow_lua is True


def test_lua_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASEPRITE_MCP_ALLOW_LUA", raising=False)
    assert Settings.from_env().allow_lua is False
