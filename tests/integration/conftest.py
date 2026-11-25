"""Integration fixtures. Each test talks to a real server process over MCP stdio, which
drives a real Aseprite installation. The suite is skipped when Aseprite is not found."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from .support import ASEPRITE, Client, connect


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    skip = pytest.mark.skip(reason="Aseprite not found; set ASEPRITE_PATH to run")
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.anyio)
            if ASEPRITE is None or not ASEPRITE.exists():
                item.add_marker(skip)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Per-test folder; the server's only allowed root."""
    return tmp_path.resolve()


@pytest.fixture
def godot_project(workspace: Path) -> Path:
    project = workspace / "game"
    project.mkdir()
    (project / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    return project


@pytest.fixture
async def client(workspace: Path) -> AsyncIterator[Client]:
    async with connect(workspace) as c:
        yield c


@pytest.fixture
async def lua_client(workspace: Path) -> AsyncIterator[Client]:
    """A client whose server has run_lua enabled, used to inspect pixels."""
    async with connect(workspace, allow_lua=True) as c:
        yield c
