"""Generation of Godot 4 text resources (.tres) from Aseprite export data."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def project_root(path: Path) -> Path:
    """Validate that `path` is a Godot project folder and return it."""
    if not (path / "project.godot").is_file():
        raise ValueError(f"{path} is not a Godot project (no project.godot found)")
    return path


def res_path(project: Path, file: Path) -> str:
    """Convert a file inside `project` to a `res://` path."""
    try:
        return "res://" + file.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        raise ValueError(f"{file} is not inside the Godot project {project}") from None


def _num(x: float) -> str:
    return f"{x:.6g}"


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def frame_order(start: int, end: int, direction: str) -> list[int]:
    """0-based frame indices for one playthrough of a tag, with direction baked in."""
    idx = list(range(start, end + 1))
    if direction == "reverse":
        return idx[::-1]
    if direction == "pingpong":
        return idx + idx[-2:0:-1]
    if direction == "pingpong_reverse":
        rev = idx[::-1]
        return rev + rev[-2:0:-1]
    return idx


def spriteframes_tres(sheet: dict[str, Any], texture: str) -> tuple[str, list[str]]:
    """Build a SpriteFrames resource from Aseprite `--format json-array` sheet data.

    Every tag becomes an animation (or a single `default` animation if there are no tags).
    Godot plays an animation at `speed` FPS and scales each frame by its relative
    `duration`, so per-frame timing from Aseprite is preserved exactly. Tags with a repeat
    count are exported as non-looping.

    Returns the resource text and the list of animation names.
    """
    frames = sheet["frames"]
    tags = sheet["meta"].get("frameTags") or [
        {"name": "default", "from": 0, "to": len(frames) - 1, "direction": "forward"}
    ]

    atlas = [
        f'[sub_resource type="AtlasTexture" id="f{i}"]\n'
        'atlas = ExtResource("1")\n'
        f"region = Rect2({f['frame']['x']}, {f['frame']['y']}, {f['frame']['w']}, "
        f"{f['frame']['h']})\n"
        for i, f in enumerate(frames)
    ]

    animations, names = [], []
    for tag in tags:
        order = frame_order(tag["from"], tag["to"], tag.get("direction", "forward"))
        base_ms = min(frames[i]["duration"] for i in order) or 100
        loops = tag.get("repeat") in (None, "", "0", 0)
        entries = ", ".join(
            "{\n"
            f'"duration": {_num(frames[i]["duration"] / base_ms)},\n'
            f'"texture": SubResource("f{i}")\n'
            "}"
            for i in order
        )
        animations.append(
            "{\n"
            f'"frames": [{entries}],\n'
            f'"loop": {"true" if loops else "false"},\n'
            f'"name": &"{_escape(tag["name"])}",\n'
            f'"speed": {_num(1000 / base_ms)}\n'
            "}"
        )
        names.append(tag["name"])

    text = (
        f'[gd_resource type="SpriteFrames" load_steps={len(frames) + 2} format=3]\n\n'
        f'[ext_resource type="Texture2D" path="{_escape(texture)}" id="1"]\n\n'
        + "\n".join(atlas)
        + "\n[resource]\nanimations = ["
        + ", ".join(animations)
        + "]\n"
    )
    return text, names


def tileset_tres(
    texture: str,
    tile_size: tuple[int, int],
    extrude: int,
    tiles: list[tuple[int, int]],
) -> str:
    """Build a TileSet with one atlas source whose margins/separation match the extrusion."""
    tw, th = tile_size
    e = extrude
    cells = "\n".join(f"{x}:{y}/0 = 0" for x, y in tiles)
    return (
        '[gd_resource type="TileSet" load_steps=3 format=3]\n\n'
        f'[ext_resource type="Texture2D" path="{_escape(texture)}" id="1"]\n\n'
        '[sub_resource type="TileSetAtlasSource" id="atlas"]\n'
        'texture = ExtResource("1")\n'
        f"margins = Vector2i({e}, {e})\n"
        f"separation = Vector2i({2 * e}, {2 * e})\n"
        f"texture_region_size = Vector2i({tw}, {th})\n"
        f"{cells}\n\n"
        "[resource]\n"
        f"tile_size = Vector2i({tw}, {th})\n"
        'sources/0 = SubResource("atlas")\n'
    )
