# Game project layout

A folder skeleton for a Godot 4 game that uses aseprite-mcp placeholder art. Copy its
contents next to your `project.godot`.

| Folder | Contents | In the game build? |
|---|---|---|
| `art/placeholder/` | AI-generated `.aseprite` sources, created through aseprite-mcp | No (`.gdignore`) |
| `art/final/` | Hand-made `.aseprite` sources, at the same relative paths as the placeholders they replace | No (`.gdignore`) |
| `assets/sprites/`, `assets/tiles/` | Exported PNG + `.tres` files. Scenes and scripts reference only these | Yes |
| `store/` | Storefront art: capsules, icons, screenshots | No (`.gdignore`) |

Placeholders and final art export to the **same** files under `assets/`, so final art
replaces a placeholder without any change to scenes or code. See
[the placeholder workflow](../../docs/placeholder-workflow.md) for the full process and the
release check.

The `.gdignore` files keep Godot from importing the sources. Remove the one in `art/` if
you use a Godot plugin that imports `.aseprite` files directly.
