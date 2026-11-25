"""MCP server exposing Aseprite as tools for creating and exporting placeholder game assets.

Every tool call runs a separate headless Aseprite process (`aseprite -b`), so the server
never interferes with an editor window the user has open.

Everything the server writes is marked as an AI-generated placeholder, and final
(unmarked) art is never modified or overwritten; see placeholder.py.

Configuration (environment variables):
    ASEPRITE_PATH           Aseprite executable (auto-detected when unset)
    ASEPRITE_MCP_ROOTS      Folders the server may read/write, separated by os.pathsep
                            (';' on Windows, ':' elsewhere). Defaults to the home folder.
    ASEPRITE_MCP_ALLOW_LUA  Set to 1 to enable the run_lua tool
    ASEPRITE_TIMEOUT        Seconds before an Aseprite invocation is aborted (default 120)
"""

from __future__ import annotations

import functools
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, TypeVar

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from aseprite_mcp import godot, placeholder
from aseprite_mcp.aseprite import Aseprite
from aseprite_mcp.config import Settings
from aseprite_mcp.paths import resolve, resolve_output

settings = Settings.from_env()
aseprite = Aseprite(settings.aseprite, settings.timeout)

mcp = MCPServer(
    "aseprite",
    instructions=(
        "Tools for building placeholder pixel-art game assets with Aseprite and exporting them "
        "to Godot 4. Every file these tools write is marked as an AI-generated placeholder, to "
        "be replaced by final art before release; final (unmarked) art is never modified or "
        "overwritten. Keep placeholder sources under art/placeholder/ in the game project, at "
        "the same relative path the final source will use under art/final/, and export with "
        "stable names so final art can later replace each file in place. "
        "Frames are 1-based. Colors are '#rrggbb' or '#rrggbbaa'. All paths must be absolute "
        f"and inside: {', '.join(map(str, settings.roots))}. "
        "Typical flow: create_sprite -> draw (the 'rows' op suits pixel art) -> add_frames / "
        "tag_animation -> preview to check the result -> export_godot_spriteframes or "
        "export_tileset. placeholder_report lists what still needs final art."
    ),
)

Direction = Literal["forward", "reverse", "pingpong", "pingpong_reverse"]
Dithering = Literal["none", "ordered", "old"]
F = TypeVar("F", bound=Callable[..., Any])


def tool(*, read_only: bool = False, idempotent: bool = False) -> Callable[[F], F]:
    """Register an MCP tool.

    Exceptions are re-raised as ToolError so their message reaches the model, which lets
    it correct the call; otherwise the SDK reports only a generic failure. The annotations
    tell clients which tools are safe to run without asking the user.
    """

    def register(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except ToolError:
                raise
            except Exception as e:
                raise ToolError(f"{type(e).__name__}: {e}") from e

        annotations = ToolAnnotations(
            read_only_hint=read_only,
            destructive_hint=None if read_only else True,
            idempotent_hint=read_only or idempotent,
            open_world_hint=False,
        )
        mcp.tool(annotations=annotations)(wrapper)
        return fn

    return register


def _in(raw: str) -> str:
    """A file the tool only reads."""
    return str(resolve(raw, settings.roots, must_exist=True))


def _edit(raw: str) -> str:
    """An existing sprite the tool modifies in place; it must be a placeholder."""
    return str(placeholder.require_placeholder(resolve(raw, settings.roots, must_exist=True)))


def _new(raw: str) -> str:
    """A sprite the tool creates; it may only replace an existing placeholder."""
    return str(placeholder.require_placeholder(resolve_output(raw, settings.roots)))


def _out(raw: str) -> str:
    """An export target; see placeholder.guard_export."""
    return str(resolve_output(raw, settings.roots))


def _godot_project(raw: str) -> Path:
    return godot.project_root(resolve(raw, settings.roots, must_exist=True))


# --------------------------------------------------------------------------- authoring


@tool()
def create_sprite(
    path: str,
    width: int,
    height: int,
    frames: int = 1,
    color_mode: Literal["rgb", "indexed", "gray"] = "rgb",
    palette: list[str] | None = None,
    background: str | None = None,
    duration_ms: int = 100,
    layer_name: str = "Layer 1",
) -> dict:
    """Create a new .aseprite file, marked as an AI-generated placeholder.

    `palette` is a list of '#rrggbb' colors; using one fixed palette keeps an asset set
    consistent. `background` fills the first layer; omit it for a transparent sprite.
    """
    return aseprite.lua(
        "create_sprite", path=_new(path), width=width, height=height, frames=frames,
        color_mode=color_mode, palette=palette, background=background,
        duration_ms=duration_ms, layer_name=layer_name,
    )  # fmt: skip


@tool(read_only=True)
def sprite_info(path: str) -> dict:
    """Describe a sprite: size, color mode, whether it is a placeholder, frames (1-based,
    with durations), layers (bottom to top), animation tags and palette."""
    return aseprite.lua("sprite_info", path=_in(path))


@tool()
def add_layer(path: str, name: str, group: bool = False, parent: str | None = None) -> dict:
    """Add a layer (or a layer group when group=True) on top. `parent` places it inside an
    existing group."""
    return aseprite.lua("add_layer", path=_edit(path), name=name, group=group, parent=parent)


@tool()
def add_frames(
    path: str,
    count: int = 0,
    copy_from: int | None = None,
    duration_ms: int | None = None,
    duration_from: int | None = None,
    duration_to: int | None = None,
) -> dict:
    """Append `count` frames, either empty or copied from frame `copy_from`.

    Copying a frame and then editing the copy is the simplest way to animate. Optionally
    sets `duration_ms` on frames duration_from..duration_to (default: all frames); use
    count=0 to change durations only. Existing animation tags are left unchanged.
    """
    return aseprite.lua(
        "add_frames", path=_edit(path), count=count, copy_from=copy_from,
        duration_ms=duration_ms, duration_from=duration_from, duration_to=duration_to,
    )  # fmt: skip


@tool()
def tag_animation(
    path: str,
    name: str,
    from_frame: int,
    to_frame: int,
    direction: Direction = "forward",
    repeat: int = 0,
) -> dict:
    """Tag a frame range as a named animation such as 'idle', 'walk' or 'attack'.

    Tag names become animation names in Godot. repeat=0 loops forever; a positive value
    makes the animation play through and stop. A tag with the same name is replaced.
    """
    return aseprite.lua(
        "tag_animation", path=_edit(path), name=name, from_frame=from_frame,
        to_frame=to_frame, direction=direction, repeat=repeat,
    )  # fmt: skip


@tool()
def draw(
    path: str,
    ops: list[dict[str, Any]],
    layer: str | None = None,
    frame: int = 1,
    frames: list[int] | None = None,
) -> dict:
    """Draw on a layer (default: the topmost image layer) at `frame`, or on every frame
    listed in `frames`. Ops are applied in order; colors are '#rrggbb' or '#rrggbbaa'.

      {"op":"rows","x":0,"y":0,"rows":["..kk..",".kssk."],"key":{"k":"#1a1c2c","s":"#f4b41b"}}
          Pixel-art grid: one character per pixel, '.' or ' ' leaves the pixel unchanged.
          Best suited to sprites.
      {"op":"pixels","points":[[x,y],...],"color":"#ffffff"}  or points [[x,y,"#rrggbb"],...]
      {"op":"rect","x":0,"y":0,"w":8,"h":8,"color":"#000000","fill":true}
      {"op":"line","x1":0,"y1":0,"x2":7,"y2":7,"color":"#000000"}
      {"op":"circle","cx":8,"cy":8,"r":4,"color":"#000000","fill":false}
      {"op":"clear"}  or  {"op":"clear","color":"#00000000"}
    """
    return aseprite.lua("draw", path=_edit(path), ops=ops, layer=layer, frame=frame, frames=frames)


@tool()
def set_palette(
    path: str,
    colors: list[str] | None = None,
    palette_file: str | None = None,
    to_indexed: bool = False,
    dithering: Dithering = "none",
) -> dict:
    """Replace the palette from a list of hex colors or a palette file (.gpl, .pal, .png,
    .aseprite). With to_indexed=True the sprite is converted to indexed mode and every
    pixel snaps to its nearest palette color."""
    return aseprite.lua(
        "set_palette", path=_edit(path), colors=colors,
        palette_file=_in(palette_file) if palette_file else None,
        to_indexed=to_indexed, dithering=dithering,
    )  # fmt: skip


@tool()
def palette_swap(path: str, mapping: dict[str, str], out_path: str | None = None) -> dict:
    """Recolor exact colors across all layers and frames, e.g. {"#38b764": "#b13e53"}.
    Writes to `out_path`, or overwrites the source when omitted. Useful for character
    variants, team colors and seasonal tilesets. The result is a placeholder; a final-art
    source can be recolored only into a new `out_path`."""
    return aseprite.lua(
        "palette_swap", path=_in(path) if out_path else _edit(path), mapping=mapping,
        out_path=_new(out_path) if out_path else None,
    )  # fmt: skip


@tool()
def import_image(
    src: str,
    out_path: str,
    width: int | None = None,
    height: int | None = None,
    colors: list[str] | None = None,
    max_colors: int | None = None,
    dithering: Dithering = "none",
) -> dict:
    """Import a PNG, JPG or GIF as an .aseprite file.

    Resizes with nearest-neighbor sampling (give only width or height to keep the aspect
    ratio), then snaps to a fixed palette (`colors`) or quantizes to `max_colors`. The new
    file is marked as a placeholder.
    """
    return aseprite.lua(
        "import_image", src=_in(src), out_path=_new(out_path), width=width, height=height,
        colors=colors, max_colors=max_colors, dithering=dithering,
    )  # fmt: skip


@tool(read_only=True)
def preview(path: str, frame: int | None = None, scale: int = 8) -> Image:
    """Render the sprite as a PNG image. frame=None shows all frames side by side.
    Use it after drawing to check the result."""
    src = Path(_in(path))
    with tempfile.TemporaryDirectory(prefix="aseprite-mcp-") as tmp:
        png = Path(tmp) / "preview.png"
        aseprite.export_sheet(
            src, png, sheet_type="horizontal", scale=scale, padding=0, frame=frame
        )
        return Image(data=png.read_bytes(), format="png")


# --------------------------------------------------------------------------- export


@tool(idempotent=True)
def export_spritesheet(
    path: str,
    out_png: str,
    out_json: str | None = None,
    sheet_type: Literal["packed", "horizontal", "vertical", "rows", "columns"] = "packed",
    tag: str | None = None,
    layer: str | None = None,
    scale: int = 1,
    padding: int = 1,
    trim: bool = False,
    columns: int | None = None,
) -> dict:
    """Export a sprite sheet PNG, plus optional Aseprite JSON (frame rectangles, durations,
    tags). Filter by `tag` or `layer`. Keep scale=1 for Godot and scale the viewport
    instead. Exports of a placeholder sprite are marked as placeholders too."""
    src = Path(_in(path))
    png = Path(_out(out_png))
    data = Path(_out(out_json)) if out_json else None
    is_placeholder = placeholder.is_placeholder(src)
    placeholder.guard_export([png, *([data] if data else [])], is_placeholder)
    sheet = aseprite.export_sheet(
        src, png, data, sheet_type=sheet_type, tag=tag, layer=layer,
        scale=scale, padding=padding, trim=trim, columns=columns,
    )  # fmt: skip
    if is_placeholder:
        for file in (png, data):
            if file:
                placeholder.mark(file)
    result: dict[str, Any] = {"png": str(png), "placeholder": is_placeholder}
    if sheet:
        result.update(
            json=str(data),
            frames=len(sheet["frames"]),
            size=sheet["meta"]["size"],
            tags=[t["name"] for t in sheet["meta"].get("frameTags", [])],
        )
    return result


def _export_spriteframes(src: Path, project: Path, target_dir: str, name: str, padding: int):
    folder = (project / target_dir).resolve()
    if not folder.is_relative_to(project.resolve()):
        raise ValueError(f"target_dir '{target_dir}' must be inside the Godot project")
    if Path(name).name != name:
        raise ValueError(f"name '{name}' must be a plain file name without folders")
    png, tres = folder / f"{name}.png", folder / f"{name}.tres"
    is_placeholder = placeholder.is_placeholder(src)
    placeholder.guard_export([png, tres], is_placeholder)
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aseprite-mcp-") as tmp:
        sheet = aseprite.export_sheet(src, png, Path(tmp) / "sheet.json", padding=padding)
    if is_placeholder:
        placeholder.mark(png)
    text, animations = godot.spriteframes_tres(
        sheet, godot.res_path(project, png), placeholder=is_placeholder
    )
    tres.write_text(text, encoding="utf-8")
    return {
        "png": godot.res_path(project, png),
        "spriteframes": godot.res_path(project, tres),
        "animations": animations,
        "placeholder": is_placeholder,
    }


@tool(idempotent=True)
def export_godot_spriteframes(
    path: str,
    godot_project: str,
    target_dir: str = "assets/sprites",
    name: str | None = None,
    padding: int = 1,
) -> dict:
    """Export a sprite into a Godot 4 project as <name>.png plus <name>.tres (SpriteFrames).

    Each Aseprite tag becomes an animation with per-frame timing preserved; reverse and
    ping-pong directions are baked into the frame order, and tags with a repeat count do
    not loop. Assign the .tres to an AnimatedSprite2D.

    Exports of a placeholder sprite are marked as placeholders. Final art exported later
    with the same `target_dir` and `name` replaces them in place, so scenes keep working;
    a placeholder export never overwrites a final one.
    """
    src = Path(_in(path))
    return _export_spriteframes(
        src, _godot_project(godot_project), target_dir, name or src.stem, padding
    )


@tool(idempotent=True)
def export_tileset(
    path: str,
    out_png: str,
    tile_w: int | None = None,
    tile_h: int | None = None,
    layer: str | None = None,
    frame: int = 1,
    extrude: int = 1,
    columns: int | None = None,
    godot_project: str | None = None,
) -> dict:
    """Export a tileset PNG with `extrude` pixels of edge padding around each tile, which
    prevents seams when tiles are scaled.

    The source is a tilemap layer's tileset (pass `layer`), or the flattened `frame`
    sliced into a tile_w x tile_h grid. When `godot_project` is given, `out_png` must be
    inside it and a matching TileSet .tres is written next to the PNG. Exports of a
    placeholder sprite are marked as placeholders too.
    """
    src = Path(_in(path))
    png = Path(_out(out_png))
    project = _godot_project(godot_project) if godot_project else None
    tres = png.with_suffix(".tres")
    is_placeholder = placeholder.is_placeholder(src)
    placeholder.guard_export([png, *([tres] if project else [])], is_placeholder)
    info = aseprite.lua(
        "export_tileset", path=str(src), out_png=str(png), tile_w=tile_w, tile_h=tile_h,
        layer=layer, frame=frame, extrude=extrude, columns=columns,
    )  # fmt: skip
    if is_placeholder:
        placeholder.mark(png)
    info["placeholder"] = is_placeholder
    if project:
        tres.write_text(
            godot.tileset_tres(
                godot.res_path(project, png),
                (info["tile_w"], info["tile_h"]),
                info["extrude"],
                [tuple(t) for t in info["tiles"]],
                placeholder=is_placeholder,
            ),
            encoding="utf-8",
        )
        info["tileset"] = godot.res_path(project, tres)
    return info


@tool(idempotent=True)
def batch_export(src_dir: str, godot_project: str, target_dir: str = "assets/sprites") -> dict:
    """Re-export every .aseprite/.ase file under `src_dir` (recursively) into the Godot
    project as SpriteFrames, mirroring the folder structure. Failures are reported per
    file without stopping the batch.

    Run it on art/final/ to drop final art in over the placeholders. A placeholder whose
    export already holds final art is listed under `kept_final` instead of overwriting it."""
    root = Path(_in(src_dir))
    project = _godot_project(godot_project)
    exported: list[str] = []
    placeholders: list[str] = []
    kept_final: list[str] = []
    failed: dict[str, str] = {}
    for file in sorted([*root.rglob("*.aseprite"), *root.rglob("*.ase")]):
        subdir = Path(target_dir) / file.parent.relative_to(root)
        try:
            result = _export_spriteframes(file, project, str(subdir), file.stem, padding=1)
        except placeholder.FinalArtError:
            kept_final.append(str(file))
        except Exception as e:
            failed[str(file)] = f"{type(e).__name__}: {e}"
        else:
            exported.append(result["spriteframes"])
            if result["placeholder"]:
                placeholders.append(result["spriteframes"])
    return {
        "exported": exported,
        "placeholders": placeholders,
        "kept_final": kept_final,
        "failed": failed,
    }


@tool(read_only=True)
def placeholder_report(paths: list[str]) -> dict:
    """List every AI-generated placeholder under the given files or folders: .aseprite
    sources, PNGs, Godot .tres resources and sprite sheet JSON. Each entry includes the
    sizes and animation names a final replacement must match. Point it at a game project
    to see what still needs final art before release."""
    return placeholder.report([Path(_in(p)) for p in paths])


@tool()
def run_lua(code: str, params: dict[str, Any] | None = None) -> dict:
    """Run arbitrary Aseprite Lua. Disabled unless ASEPRITE_MCP_ALLOW_LUA=1.

    `code` is the body of `function(params)` and may return a JSON-serializable value,
    which is returned as {"result": value}. Files saved by this code are NOT marked as
    placeholders automatically; set sprite.properties.aseprite_mcp_placeholder = true.
    The full Aseprite scripting API is available: https://aseprite.org/api
    """
    if not settings.allow_lua:
        raise PermissionError(
            "run_lua is disabled. Set ASEPRITE_MCP_ALLOW_LUA=1 in the MCP server configuration."
        )
    with tempfile.TemporaryDirectory(prefix="aseprite-mcp-") as tmp:
        script = Path(tmp) / "run_lua.lua"
        script.write_text(
            f"local C = dofile(app.params.lib)\nC.run(function(params)\n{code}\nend)\n",
            encoding="utf-8",
        )
        return {"result": aseprite.lua(script, **(params or {}))}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
