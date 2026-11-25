"""Path validation: every file the server touches must be absolute and inside an allowed root."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


def resolve(raw: str, roots: Sequence[Path], *, must_exist: bool = False) -> Path:
    """Return `raw` as a resolved absolute path, or raise if it is unsafe or missing.

    Relative paths are rejected rather than guessed: the server cannot know the client's
    working folder, and guessing would silently read or write the wrong location.
    """
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError(
            f"'{raw}' is a relative path. Use a full absolute path, e.g. "
            f"'{roots[0] / path}' if that is where it lives."
        )
    path = path.resolve()
    if not any(path.is_relative_to(root) for root in roots):
        allowed = ", ".join(str(r) for r in roots)
        raise ValueError(
            f"{path} is outside the allowed folders ({allowed}). "
            "Add its folder to ASEPRITE_MCP_ROOTS in the MCP server configuration."
        )
    if must_exist and not path.exists():
        raise FileNotFoundError(f"{path} does not exist")
    return path


def resolve_output(raw: str, roots: Sequence[Path]) -> Path:
    """Like `resolve`, and also create the parent folder."""
    path = resolve(raw, roots)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
