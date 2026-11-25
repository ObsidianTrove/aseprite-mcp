-- Create a new sprite file.
-- Params: path, width, height, frames?, color_mode?, palette?, background?, duration_ms?, layer_name?

local C = dofile(app.params.lib)

C.run(function(p)
  local mode = C.MODES[p.color_mode or "rgb"]
  assert(mode, "color_mode must be rgb, indexed or gray")
  local s = Sprite(p.width, p.height, mode)
  app.sprite = s
  if p.palette and #p.palette > 0 then s:setPalette(C.palette_from(p.palette)) end
  s.layers[1].name = p.layer_name or "Layer 1"
  for _ = 2, (p.frames or 1) do s:newEmptyFrame() end
  for _, f in ipairs(s.frames) do f.duration = (p.duration_ms or 100) / 1000 end
  if p.background then
    local layer = s.layers[1]
    for i = 1, #s.frames do
      local img, commit = C.canvas(s, layer, i)
      img:clear(C.pixel(s, p.background))
      commit()
    end
  end
  C.save(s, p.path)
  return C.info(s)
end)
