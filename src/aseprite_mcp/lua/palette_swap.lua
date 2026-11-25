-- Recolor exact colors ({"#from": "#to"}) across every cel of every layer and frame.
-- Indexed sprites are recolored through the palette; RGB/gray sprites pixel by pixel.
-- Params: path, mapping, out_path?

local C = dofile(app.params.lib)
C.run(function(p)
  local s = C.open(p.path)
  local changed = 0
  if s.colorMode == ColorMode.INDEXED then
    local pal = s.palettes[1]
    for from, to in pairs(p.mapping) do
      local fr, fg, fb = C.parse_hex(from)
      local tr, tg, tb, ta = C.parse_hex(to)
      for i = 0, #pal - 1 do
        local c = pal:getColor(i)
        if c.red == fr and c.green == fg and c.blue == fb then
          pal:setColor(i, Color { r = tr, g = tg, b = tb, a = ta })
          changed = changed + 1
        end
      end
    end
  else
    local map = {}
    for from, to in pairs(p.mapping) do
      local fr, fg, fb, fa = C.parse_hex(from)
      local key
      if s.colorMode == ColorMode.GRAY then
        key = C.pixel(s, from)
      else
        key = app.pixelColor.rgba(fr, fg, fb, fa)
      end
      map[key] = C.pixel(s, to)
    end
    for _, cel in ipairs(s.cels) do
      if not cel.layer.isTilemap then
        local img = cel.image:clone()
        local hit = false
        for it in img:pixels() do
          local v = map[it()]
          if v then it(v); hit = true; changed = changed + 1 end
        end
        if hit then cel.image = img end
      end
    end
  end
  C.save(s, p.out_path or s.filename)
  return { changed = changed, out_path = p.out_path or s.filename }
end)
