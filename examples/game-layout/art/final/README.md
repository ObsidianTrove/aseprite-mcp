# Final sources

Hand-made `.aseprite` files that replace the placeholders. Mirror the folder structure and
file names of `art/placeholder/` exactly, and keep the animation names, frame sizes and
tile layouts the game already relies on.

Start each file from scratch rather than from the placeholder: a file saved from a
placeholder keeps its marker. aseprite-mcp never modifies files in this folder.

Export with `batch_export` (`src_dir` = this folder) to replace the placeholder exports in
`assets/`.
