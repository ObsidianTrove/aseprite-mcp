import json
import struct
import zlib
from pathlib import Path

import pytest

from aseprite_mcp import godot, placeholder


def _png(path: Path, width: int = 4, height: int = 3) -> Path:
    """Write a minimal valid RGBA PNG."""

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload))
        )

    raw = b"".join(b"\0" + b"\0" * 4 * width for _ in range(height))
    data = (
        placeholder.PNG_SIGNATURE
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(data)
    return path


def _crc_ok(data: bytes) -> bool:
    for kind, payload, _start, end in placeholder._png_chunks(data):
        (crc,) = struct.unpack(">I", data[end - 4 : end])
        if crc != zlib.crc32(kind + payload):
            return False
    return True


def test_mark_png_adds_valid_text_chunk_after_ihdr(tmp_path: Path) -> None:
    png = _png(tmp_path / "a.png")
    assert not placeholder.is_placeholder(png)
    placeholder.mark_png(png)
    data = png.read_bytes()
    kinds = [k for k, *_ in placeholder._png_chunks(data)]
    assert kinds == [b"IHDR", b"tEXt", b"IDAT", b"IEND"]
    assert _crc_ok(data)
    assert placeholder.is_placeholder(png)


def test_mark_png_is_idempotent(tmp_path: Path) -> None:
    png = _png(tmp_path / "a.png")
    placeholder.mark_png(png)
    once = png.read_bytes()
    placeholder.mark_png(png)
    assert png.read_bytes() == once


def test_replacing_a_png_removes_the_marker(tmp_path: Path) -> None:
    png = _png(tmp_path / "a.png")
    placeholder.mark_png(png)
    _png(png)  # final art dropped in at the same path
    assert not placeholder.is_placeholder(png)


def test_json_marker(tmp_path: Path) -> None:
    sheet = tmp_path / "a.json"
    sheet.write_text(json.dumps({"frames": [], "meta": {"app": "aseprite"}}))
    assert not placeholder.is_placeholder(sheet)
    placeholder.mark_json(sheet)
    assert json.loads(sheet.read_text())["meta"] == {"app": "aseprite", "placeholder": True}
    assert placeholder.is_placeholder(sheet)


def test_godot_resources_carry_metadata(tmp_path: Path) -> None:
    sheet = {"frames": [{"frame": {"x": 1, "y": 1, "w": 16, "h": 16}, "duration": 100}], "meta": {}}
    final, _ = godot.spriteframes_tres(sheet, "res://a.png")
    marked, _ = godot.spriteframes_tres(sheet, "res://a.png", placeholder=True)
    assert "metadata/placeholder" not in final
    assert marked.endswith("]\nmetadata/placeholder = true\n")

    tres = tmp_path / "a.tres"
    tres.write_text(marked)
    assert placeholder.is_placeholder(tres)
    tres.write_text(final)
    assert not placeholder.is_placeholder(tres)

    tiles = godot.tileset_tres("res://t.png", (16, 16), 1, [(0, 0)], placeholder=True)
    assert tiles.endswith('sources/0 = SubResource("atlas")\nmetadata/placeholder = true\n')


def test_aseprite_marker_is_detected_from_bytes(tmp_path: Path) -> None:
    # Header: file size, magic, frames, width, height; the property key follows later.
    header = struct.pack("<IHHHH", 0, 0xA5E0, 3, 32, 24)
    marked = tmp_path / "a.aseprite"
    marked.write_bytes(header + b"\0" * 10 + placeholder.MARKER.encode())
    final = tmp_path / "b.aseprite"
    final.write_bytes(header + b"\0" * 10)
    assert placeholder.is_placeholder(marked)
    assert not placeholder.is_placeholder(final)
    [finding] = placeholder.scan(marked)
    assert finding.details == {"width": 32, "height": 24, "frames": 3}


def test_missing_and_unknown_files_are_not_placeholders(tmp_path: Path) -> None:
    assert not placeholder.is_placeholder(tmp_path / "missing.png")
    (tmp_path / "broken.png").write_bytes(b"not a png")
    assert not placeholder.is_placeholder(tmp_path / "broken.png")
    (tmp_path / "notes.txt").write_text(placeholder.MARKER)
    assert not placeholder.is_placeholder(tmp_path / "notes.txt")


def test_require_placeholder(tmp_path: Path) -> None:
    final = _png(tmp_path / "final.png")
    with pytest.raises(placeholder.FinalArtError, match="final art"):
        placeholder.require_placeholder(final)
    marked = _png(tmp_path / "marked.png")
    placeholder.mark_png(marked)
    assert placeholder.require_placeholder(marked) == marked
    assert placeholder.require_placeholder(tmp_path / "new.png") == tmp_path / "new.png"


def test_guard_export_protects_only_final_art(tmp_path: Path) -> None:
    final = _png(tmp_path / "final.png")
    with pytest.raises(placeholder.FinalArtError, match="will not be replaced"):
        placeholder.guard_export([final], source_is_placeholder=True)
    placeholder.guard_export([final], source_is_placeholder=False)  # final may replace final
    placeholder.guard_export([tmp_path / "new.png"], source_is_placeholder=True)


def test_scan_reports_details_and_skips_engine_folders(tmp_path: Path) -> None:
    sprites = tmp_path / "assets" / "sprites"
    sprites.mkdir(parents=True)
    placeholder.mark_png(_png(sprites / "hero.png", 34, 18))
    tags = [{"name": "idle", "from": 0, "to": 0, "direction": "forward"}]
    sheet = {
        "frames": [{"frame": {"x": 1, "y": 1, "w": 16, "h": 16}, "duration": 100}],
        "meta": {"frameTags": tags},
    }
    text, _ = godot.spriteframes_tres(sheet, "res://assets/sprites/hero.png", placeholder=True)
    (sprites / "hero.tres").write_text(text)
    _png(sprites / "final.png")
    cache = tmp_path / ".godot" / "imported"
    cache.mkdir(parents=True)
    placeholder.mark_png(_png(cache / "hero.png"))

    found = {Path(f.path).name: f for f in placeholder.scan(tmp_path)}
    assert set(found) == {"hero.png", "hero.tres"}
    assert found["hero.png"].details == {"width": 34, "height": 18}
    assert found["hero.tres"].kind == "Godot SpriteFrames"
    assert found["hero.tres"].details == {"animations": ["idle"], "frame_size": "16x16"}


def test_audit_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    png = _png(tmp_path / "a.png")
    assert placeholder.audit_main([str(tmp_path)]) == 0
    assert "No placeholder assets found" in capsys.readouterr().out

    placeholder.mark_png(png)
    assert placeholder.audit_main([str(tmp_path)]) == 1
    assert "1 placeholder asset(s)" in capsys.readouterr().out

    assert placeholder.audit_main(["--json", str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out)["count"] == 1

    assert placeholder.audit_main([str(tmp_path / "missing")]) == 2
