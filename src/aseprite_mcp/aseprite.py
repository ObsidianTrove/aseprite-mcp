"""Thin wrapper around the Aseprite command line and its Lua scripting interface."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

LUA_DIR = Path(__file__).resolve().parent / "lua"


class AsepriteError(RuntimeError):
    """Aseprite failed, or a Lua tool script reported an error."""


class Aseprite:
    """Runs Aseprite in batch mode (`-b`). Every call is a separate, windowless process."""

    def __init__(self, executable: Path | None, timeout: int = 120) -> None:
        self.executable = executable
        self.timeout = timeout

    def run(self, args: list[str]) -> str:
        """Run `aseprite -b <args>` and return its stdout."""
        if self.executable is None or not self.executable.exists():
            where = f" at {self.executable}" if self.executable else ""
            raise AsepriteError(
                f"Aseprite executable not found{where}. Set ASEPRITE_PATH in the MCP server "
                "configuration."
            )
        proc = subprocess.run(
            [str(self.executable), "-b", *args],
            stdin=subprocess.DEVNULL,  # keep Aseprite away from the MCP stdio stream
            capture_output=True,
            text=True,
            timeout=self.timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            output = (proc.stderr or proc.stdout).strip()
            raise AsepriteError(f"Aseprite exited with code {proc.returncode}: {output}")
        return proc.stdout

    def lua(self, script: str | Path, /, **params: Any) -> Any:
        """Run a Lua tool script and return its result.

        `script` is either the name of a bundled script in `lua/` or a path to a script.
        Arguments travel through a JSON file; `None` values are omitted.
        """
        script_path = script if isinstance(script, Path) else LUA_DIR / f"{script}.lua"
        with tempfile.TemporaryDirectory(prefix="aseprite-mcp-") as tmp:
            params_file = Path(tmp) / "params.json"
            result_file = Path(tmp) / "result.json"
            payload = {k: v for k, v in params.items() if v is not None}
            payload["__out"] = str(result_file)
            params_file.write_text(json.dumps(payload), encoding="utf-8")
            stdout = self.run(
                [
                    "--script-param", f"lib={LUA_DIR / 'common.lua'}",
                    "--script-param", f"params={params_file}",
                    "--script", str(script_path),
                ]
            )  # fmt: skip
            if not result_file.exists():
                raise AsepriteError(f"{script_path.name} produced no result. Output:\n{stdout}")
            result = json.loads(result_file.read_text(encoding="utf-8"))
        if not result.get("ok"):
            raise AsepriteError(result.get("error", "unknown Lua error"))
        return result.get("result")

    def export_sheet(
        self,
        src: Path,
        png: Path,
        data: Path | None = None,
        *,
        sheet_type: str = "packed",
        tag: str | None = None,
        layer: str | None = None,
        scale: int = 1,
        padding: int = 1,
        trim: bool = False,
        columns: int | None = None,
        frame: int | None = None,
    ) -> dict[str, Any] | None:
        """Export a sprite sheet PNG, plus Aseprite's JSON metadata when `data` is given.

        `frame` is 1-based and limits the export to a single frame.
        """
        args: list[str] = []
        if layer:
            args += ["--layer", layer]
        if tag:
            args += ["--tag", tag]
        if frame is not None:
            args += ["--frame-range", f"{frame - 1},{frame - 1}"]
        if trim:
            args += ["--trim"]
        args.append(str(src))
        if scale != 1:
            args += ["--scale", str(scale)]  # applies to sprites opened before it
        args += ["--sheet", str(png), "--sheet-type", sheet_type]
        if padding:
            args += ["--shape-padding", str(padding), "--border-padding", str(padding)]
        if columns and sheet_type in ("rows", "columns", "horizontal"):
            args += ["--sheet-columns", str(columns)]
        if data:
            args += ["--data", str(data), "--format", "json-array", "--list-tags", "--list-layers"]
        self.run(args)
        return json.loads(data.read_text(encoding="utf-8")) if data else None
