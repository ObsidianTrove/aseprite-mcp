-- Apply a list of drawing operations to one layer on one or more frames.
-- Params: path, ops, layer?, frame? | frames?
--
-- Ops (coordinates in pixels, origin top-left):
--   {op="pixels", points={{x,y},...}, color="#rrggbb"}
--   {op="pixels", points={{x,y,"#rrggbb"},...}}
--   {op="rect", x=,y=,w=,h=, color=, fill=true|false}
--   {op="line", x1=,y1=,x2=,y2=, color=}
--   {op="circle", cx=,cy=,r=, color=, fill=true|false}
--   {op="rows", x=0, y=0, rows={"..aa..", ".abba."}, key={a="#000000", b="#ff0000"}}  ('.' or ' ' = skip)
--   {op="clear", color=optional}   (clear whole cel to transparent or a color)

local C = dofile(app.params.lib)

local function plot(img, x, y, v)
  if x >= 0 and y >= 0 and x < img.width and y < img.height then img:drawPixel(x, y, v) end
end

local function line(img, x1, y1, x2, y2, v)
  local dx, dy = math.abs(x2 - x1), -math.abs(y2 - y1)
  local sx = x1 < x2 and 1 or -1
  local sy = y1 < y2 and 1 or -1
  local err = dx + dy
  while true do
    plot(img, x1, y1, v)
    if x1 == x2 and y1 == y2 then break end
    local e2 = 2 * err
    if e2 >= dy then err = err + dy; x1 = x1 + sx end
    if e2 <= dx then err = err + dx; y1 = y1 + sy end
  end
end

local function circle(img, cx, cy, r, v, fill)
  for y = -r, r do
    for x = -r, r do
      local d = x * x + y * y
      if fill then
        if d <= r * r + r then plot(img, cx + x, cy + y, v) end
      else
        if d <= r * r + r and d >= r * r - r then plot(img, cx + x, cy + y, v) end
      end
    end
  end
end

C.run(function(p)
  local s = C.open(p.path)
  local layer = C.find_layer(s, p.layer)
  local frames = p.frames or { p.frame or 1 }
  local n = 0
  for _, fno in ipairs(frames) do
    local img, commit = C.canvas(s, layer, fno)
    for _, op in ipairs(p.ops) do
      local kind = op.op
      if kind == "pixels" then
        for _, pt in ipairs(op.points) do
          plot(img, pt[1], pt[2], C.pixel(s, pt[3] or op.color))
        end
      elseif kind == "rect" then
        local v = C.pixel(s, op.color)
        for y = op.y, op.y + op.h - 1 do
          for x = op.x, op.x + op.w - 1 do
            if op.fill or y == op.y or y == op.y + op.h - 1 or x == op.x or x == op.x + op.w - 1 then
              plot(img, x, y, v)
            end
          end
        end
      elseif kind == "line" then
        line(img, op.x1, op.y1, op.x2, op.y2, C.pixel(s, op.color))
      elseif kind == "circle" then
        circle(img, op.cx, op.cy, op.r, C.pixel(s, op.color), op.fill)
      elseif kind == "rows" then
        local cache = {}
        for k, c in pairs(op.key) do cache[k] = C.pixel(s, c) end
        local ox, oy = op.x or 0, op.y or 0
        for ry, row in ipairs(op.rows) do
          for rx = 1, #row do
            local ch = row:sub(rx, rx)
            if ch ~= "." and ch ~= " " then
              local v = cache[ch]
              assert(v ~= nil, "rows: character '" .. ch .. "' missing from key")
              plot(img, ox + rx - 1, oy + ry - 1, v)
            end
          end
        end
      elseif kind == "clear" then
        if op.color then img:clear(C.pixel(s, op.color)) else img:clear() end
      else
        error("unknown draw op: " .. tostring(kind))
      end
      n = n + 1
    end
    commit()
  end
  C.save(s)
  return { ops_applied = n, layer = layer.name, frames = frames }
end)
