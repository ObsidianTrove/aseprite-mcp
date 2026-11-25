"""Build a small animated scene through the MCP server and save it as a GIF.

Demonstrates driving the server programmatically with the MCP Python client:
create a sprite, draw pixel art with the `rows` op, animate, and preview.

    uv run examples/showcase.py docs/images/showcase.gif
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from aseprite_mcp.aseprite import Aseprite
from aseprite_mcp.config import find_aseprite

PALETTE = [
    "#1a1c2c", "#5d275d", "#b13e53", "#ef7d57", "#ffcd75", "#a7f070", "#38b764", "#257179",
    "#29366f", "#3b5dc9", "#41a6f6", "#73eff7", "#f4f4f4", "#94b0c2", "#566c86", "#333c57",
]  # fmt: skip

SLIME = [
    "......kkkk......",
    "....kkbbbbkk....",
    "...kbbbbbbbbk...",
    "..kbblbbbbbbk...",
    "..kblwbbbwlbbk..",
    "..kbbkbbbkbbbk..",
    ".kbbbbbbbbbbbk..",
    ".kbbbbddddbbbk..",
    ".kdbbbbbbbbbdk..",
    "..kddddddddddk..",
    "...kkkkkkkkkk...",
]
VARIANTS = [  # body, shade, highlight
    ("#38b764", "#257179", "#a7f070"),
    ("#b13e53", "#5d275d", "#ef7d57"),
    ("#3b5dc9", "#29366f", "#73eff7"),
]
WIDTH, HEIGHT, GROUND = 56, 24, 19


def slime_ops(x: int, y: int, body: str, shade: str, light: str) -> dict:
    key = {"k": "#1a1c2c", "b": body, "d": shade, "l": light, "w": "#f4f4f4"}
    return {"op": "rows", "x": x, "y": y, "rows": SLIME, "key": key}


async def build(sprite: Path, root: Path) -> None:
    env = {"ASEPRITE_MCP_ROOTS": str(root)}
    if os.environ.get("ASEPRITE_PATH"):
        env["ASEPRITE_PATH"] = os.environ["ASEPRITE_PATH"]
    params = StdioServerParameters(command=sys.executable, args=["-m", "aseprite_mcp"], env=env)
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()

        async def call(tool: str, **args: object) -> None:
            result = await s.call_tool(tool, args)
            if result.is_error:
                raise RuntimeError(result.content[0].text)

        await call(
            "create_sprite",
            path=str(sprite),
            width=WIDTH,
            height=HEIGHT,
            frames=2,
            palette=PALETTE,
            background="#94b0c2",
            duration_ms=300,
        )
        strip = {"op": "rect", "x": 0, "y": GROUND, "w": WIDTH, "fill": True}
        ground = [
            {**strip, "h": 5, "color": "#566c86"},  # soil
            {**strip, "h": 2, "color": "#38b764"},  # grass
            {**strip, "h": 1, "color": "#a7f070"},  # grass highlight
        ]
        await call("draw", path=str(sprite), frames=[1, 2], ops=ground)
        # Frame 2 squashes each slime down one pixel for a simple idle bounce.
        for frame, dy in ((1, 0), (2, 1)):
            ops = [
                slime_ops(2 + i * 18, GROUND - len(SLIME) + dy, *colors)
                for i, colors in enumerate(VARIANTS)
            ]
            await call("draw", path=str(sprite), frame=frame, ops=ops)
        await call("tag_animation", path=str(sprite), name="idle", from_frame=1, to_frame=2)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "showcase.gif").resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        sprite = root / "showcase.aseprite"
        asyncio.run(build(sprite, root))
        Aseprite(find_aseprite()).run([str(sprite), "--scale", "8", "--save-as", str(out)])
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
