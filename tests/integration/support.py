"""Helpers shared by the integration tests."""

from __future__ import annotations

import json
import struct
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from aseprite_mcp.config import find_aseprite

ASEPRITE = find_aseprite()
ASEPRITE_AVAILABLE = ASEPRITE is not None and ASEPRITE.exists()

PALETTE = [
    "#1a1c2c", "#5d275d", "#b13e53", "#ef7d57", "#ffcd75", "#a7f070", "#38b764", "#257179",
    "#29366f", "#3b5dc9", "#41a6f6", "#73eff7", "#f4f4f4", "#94b0c2", "#566c86", "#333c57",
]  # fmt: skip


class Client:
    """Thin wrapper over ClientSession that turns tool results into assertions."""

    def __init__(self, session: ClientSession) -> None:
        self.session = session

    async def call(self, tool: str, **args: Any) -> Any:
        """Call a tool that must succeed; return parsed JSON, or the content for images."""
        result = await self.session.call_tool(tool, args)
        assert not result.is_error, f"{tool} failed: {result.content[0].text}"
        content = result.content[0]
        return json.loads(content.text) if content.type == "text" else content

    async def error(self, tool: str, **args: Any) -> str:
        """Call a tool that must fail; return the error message the model would see."""
        result = await self.session.call_tool(tool, args)
        assert result.is_error, f"{tool} unexpectedly succeeded"
        return result.content[0].text


@asynccontextmanager
async def connect(root: Path, *, allow_lua: bool = False) -> AsyncIterator[Client]:
    """Start the server as a subprocess (exactly as an MCP client would) and connect to it."""
    env = {"ASEPRITE_MCP_ROOTS": str(root), "ASEPRITE_PATH": str(ASEPRITE)}
    if allow_lua:
        env["ASEPRITE_MCP_ALLOW_LUA"] = "1"
    params = StdioServerParameters(command=sys.executable, args=["-m", "aseprite_mcp"], env=env)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield Client(session)


def png_size(data: bytes) -> tuple[int, int]:
    """Read width and height from a PNG header."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG file"
    width, height = struct.unpack(">II", data[16:24])
    return width, height
