from pathlib import Path

import pytest

from aseprite_mcp.paths import resolve, resolve_output


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path.resolve()


def test_accepts_absolute_path_inside_root(root: Path) -> None:
    assert resolve(str(root / "art" / "hero.aseprite"), [root]) == root / "art" / "hero.aseprite"


def test_rejects_relative_path_with_actionable_message(root: Path) -> None:
    with pytest.raises(ValueError, match="relative path") as exc:
        resolve("art/hero.aseprite", [root])
    assert str(root / "art" / "hero.aseprite") in str(exc.value)


def test_rejects_path_outside_roots(root: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside") / "x.aseprite"
    with pytest.raises(ValueError, match="outside the allowed folders"):
        resolve(str(outside), [root])


def test_rejects_traversal_out_of_root(root: Path) -> None:
    with pytest.raises(ValueError, match="outside the allowed folders"):
        resolve(str(root / ".." / "escape.aseprite"), [root])


def test_accepts_any_of_several_roots(root: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    second = tmp_path_factory.mktemp("second").resolve()
    assert resolve(str(second / "a.png"), [root, second]) == second / "a.png"


def test_must_exist(root: Path) -> None:
    with pytest.raises(FileNotFoundError):
        resolve(str(root / "missing.aseprite"), [root], must_exist=True)
    (root / "present.aseprite").touch()
    assert resolve(str(root / "present.aseprite"), [root], must_exist=True).exists()


def test_resolve_output_creates_parent_folders(root: Path) -> None:
    out = resolve_output(str(root / "a" / "b" / "sheet.png"), [root])
    assert out.parent.is_dir()
    assert not out.exists()
