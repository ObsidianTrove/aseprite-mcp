-- Describe a sprite: size, color mode, frames, layers, tags and palette.
-- Params: path

local C = dofile(app.params.lib)

C.run(function(p)
  return C.info(C.open(p.path))
end)
