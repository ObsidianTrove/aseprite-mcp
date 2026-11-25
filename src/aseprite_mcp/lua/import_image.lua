-- Import a raster image, resize it with nearest-neighbor sampling, and optionally reduce
-- it to a fixed palette or a maximum number of colors.
-- Params: src, out_path, width?, height?, colors? | max_colors?, dithering?

local C = dofile(app.params.lib)

C.run(function(p)
  local s = C.open(p.src)
  if p.width or p.height then
    local w = p.width or math.floor(s.width * p.height / s.height + 0.5)
    local h = p.height or math.floor(s.height * p.width / s.width + 0.5)
    app.command.SpriteSize { ui = false, width = w, height = h, lockRatio = false }
  end
  if s.colorMode ~= ColorMode.RGB and (p.colors or p.max_colors) then
    app.command.ChangePixelFormat { format = "rgb" }
  end
  if p.colors and #p.colors > 0 then
    s:setPalette(C.palette_from(p.colors))
    app.command.ChangePixelFormat { format = "indexed", dithering = p.dithering or "none" }
  elseif p.max_colors then
    app.command.ColorQuantization { ui = false, maxColors = p.max_colors, withAlpha = true }
    app.command.ChangePixelFormat { format = "indexed", dithering = p.dithering or "none" }
  end
  C.save(s, p.out_path)
  return C.info(s)
end)
