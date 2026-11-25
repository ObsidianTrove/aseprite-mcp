-- Export a tileset PNG with edge extrusion, which prevents seams when tiles are scaled
-- or filtered. The source is either a tilemap layer's tileset (when `layer` names a
-- tilemap layer) or the flattened frame sliced into a tile_w x tile_h grid.
-- Params: path, out_png, tile_w?, tile_h?, layer?, frame?, extrude?, columns?

local C = dofile(app.params.lib)
C.run(function(p)
  local s = C.open(p.path)
  local e = p.extrude or 1
  local tw, th = p.tile_w, p.tile_h
  local tiles = {}  -- list of Images (nil = empty slot)
  local src_cols

  local layer = p.layer and C.find_layer(s, p.layer) or nil
  if layer and layer.isTilemap then
    local ts = layer.tileset
    tw, th = ts.grid.tileSize.width, ts.grid.tileSize.height
    for i = 1, #ts - 1 do  -- index 0 is the empty tile
      tiles[#tiles + 1] = ts:tile(i).image
    end
    src_cols = p.columns or math.max(1, math.ceil(math.sqrt(#tiles)))
  else
    assert(tw and th, "tile_w and tile_h are required for non-tilemap sources")
    local flat = Image(s.width, s.height, s.colorMode)
    flat:clear()
    flat:drawSprite(s, p.frame or 1)
    src_cols = math.floor(s.width / tw)
    local src_rows = math.floor(s.height / th)
    for ty = 0, src_rows - 1 do
      for tx = 0, src_cols - 1 do
        local t = Image(tw, th, s.colorMode)
        t:clear()
        for y = 0, th - 1 do
          for x = 0, tw - 1 do
            t:drawPixel(x, y, flat:getPixel(tx * tw + x, ty * th + y))
          end
        end
        tiles[#tiles + 1] = t
      end
    end
  end

  local cols = p.columns or src_cols
  local rows = math.ceil(#tiles / cols)
  local cw, ch = tw + 2 * e, th + 2 * e
  local out = Sprite(cols * cw, rows * ch, s.colorMode)
  out:setPalette(s.palettes[1])
  local img = Image(out.width, out.height, out.colorMode)
  img:clear()

  local occupied = {}
  for i, t in ipairs(tiles) do
    local cx = ((i - 1) % cols)
    local cy = math.floor((i - 1) / cols)
    if not t:isEmpty() then occupied[#occupied + 1] = { cx, cy } end
    for oy = -e, th + e - 1 do
      local sy = math.min(math.max(oy, 0), th - 1)
      for ox = -e, tw + e - 1 do
        local sx = math.min(math.max(ox, 0), tw - 1)
        img:drawPixel(cx * cw + e + ox, cy * ch + e + oy, t:getPixel(sx, sy))
      end
    end
  end
  out.cels[1].image = img
  out:saveAs(p.out_png)

  return {
    png = p.out_png,
    tile_w = tw,
    tile_h = th,
    columns = cols,
    rows = rows,
    extrude = e,
    tiles = occupied, -- atlas coordinates of non-empty tiles
  }
end)
