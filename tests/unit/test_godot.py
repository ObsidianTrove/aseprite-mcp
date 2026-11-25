from pathlib import Path

import pytest

from aseprite_mcp import godot


def _sheet(durations: list[int], tags: list[dict] | None = None) -> dict:
    frames = [
        {"frame": {"x": i * 17 + 1, "y": 1, "w": 16, "h": 16}, "duration": d}
        for i, d in enumerate(durations)
    ]
    meta: dict = {"size": {"w": 17 * len(durations) + 1, "h": 18}}
    if tags is not None:
        meta["frameTags"] = tags
    return {"frames": frames, "meta": meta}


@pytest.mark.parametrize(
    ("direction", "expected"),
    [
        ("forward", [0, 1, 2]),
        ("reverse", [2, 1, 0]),
        ("pingpong", [0, 1, 2, 1]),
        ("pingpong_reverse", [2, 1, 0, 1]),
    ],
)
def test_frame_order(direction: str, expected: list[int]) -> None:
    assert godot.frame_order(0, 2, direction) == expected


def test_frame_order_single_frame_pingpong() -> None:
    assert godot.frame_order(3, 3, "pingpong") == [3]


def test_spriteframes_without_tags_has_default_animation() -> None:
    text, names = godot.spriteframes_tres(_sheet([100, 100]), "res://hero.png")
    assert names == ["default"]
    assert '[gd_resource type="SpriteFrames" load_steps=4 format=3]' in text
    assert 'path="res://hero.png"' in text
    assert "region = Rect2(1, 1, 16, 16)" in text
    assert "region = Rect2(18, 1, 16, 16)" in text


def test_spriteframes_preserves_relative_frame_timing() -> None:
    tags = [{"name": "walk", "from": 0, "to": 2, "direction": "forward"}]
    text, _ = godot.spriteframes_tres(_sheet([100, 200, 100], tags), "res://a.png")
    # Base duration is the shortest frame (100 ms) -> 10 FPS; the 200 ms frame counts double.
    assert '"speed": 10' in text
    assert text.count('"duration": 1,') == 2
    assert text.count('"duration": 2,') == 1


def test_spriteframes_loop_flag_follows_repeat() -> None:
    tags = [
        {"name": "idle", "from": 0, "to": 1, "direction": "forward"},
        {"name": "hurt", "from": 2, "to": 2, "direction": "forward", "repeat": "1"},
    ]
    text, names = godot.spriteframes_tres(_sheet([100, 100, 100], tags), "res://a.png")
    assert names == ["idle", "hurt"]
    # Each animation's "loop" key precedes its "name" key.
    idle_block, hurt_block = text.split('"name": &"idle"')
    assert '"loop": true' in idle_block
    assert '"loop": false' in hurt_block


def test_spriteframes_escapes_animation_names() -> None:
    tags = [{"name": 'say "hi"', "from": 0, "to": 0, "direction": "forward"}]
    text, _ = godot.spriteframes_tres(_sheet([100], tags), "res://a.png")
    assert '"name": &"say \\"hi\\""' in text


def test_tileset_tres_matches_extrusion() -> None:
    text = godot.tileset_tres("res://tiles.png", (16, 16), 1, [(0, 0), (2, 1)])
    assert "margins = Vector2i(1, 1)" in text
    assert "separation = Vector2i(2, 2)" in text
    assert "texture_region_size = Vector2i(16, 16)" in text
    assert "tile_size = Vector2i(16, 16)" in text
    assert "0:0/0 = 0" in text
    assert "2:1/0 = 0" in text


def test_res_path(tmp_path: Path) -> None:
    assert godot.res_path(tmp_path, tmp_path / "assets" / "a.png") == "res://assets/a.png"
    with pytest.raises(ValueError, match="not inside the Godot project"):
        godot.res_path(tmp_path / "game", tmp_path / "elsewhere.png")


def test_project_root_requires_project_godot(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a Godot project"):
        godot.project_root(tmp_path)
    (tmp_path / "project.godot").write_text("config_version=5\n")
    assert godot.project_root(tmp_path) == tmp_path
