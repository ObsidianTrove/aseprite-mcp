-- Replace the palette from hex colors or a palette file, optionally converting the
-- sprite to indexed mode (which remaps every pixel to its nearest palette color).
-- Params: path, colors? | palette_file?, to_indexed?, dithering?

local C = dofile(app.params.lib)

C.run(function(p)
  local s = C.open(p.path)
  local pal
  if p.palette_file then
    pal = Palette { fromFile = p.palette_file }
    assert(pal, "could not load palette file " .. p.palette_file)
  else
    assert(p.colors and #p.colors > 0, "provide colors or palette_file")
    pal = C.palette_from(p.colors)
  end
  s:setPalette(pal)
  if p.to_indexed and s.colorMode ~= ColorMode.INDEXED then
    app.command.ChangePixelFormat { format = "indexed", dithering = p.dithering or "none" }
  end
  C.save(s)
  return C.info(s)
end)
