# Placeholder asset workflow

aseprite-mcp is for **placeholder art**: quick, iterable assets that let you build and test
a game long before final art exists. It is not meant for final, shipped art.

Every file the server writes is marked as an AI-generated placeholder, and the marker
travels inside the file itself. When final art replaces a file, the marker goes with it.
Before release, one command confirms that nothing AI-generated is left in the build.

- [Goals](#goals)
- [How assets are marked](#how-assets-are-marked)
- [How final art is protected](#how-final-art-is-protected)
- [Recommended game project layout](#recommended-game-project-layout)
- [The replacement contract](#the-replacement-contract)
- [Swapping in final art](#swapping-in-final-art)
- [Release check](#release-check)
- [Storefront checklist](#storefront-checklist)
- [Limitations](#limitations)

## Goals

1. **Every placeholder is identifiable**, by people and by tools, at every stage: in
   Aseprite, in the Godot project, in game code, and in CI.
2. **Final art drops in without refactoring.** Scenes, scripts and resources reference
   stable `res://` paths and animation names, so replacing a placeholder never means
   editing a scene.
3. **Final art is never touched by the AI.** The server refuses to modify or overwrite
   unmarked files, so hand-made work cannot be altered or downgraded by accident.

## How assets are marked

| File | Marker | Where you can see it |
|---|---|---|
| `.aseprite` / `.ase` | Sprite property `aseprite_mcp_placeholder = true`, plus a note in the sprite's user data | Aseprite: **Sprite > Properties > User Data**; `sprite_info` returns `"placeholder": true` |
| `.png` | A `tEXt` chunk with keyword `aseprite_mcp_placeholder` | Image metadata viewers (e.g. `exiftool`); the audit |
| `.tres` (SpriteFrames, TileSet) | `metadata/placeholder = true` on the resource | Godot Inspector under **Metadata**; game code (below) |
| `.json` (sprite sheet data) | `"placeholder": true` in the `meta` object | Any text editor |

Marking is automatic and cannot be turned off from a tool call:

- Every tool that saves a sprite (`create_sprite`, `draw`, `add_frames`, `add_layer`,
  `tag_animation`, `set_palette`, `palette_swap`, `import_image`) marks it.
- Every export (`export_spritesheet`, `export_godot_spriteframes`, `export_tileset`,
  `batch_export`) marks its output when the source sprite is a placeholder. Exporting an
  unmarked sprite, such as final art you made yourself, produces clean output. That means
  the same tools export both kinds.

Game code can check the marker at runtime, for example to tint placeholders in debug builds
or log a warning:

```gdscript
func _ready() -> void:
    if OS.is_debug_build() and sprite_frames.get_meta("placeholder", false):
        push_warning("%s uses placeholder art" % sprite_frames.resource_path)
```

## How final art is protected

Any file **without** the marker counts as final art. The server:

- **Will not modify final art.** `draw`, `add_frames`, `add_layer`, `tag_animation`,
  `set_palette` and in-place `palette_swap` refuse to touch an unmarked sprite, and
  `create_sprite` and `import_image` refuse to overwrite one.
- **Will not downgrade final exports.** A placeholder export refuses to overwrite an
  unmarked PNG, `.tres` or `.json`. `batch_export` lists such files under `kept_final`
  and carries on with the rest.
- **Can derive from final art.** `palette_swap` with `out_path` creates a new,
  placeholder-marked variant and leaves the original untouched.

The guard works in that direction only: final art may always replace a placeholder.

## Recommended game project layout

[examples/game-layout](../examples/game-layout) contains this skeleton, ready to copy into
a Godot project:

```
my-game/
  project.godot
  art/                      Aseprite sources. Contains .gdignore, so Godot skips it
    placeholder/            AI-generated sources, created through aseprite-mcp
      characters/hero.aseprite
      enemies/slime.aseprite
    final/                  Hand-made sources, at the same relative paths
      characters/hero.aseprite
  assets/                   Exported files. Scenes and scripts reference only these
    sprites/
      characters/hero.png   (final)
      characters/hero.tres  (final)
      enemies/slime.png     (placeholder until final art exists)
      enemies/slime.tres
    tiles/
  store/                    Storefront art: capsules, icons, screenshots. Also .gdignore
```

Placeholders and final art have **separate source folders** but share **one export folder**.
The source folders keep the provenance of every source file obvious. The shared export
folder means a scene that references `res://assets/sprites/enemies/slime.tres` keeps working
when the slime's final art arrives; nothing in Godot needs to know which version it has.

Avoid separate `assets/placeholder/` and `assets/final/` export folders: every swap would
then mean re-pointing every scene and script that uses the asset.

## The replacement contract

A final asset can drop in without refactoring when it keeps everything that code and scenes
depend on:

| Keep the same | Why |
|---|---|
| File name and relative folder | Scenes and scripts reference the `res://` path |
| Animation (tag) names | Code calls `play("walk")` |
| Frame size | Collision shapes, offsets and pivots are tuned to it |
| Tile size and atlas layout (tilesets) | Painted `TileMapLayer` cells refer to atlas coordinates |

Everything else is free to change: colors, palette, number of frames per animation, frame
timing, and detail.

`placeholder_report` (or `aseprite-mcp-audit`) lists these properties for every remaining
placeholder, so its output doubles as a brief for the artist:

```
assets/sprites/enemies/slime.tres
    Godot SpriteFrames  (animations=['idle', 'hurt'], frame_size=16x16)
```

## Swapping in final art

1. Save the final source at the mirrored path, e.g.
   `art/final/enemies/slime.aseprite` for `art/placeholder/enemies/slime.aseprite`.
   Start from a new file rather than from the placeholder: a file saved from a placeholder
   keeps its marker, and art painted over AI output is still AI-derived.
2. Export it to the same place:
   ```
   batch_export(src_dir=".../art/final", godot_project=".../my-game")
   ```
   or `export_godot_spriteframes` with the same `target_dir` and `name` as the placeholder.
   The export is unmarked, so it replaces the placeholder files in place.
3. Run the audit to confirm the placeholder is gone.

You can repeat `batch_export` on `art/placeholder` at any time. It refreshes the remaining
placeholders and skips everything that already has final art.

Final art that arrives as a plain PNG works as well, as long as it matches the replacement
contract: overwrite the PNG and regenerate or edit the `.tres`. The audit keeps reporting the
`.tres` until its `metadata/placeholder` line is gone.

## Release check

`aseprite-mcp-audit` scans files and folders, lists every placeholder, and exits with
status 1 while any remain. It needs no Aseprite installation, so it runs in CI.

```sh
# From a clone of aseprite-mcp
uv run aseprite-mcp-audit /path/to/my-game/assets /path/to/my-game/store

# Without a clone
uvx --from git+https://github.com/ObsidianTrove/aseprite-mcp aseprite-mcp-audit assets store

# Machine-readable output
uv run aseprite-mcp-audit --json /path/to/my-game
```

Choose what to audit:

- **Shipped content** (`assets/`, `store/` and any other folder that ends up in the build or
  on a store page): this is the release gate. It must report nothing before you submit.
- **The whole project**: this also counts placeholder sources under `art/placeholder/`. Use
  it to track progress, or as a strict gate once you want the repository itself free of AI
  art; delete `art/placeholder/` when everything has final art (it stays in version
  control history).

Example GitHub Actions step for a game repository, failing release builds that still
contain placeholders:

```yaml
- uses: astral-sh/setup-uv@v6
- name: No placeholder art in shipped content
  run: uvx --from git+https://github.com/ObsidianTrove/aseprite-mcp aseprite-mcp-audit assets store
```

From an agent, `placeholder_report` returns the same information.

## Storefront checklist

Before submitting a build to Steam, the App Store or Google Play:

- [ ] `aseprite-mcp-audit` reports no placeholders in shipped folders.
- [ ] Store art (capsules, icons, feature graphics, screenshots, trailers) is final.
      Screenshots and trailer footage captured while placeholders were in the game are
      not marked, so recapture them after the swap.
- [ ] Assets created outside aseprite-mcp, for example with `run_lua` or other AI tools,
      have been reviewed by hand. They carry no marker.
- [ ] Your answers to the storefront's questions about AI-generated content (Steam asks
      about this when you set up a store page) reflect what actually ships.

## Limitations

- **`run_lua` is outside the guarantee.** Scripts run with full scripting access and can
  save files without the marker. It is disabled unless `ASEPRITE_MCP_ALLOW_LUA=1`.
- **Markers can be removed by hand.** The system tracks provenance faithfully; it does not
  enforce it against deliberate edits. Re-saving a placeholder in another program may drop
  a PNG's metadata chunk. Keep exports flowing through aseprite-mcp, and treat the audit as
  a safety net, not a replacement for review.
- **Files written before this feature** carry no marker and are treated as final art. If
  you have older AI-made sprites, recreate them through the current server, or mark them
  in Aseprite with a script that sets `sprite.properties.aseprite_mcp_placeholder = true`.
- **Binary Godot resources** (`.res`, `.scn`) and imported textures under `.godot/` are not
  scanned. The server writes only text resources, and the audit checks the source files
  that Godot imports from.
