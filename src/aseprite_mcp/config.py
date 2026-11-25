"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

# Common install locations, checked in order when ASEPRITE_PATH is not set.
_CANDIDATES: dict[str, list[str]] = {
    "win32": [
        r"C:\Program Files (x86)\Steam\steamapps\common\Aseprite\Aseprite.exe",
        r"C:\Program Files\Aseprite\Aseprite.exe",
    ],
    "darwin": [
        "/Applications/Aseprite.app/Contents/MacOS/aseprite",
        "~/Library/Application Support/Steam/steamapps/common/Aseprite/"
        "Aseprite.app/Contents/MacOS/aseprite",
    ],
    "linux": [
        "~/.steam/steam/steamapps/common/Aseprite/aseprite",
        "~/.local/share/Steam/steamapps/common/Aseprite/aseprite",
    ],
}


def find_aseprite() -> Path | None:
    """Locate the Aseprite executable: ASEPRITE_PATH, then known install paths, then PATH."""
    if env := os.environ.get("ASEPRITE_PATH"):
        return Path(env).expanduser()
    for candidate in _CANDIDATES.get(sys.platform, []):
        path = Path(candidate).expanduser()
        if path.exists():
            return path
    found = shutil.which("aseprite")
    return Path(found) if found else None


def parse_roots(raw: str) -> list[Path]:
    """Parse an os.pathsep-separated list of folders; defaults to the user's home folder."""
    roots = [Path(r).expanduser().resolve() for r in raw.split(os.pathsep) if r.strip()]
    return roots or [Path.home().resolve()]


@dataclass(frozen=True)
class Settings:
    aseprite: Path | None
    """Aseprite executable, or None if it could not be found."""
    roots: list[Path]
    """Folders the server is allowed to read from and write to."""
    timeout: int
    """Seconds before a single Aseprite invocation is aborted."""
    allow_lua: bool
    """Whether the run_lua tool may execute arbitrary scripts."""

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            aseprite=find_aseprite(),
            roots=parse_roots(os.environ.get("ASEPRITE_MCP_ROOTS", "")),
            timeout=int(os.environ.get("ASEPRITE_TIMEOUT", "120")),
            allow_lua=os.environ.get("ASEPRITE_MCP_ALLOW_LUA") == "1",
        )
