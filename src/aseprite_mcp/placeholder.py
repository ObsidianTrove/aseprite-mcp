"""Placeholder marking: everything this server writes is tagged as an AI-generated placeholder.

The marker travels inside each file, so replacing a file with final art removes the marker
with it and there is no separate manifest to keep in sync:

    .aseprite / .ase   sprite property `aseprite_mcp_placeholder` (set by common.lua on save)
    .png               a tEXt chunk with keyword `aseprite_mcp_placeholder`
    .tres / .tscn      `metadata/placeholder = true` on the resource, readable in game code
                       with `resource.get_meta("placeholder", false)`
    .json              `"placeholder": true` in the sprite sheet's `meta` object

Two rules protect final art:
  * Final (unmarked) art is never modified or overwritten by the server.
  * Exports of placeholder sources never overwrite final exports.

`scan` finds every marked file under a folder; it is used by the `placeholder_report` tool
and the `aseprite-mcp-audit` command, which exits non-zero while any placeholder remains.
"""

from __future__ import annotations

import json
import re
import struct
import sys
import zlib
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

MARKER = "aseprite_mcp_placeholder"
NOTICE = "AI-generated placeholder asset (aseprite-mcp). Replace with final art before release."

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SPRITE_SUFFIXES = {".aseprite", ".ase"}
GODOT_SUFFIXES = {".tres", ".tscn"}
SKIP_DIRS = {".git", ".godot", ".import", ".venv", "node_modules", "__pycache__"}

_GODOT_META = re.compile(r"^metadata/placeholder = true$", re.MULTILINE)


class FinalArtError(PermissionError):
    """An operation would modify or replace final (non-placeholder) art."""


# --------------------------------------------------------------------------- detection


def _png_chunks(data: bytes) -> Iterator[tuple[bytes, bytes, int, int]]:
    """Yield (type, payload, start, end) for each chunk of a PNG file."""
    if data[:8] != PNG_SIGNATURE:
        raise ValueError("not a PNG file")
    pos = 8
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        end = pos + 12 + length
        yield kind, data[pos + 8 : pos + 8 + length], pos, end
        if kind == b"IEND":
            return
        pos = end


def _png_marked(data: bytes) -> bool:
    keyword = MARKER.encode("latin-1") + b"\0"
    return any(k == b"tEXt" and p.startswith(keyword) for k, p, _, _ in _png_chunks(data))


def is_placeholder(path: Path) -> bool:
    """True if `path` exists and carries the placeholder marker for its file type."""
    if not path.is_file():
        return False
    suffix = path.suffix.lower()
    try:
        if suffix in SPRITE_SUFFIXES:
            # Sprite properties are stored uncompressed, so the key appears verbatim.
            return MARKER.encode() in path.read_bytes()
        if suffix == ".png":
            return _png_marked(path.read_bytes())
        if suffix in GODOT_SUFFIXES:
            return bool(_GODOT_META.search(path.read_text(encoding="utf-8", errors="replace")))
        if suffix == ".json":
            meta = json.loads(path.read_text(encoding="utf-8")).get("meta", {})
            return isinstance(meta, dict) and meta.get("placeholder") is True
    except (ValueError, OSError, AttributeError):
        return False
    return False


# --------------------------------------------------------------------------- marking


def mark_png(path: Path) -> None:
    """Add the placeholder tEXt chunk to a PNG, directly after its IHDR chunk."""
    data = path.read_bytes()
    if _png_marked(data):
        return
    _, _, _, ihdr_end = next(_png_chunks(data))
    payload = MARKER.encode("latin-1") + b"\0" + NOTICE.encode("latin-1")
    chunk = (
        struct.pack(">I", len(payload))
        + b"tEXt"
        + payload
        + struct.pack(">I", zlib.crc32(b"tEXt" + payload))
    )
    path.write_bytes(data[:ihdr_end] + chunk + data[ihdr_end:])


def mark_json(path: Path) -> None:
    """Set `meta.placeholder = true` in an Aseprite sprite sheet JSON file."""
    sheet = json.loads(path.read_text(encoding="utf-8"))
    sheet.setdefault("meta", {})["placeholder"] = True
    path.write_text(json.dumps(sheet, indent=1), encoding="utf-8")


def mark(path: Path) -> None:
    """Mark an exported file. .aseprite files are marked by the Lua scripts on save, and
    .tres files are generated with the metadata already in place."""
    suffix = path.suffix.lower()
    if suffix == ".png":
        mark_png(path)
    elif suffix == ".json":
        mark_json(path)


# --------------------------------------------------------------------------- guards


def require_placeholder(path: Path) -> Path:
    """Refuse to modify an existing file unless it is a placeholder."""
    if path.exists() and not is_placeholder(path):
        raise FinalArtError(
            f"{path} is final art (it has no placeholder marker), and this server never "
            "modifies final art. To build a placeholder variant from it, use palette_swap "
            "with out_path, or import_image into a new file."
        )
    return path


def guard_export(targets: Sequence[Path], source_is_placeholder: bool) -> None:
    """Refuse to overwrite final exports with exports of a placeholder source."""
    if not source_is_placeholder:
        return
    for target in targets:
        if target.exists() and not is_placeholder(target):
            raise FinalArtError(
                f"{target} is final art and will not be replaced by a placeholder export. "
                "Delete it first if you really want to go back to the placeholder."
            )


# --------------------------------------------------------------------------- audit


@dataclass
class Finding:
    path: str
    kind: str
    details: dict = field(default_factory=dict)


def _details(path: Path) -> tuple[str, dict]:
    """Describe a placeholder so a replacement can match it exactly."""
    suffix = path.suffix.lower()
    if suffix in SPRITE_SUFFIXES:
        frames, width, height = struct.unpack("<HHH", path.read_bytes()[6:12])
        return "aseprite source", {"width": width, "height": height, "frames": frames}
    if suffix == ".png":
        width, height = struct.unpack(">II", path.read_bytes()[16:24])
        return "image", {"width": width, "height": height}
    if suffix == ".json":
        return "sprite sheet data", {}
    text = path.read_text(encoding="utf-8", errors="replace")
    if 'type="SpriteFrames"' in text:
        region = re.search(r"region = Rect2\([\d.]+, [\d.]+, ([\d.]+), ([\d.]+)\)", text)
        details: dict = {"animations": re.findall(r'"name": &"((?:[^"\\]|\\.)*)"', text)}
        if region:
            details["frame_size"] = f"{region[1]}x{region[2]}"
        return "Godot SpriteFrames", details
    if 'type="TileSet"' in text:
        tile = re.search(r"^tile_size = Vector2i\((\d+), (\d+)\)", text, re.MULTILINE)
        return "Godot TileSet", {"tile_size": f"{tile[1]}x{tile[2]}"} if tile else {}
    return "Godot resource", {}


def scan(root: Path) -> list[Finding]:
    """Find every placeholder file under `root` (or `root` itself, if it is a file)."""
    files = [root] if root.is_file() else _walk(root)
    findings = []
    for file in files:
        if is_placeholder(file):
            kind, details = _details(file)
            findings.append(Finding(str(file), kind, details))
    return findings


def _walk(root: Path) -> Iterator[Path]:
    suffixes = SPRITE_SUFFIXES | GODOT_SUFFIXES | {".png", ".json"}
    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            if entry.name not in SKIP_DIRS:
                yield from _walk(entry)
        elif entry.suffix.lower() in suffixes:
            yield entry


def report(roots: Sequence[Path]) -> dict:
    findings = [f for root in roots for f in scan(root)]
    return {"count": len(findings), "placeholders": [asdict(f) for f in findings]}


def audit_main(argv: Sequence[str] | None = None) -> int:
    """`aseprite-mcp-audit [PATH ...]`: list placeholders; exit 1 if any remain."""
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in args
    roots = [Path(a).resolve() for a in args if a != "--json"] or [Path.cwd()]
    missing = [r for r in roots if not r.exists()]
    if missing:
        print(f"error: {', '.join(map(str, missing))} does not exist", file=sys.stderr)
        return 2
    result = report(roots)
    if as_json:
        print(json.dumps(result, indent=2))
    elif result["count"]:
        print(f"{result['count']} placeholder asset(s) must be replaced before release:\n")
        cwd = Path.cwd()
        for f in result["placeholders"]:
            path = Path(f["path"])
            shown = path.relative_to(cwd) if path.is_relative_to(cwd) else path
            details = ", ".join(f"{k}={v}" for k, v in f["details"].items())
            print(f"  {shown}\n      {f['kind']}{'  (' + details + ')' if details else ''}")
    else:
        print("No placeholder assets found.")
    return 1 if result["count"] else 0


if __name__ == "__main__":
    sys.exit(audit_main())
