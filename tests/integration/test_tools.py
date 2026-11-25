"""End-to-end tests of every tool through the MCP protocol."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from .support import ASEPRITE_AVAILABLE, PALETTE, Client, png_size

pytestmark = [
    pytest.mark.integration,
    pytest.mark.anyio,
    pytest.mark.skipif(
        not ASEPRITE_AVAILABLE, reason="Aseprite not found; set ASEPRITE_PATH to run"
    ),
]

SLIME = [
    "......kkkk......",
    "....kkggggkk....",
    "...kggggggggk...",
    "..kgglggggggk...",
    "..kglwgggwlggk..",
    "..kggkgggkgggk..",
    ".kgggggggggggk..",
    ".kggggddddgggk..",
    ".kdgggggggggdk..",
    "..kddddddddddk..",
    "...kkkkkkkkkk...",
]
KEY = {"k": "#1a1c2c", "g": "#38b764", "d": "#257179", "l": "#a7f070", "w": "#f4f4f4"}


async def make_slime(client: Client, path: Path) -> None:
    """Two-frame idle (ping-pong) plus a one-shot hurt frame."""
    await client.call(
        "create_sprite", path=str(path), width=16, height=16, palette=PALETTE, duration_ms=150
    )
    await client.call(
        "draw", path=str(path), ops=[{"op": "rows", "y": 5, "rows": SLIME, "key": KEY}]
    )
    await client.call("add_frames", path=str(path), count=1, copy_from=1)
    await client.call(
        "draw",
        path=str(path),
        frame=2,
        ops=[{"op": "clear"}, {"op": "rows", "y": 6, "rows": SLIME[:-1], "key": KEY}],
    )
    await client.call(
        "tag_animation", path=str(path), name="idle", from_frame=1, to_frame=2, direction="pingpong"
    )
    await client.call("add_frames", path=str(path), count=1, copy_from=1)
    await client.call(
        "tag_animation", path=str(path), name="hurt", from_frame=3, to_frame=3, repeat=1
    )


# ----------------------------------------------------------------------------- discovery


async def test_lists_all_tools_with_safety_annotations(client: Client) -> None:
    tools = {t.name: t for t in (await client.session.list_tools()).tools}
    assert set(tools) == {
        "create_sprite", "sprite_info", "add_layer", "add_frames", "tag_animation", "draw",
        "set_palette", "palette_swap", "import_image", "preview", "export_spritesheet",
        "export_godot_spriteframes", "export_tileset", "batch_export", "placeholder_report",
        "run_lua",
    }  # fmt: skip
    read_only = {name for name, t in tools.items() if t.annotations.read_only_hint}
    assert read_only == {"sprite_info", "preview", "placeholder_report"}


# ----------------------------------------------------------------------------- authoring


async def test_create_sprite_and_describe(client: Client, workspace: Path) -> None:
    path = workspace / "art" / "blank.aseprite"
    info = await client.call(
        "create_sprite", path=str(path), width=32, height=24, frames=3, palette=PALETTE
    )
    assert path.exists()
    assert (info["width"], info["height"]) == (32, 24)
    assert len(info["frames"]) == 3
    assert info["palette"][:2] == PALETTE[:2]
    assert info == await client.call("sprite_info", path=str(path))


async def test_draw_rows_sets_exact_pixels(lua_client: Client, workspace: Path) -> None:
    path = workspace / "dot.aseprite"
    await lua_client.call("create_sprite", path=str(path), width=4, height=4)
    await lua_client.call(
        "draw",
        path=str(path),
        ops=[
            {"op": "rows", "x": 1, "y": 2, "rows": ["ab"], "key": {"a": "#ff0000", "b": "#00ff00"}}
        ],
    )
    pixels = await lua_client.call(
        "run_lua",
        code="""
            local s = app.open(params.path)
            local img = Image(s.width, s.height, s.colorMode)
            img:drawSprite(s, 1)
            local function hex(x, y)
              local c = Color(img:getPixel(x, y))
              return string.format("#%02x%02x%02x%02x", c.red, c.green, c.blue, c.alpha)
            end
            return { hex(1, 2), hex(2, 2), hex(0, 0) }
        """,
        params={"path": str(path)},
    )
    assert pixels == {"result": ["#ff0000ff", "#00ff00ff", "#00000000"]}


async def test_add_frames_does_not_extend_existing_tags(client: Client, workspace: Path) -> None:
    path = workspace / "anim.aseprite"
    await client.call("create_sprite", path=str(path), width=8, height=8, frames=2)
    await client.call("tag_animation", path=str(path), name="idle", from_frame=1, to_frame=2)
    info = await client.call("add_frames", path=str(path), count=2, copy_from=1)
    assert len(info["frames"]) == 4
    assert info["tags"] == [{"name": "idle", "from": 1, "to": 2, "direction": "forward"}]


async def test_add_frames_sets_durations(client: Client, workspace: Path) -> None:
    path = workspace / "timing.aseprite"
    await client.call("create_sprite", path=str(path), width=8, height=8, frames=3)
    info = await client.call(
        "add_frames", path=str(path), duration_ms=250, duration_from=2, duration_to=3
    )
    assert [f["duration_ms"] for f in info["frames"]] == [100, 250, 250]


async def test_add_layer_inside_group(client: Client, workspace: Path) -> None:
    path = workspace / "layers.aseprite"
    await client.call("create_sprite", path=str(path), width=8, height=8)
    await client.call("add_layer", path=str(path), name="Body", group=True)
    info = await client.call("add_layer", path=str(path), name="Outline", parent="Body")
    paths = [layer["path"] for layer in info["layers"]]
    assert "Body/Outline" in paths


async def test_palette_swap_writes_variant(client: Client, workspace: Path) -> None:
    src, variant = workspace / "slime.aseprite", workspace / "slime_red.aseprite"
    await make_slime(client, src)
    result = await client.call(
        "palette_swap",
        path=str(src),
        out_path=str(variant),
        mapping={"#38b764": "#b13e53", "#257179": "#5d275d"},
    )
    assert result["changed"] > 0
    assert variant.exists()


async def test_set_palette_converts_to_indexed(client: Client, workspace: Path) -> None:
    path = workspace / "slime.aseprite"
    await make_slime(client, path)
    info = await client.call("set_palette", path=str(path), colors=PALETTE[:8], to_indexed=True)
    assert info["color_mode"] == "indexed"
    assert info["palette"] == PALETTE[:8]


async def test_import_image_resizes_and_quantizes(client: Client, workspace: Path) -> None:
    slime = workspace / "slime.aseprite"
    await make_slime(client, slime)
    sheet = workspace / "sheet.png"
    await client.call("export_spritesheet", path=str(slime), out_png=str(sheet), padding=0,
                      sheet_type="horizontal", scale=4)  # fmt: skip
    info = await client.call(
        "import_image", src=str(sheet), out_path=str(workspace / "imported.aseprite"),
        height=16, max_colors=8,
    )  # fmt: skip
    assert info["color_mode"] == "indexed"
    assert (info["width"], info["height"]) == (48, 16)


async def test_preview_returns_scaled_png(client: Client, workspace: Path) -> None:
    path = workspace / "slime.aseprite"
    await make_slime(client, path)
    strip = await client.call("preview", path=str(path), scale=4)
    assert strip.mime_type == "image/png"
    assert png_size(base64.b64decode(strip.data)) == (16 * 4 * 3, 16 * 4)
    single = await client.call("preview", path=str(path), frame=2, scale=2)
    assert png_size(base64.b64decode(single.data)) == (32, 32)


# ----------------------------------------------------------------------------- export


async def test_export_spritesheet_with_metadata(client: Client, workspace: Path) -> None:
    path = workspace / "slime.aseprite"
    await make_slime(client, path)
    result = await client.call(
        "export_spritesheet", path=str(path), out_png=str(workspace / "out" / "slime.png"),
        out_json=str(workspace / "out" / "slime.json"),
    )  # fmt: skip
    assert result["frames"] == 3
    assert result["tags"] == ["idle", "hurt"]
    assert png_size((workspace / "out" / "slime.png").read_bytes()) == (
        result["size"]["w"],
        result["size"]["h"],
    )


async def test_export_godot_spriteframes(
    client: Client, workspace: Path, godot_project: Path
) -> None:
    path = workspace / "slime.aseprite"
    await make_slime(client, path)
    result = await client.call(
        "export_godot_spriteframes", path=str(path), godot_project=str(godot_project)
    )
    assert result == {
        "png": "res://assets/sprites/slime.png",
        "spriteframes": "res://assets/sprites/slime.tres",
        "animations": ["idle", "hurt"],
        "placeholder": True,
    }
    folder = godot_project / "assets" / "sprites"
    assert sorted(p.name for p in folder.iterdir()) == ["slime.png", "slime.tres"]
    tres = (folder / "slime.tres").read_text(encoding="utf-8")
    assert tres.count('[sub_resource type="AtlasTexture"') == 3  # one per sprite frame
    # idle: frames 1-2 ping-pong (2 entries); hurt: frame 3 (1 entry)
    assert tres.count('"texture": SubResource(') == 3
    assert tres.count('"loop": true') == 1
    assert tres.count('"loop": false') == 1


async def test_export_tileset_for_godot(
    client: Client, workspace: Path, godot_project: Path
) -> None:
    path = workspace / "tiles.aseprite"
    await client.call("create_sprite", path=str(path), width=48, height=16, palette=PALETTE)
    await client.call("draw", path=str(path), ops=[
        {"op": "rect", "x": 0, "y": 0, "w": 16, "h": 16, "color": "#38b764", "fill": True},
        {"op": "rect", "x": 16, "y": 0, "w": 16, "h": 16, "color": "#566c86", "fill": True},
    ])  # fmt: skip
    png = godot_project / "assets" / "tiles" / "terrain.png"
    info = await client.call(
        "export_tileset", path=str(path), out_png=str(png), tile_w=16, tile_h=16, extrude=1,
        godot_project=str(godot_project),
    )  # fmt: skip
    assert (info["columns"], info["rows"]) == (3, 1)
    assert info["tiles"] == [[0, 0], [1, 0]]  # the third tile is empty
    assert info["tileset"] == "res://assets/tiles/terrain.tres"
    assert png_size(png.read_bytes()) == (3 * 18, 18)
    tres = png.with_suffix(".tres").read_text(encoding="utf-8")
    assert "separation = Vector2i(2, 2)" in tres


async def test_batch_export_reports_failures_per_file(
    client: Client, workspace: Path, godot_project: Path
) -> None:
    art = workspace / "art"
    await make_slime(client, art / "enemies" / "slime.aseprite")
    (art / "broken.aseprite").write_bytes(b"not an aseprite file")
    result = await client.call("batch_export", src_dir=str(art), godot_project=str(godot_project))
    assert result["exported"] == ["res://assets/sprites/enemies/slime.tres"]
    assert list(result["failed"]) == [str(art / "broken.aseprite")]


# ----------------------------------------------------------------------------- placeholders


async def make_final(lua_client: Client, path: Path) -> None:
    """Stand-in for hand-made final art: a sprite saved without the placeholder marker."""
    path.parent.mkdir(parents=True, exist_ok=True)
    await lua_client.call(
        "run_lua",
        code="""
            local s = Sprite(16, 16)
            s:newEmptyFrame()
            s:newTag(1, 2).name = "idle"
            s:saveAs(params.path)
        """,
        params={"path": str(path)},
    )


async def test_everything_written_is_marked(
    client: Client, workspace: Path, godot_project: Path
) -> None:
    slime = workspace / "art" / "placeholder" / "slime.aseprite"
    await make_slime(client, slime)
    assert (await client.call("sprite_info", path=str(slime)))["placeholder"] is True

    variant = workspace / "art" / "placeholder" / "slime_red.aseprite"
    await client.call(
        "palette_swap", path=str(slime), out_path=str(variant), mapping={"#38b764": "#b13e53"}
    )
    sheet_png, sheet_json = workspace / "out" / "slime.png", workspace / "out" / "slime.json"
    sheet = await client.call(
        "export_spritesheet", path=str(slime), out_png=str(sheet_png), out_json=str(sheet_json)
    )
    assert sheet["placeholder"] is True
    imported = await client.call(
        "import_image", src=str(sheet_png), out_path=str(workspace / "imported.aseprite")
    )
    assert imported["placeholder"] is True
    await client.call(
        "export_godot_spriteframes", path=str(slime), godot_project=str(godot_project)
    )
    tiles = await client.call(
        "export_tileset", path=str(slime), out_png=str(godot_project / "tiles" / "t.png"),
        tile_w=8, tile_h=8, godot_project=str(godot_project),
    )  # fmt: skip
    assert tiles["placeholder"] is True

    tres = (godot_project / "assets" / "sprites" / "slime.tres").read_text(encoding="utf-8")
    assert tres.endswith("metadata/placeholder = true\n")
    report = await client.call("placeholder_report", paths=[str(workspace)])
    assert sorted(Path(f["path"]).name for f in report["placeholders"]) == [
        "imported.aseprite", "slime.aseprite", "slime.json", "slime.png", "slime.png",
        "slime.tres", "slime_red.aseprite", "t.png", "t.tres",
    ]  # fmt: skip
    by_kind = {f["kind"]: f for f in report["placeholders"]}
    assert by_kind["Godot SpriteFrames"]["details"] == {
        "animations": ["idle", "hurt"],
        "frame_size": "16x16",
    }
    by_path = {f["path"]: f for f in report["placeholders"]}
    assert by_path[str(slime)]["details"] == {"width": 16, "height": 16, "frames": 3}


async def test_final_art_is_never_modified(lua_client: Client, workspace: Path) -> None:
    final = workspace / "art" / "final" / "hero.aseprite"
    await make_final(lua_client, final)
    before = final.read_bytes()
    assert (await lua_client.call("sprite_info", path=str(final)))["placeholder"] is False

    for tool, args in [
        ("draw", {"ops": [{"op": "clear"}]}),
        ("add_frames", {"count": 1}),
        ("tag_animation", {"name": "walk", "from_frame": 1, "to_frame": 1}),
        ("palette_swap", {"mapping": {"#000000": "#ffffff"}}),
        ("create_sprite", {"width": 8, "height": 8}),
    ]:
        message = await lua_client.error(tool, path=str(final), **args)
        assert "final art" in message, tool
    assert final.read_bytes() == before

    # Deriving a new placeholder from final art is allowed.
    variant = workspace / "art" / "placeholder" / "hero_alt.aseprite"
    await lua_client.call(
        "palette_swap", path=str(final), out_path=str(variant), mapping={"#000000": "#ffffff"}
    )
    assert (await lua_client.call("sprite_info", path=str(variant)))["placeholder"] is True
    assert final.read_bytes() == before


async def test_final_art_replaces_placeholder_in_place(
    lua_client: Client, workspace: Path, godot_project: Path
) -> None:
    placeholders, finals = workspace / "art" / "placeholder", workspace / "art" / "final"
    await make_slime(lua_client, placeholders / "enemies" / "slime.aseprite")
    first = await lua_client.call(
        "batch_export", src_dir=str(placeholders), godot_project=str(godot_project)
    )
    assert first["placeholders"] == ["res://assets/sprites/enemies/slime.tres"]
    exported = godot_project / "assets" / "sprites" / "enemies"
    report = await lua_client.call("placeholder_report", paths=[str(godot_project)])
    assert report["count"] == 2  # slime.png + slime.tres

    # The artist drops final art in at the same relative path and re-exports.
    await make_final(lua_client, finals / "enemies" / "slime.aseprite")
    second = await lua_client.call(
        "batch_export", src_dir=str(finals), godot_project=str(godot_project)
    )
    assert second["exported"] == first["exported"]  # same res:// paths: scenes keep working
    assert second["placeholders"] == []
    assert (await lua_client.call("placeholder_report", paths=[str(godot_project)]))["count"] == 0

    # Re-exporting the placeholders later must not undo the swap.
    third = await lua_client.call(
        "batch_export", src_dir=str(placeholders), godot_project=str(godot_project)
    )
    assert third["exported"] == []
    assert third["kept_final"] == [str(placeholders / "enemies" / "slime.aseprite")]
    assert "metadata/placeholder" not in (exported / "slime.tres").read_text(encoding="utf-8")
    message = await lua_client.error(
        "export_godot_spriteframes", path=str(placeholders / "enemies" / "slime.aseprite"),
        godot_project=str(godot_project), target_dir="assets/sprites/enemies",
    )  # fmt: skip
    assert "will not be replaced by a placeholder export" in message


# ----------------------------------------------------------------------------- errors


async def test_relative_path_is_rejected_with_guidance(client: Client) -> None:
    message = await client.error("sprite_info", path="art/hero.aseprite")
    assert "relative path" in message
    assert "absolute" in message


async def test_path_outside_roots_is_rejected(client: Client, workspace: Path) -> None:
    message = await client.error("sprite_info", path=str(workspace.parent / "elsewhere.aseprite"))
    assert "outside the allowed folders" in message


async def test_lua_errors_reach_the_model(client: Client, workspace: Path) -> None:
    path = workspace / "x.aseprite"
    await client.call("create_sprite", path=str(path), width=8, height=8)
    message = await client.error("draw", path=str(path), ops=[{"op": "spiral"}])
    assert "unknown draw op: spiral" in message


async def test_run_lua_disabled_by_default(client: Client) -> None:
    message = await client.error("run_lua", code="return 1")
    assert "disabled" in message


async def test_godot_export_requires_project(client: Client, workspace: Path) -> None:
    path = workspace / "x.aseprite"
    await client.call("create_sprite", path=str(path), width=8, height=8)
    message = await client.error(
        "export_godot_spriteframes", path=str(path), godot_project=str(workspace)
    )
    assert "not a Godot project" in message


async def test_godot_export_rejects_target_outside_project(
    client: Client, workspace: Path, godot_project: Path
) -> None:
    path = workspace / "x.aseprite"
    await client.call("create_sprite", path=str(path), width=8, height=8)
    message = await client.error(
        "export_godot_spriteframes", path=str(path), godot_project=str(godot_project),
        target_dir="../outside",
    )  # fmt: skip
    assert "must be inside the Godot project" in message
