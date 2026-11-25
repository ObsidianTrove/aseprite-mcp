-- Shared helpers for the aseprite-mcp tool scripts.
--
-- Protocol: the server invokes `aseprite -b --script <tool>.lua` with two script params:
--   lib    = path to this file
--   params = path to a JSON file holding the tool arguments plus `__out`
-- Each tool script calls C.run(fn); fn receives the decoded arguments and returns a
-- JSON-serializable table. C.run writes {ok=true, result=...} or {ok=false, error=...}
-- to `__out`, which the server reads back.

local M = {}

local function read_file(path)
  local f = assert(io.open(path, "rb"), "cannot open " .. tostring(path))
  local s = f:read("a")
  f:close()
  return s
end

local function write_file(path, s)
  local f = assert(io.open(path, "wb"), "cannot write " .. tostring(path))
  f:write(s)
  f:close()
end

function M.run(fn)
  local p = json.decode(read_file(app.params.params))
  local handler = (debug and debug.traceback) or tostring
  local ok, res = xpcall(function() return fn(p) end, handler)
  if ok then
    write_file(p.__out, json.encode({ ok = true, result = res or {} }))
  else
    write_file(p.__out, json.encode({ ok = false, error = tostring(res) }))
  end
end

------------------------------------------------------------------ sprites

function M.open(path)
  local s = app.open(path)
  assert(s, "could not open sprite: " .. tostring(path))
  app.sprite = s
  return s
end

-- Everything this server writes is an AI-generated placeholder. The property is the
-- machine-readable marker (see placeholder.py); the user data note is what a person sees
-- in Sprite > Properties. Existing user data is never overwritten.
M.PLACEHOLDER = "aseprite_mcp_placeholder"
M.NOTICE = "AI-generated placeholder asset (aseprite-mcp). Replace with final art before release."

function M.save(sprite, path)
  sprite.properties[M.PLACEHOLDER] = true
  if sprite.data == nil or sprite.data == "" then sprite.data = M.NOTICE end
  sprite:saveAs(path or sprite.filename)
end

M.MODES = { rgb = ColorMode.RGB, indexed = ColorMode.INDEXED, gray = ColorMode.GRAY }

function M.mode_name(m)
  if m == ColorMode.INDEXED then return "indexed" end
  if m == ColorMode.GRAY then return "gray" end
  return "rgb"
end

M.DIRS = {
  forward = AniDir.FORWARD,
  reverse = AniDir.REVERSE,
  pingpong = AniDir.PING_PONG,
  pingpong_reverse = AniDir.PING_PONG_REVERSE,
}

function M.dir_name(d)
  for k, v in pairs(M.DIRS) do
    if v == d then return k end
  end
  return "forward"
end

local function collect_layers(layers, out, prefix)
  for _, l in ipairs(layers) do
    out[#out + 1] = {
      name = l.name,
      path = prefix .. l.name,
      visible = l.isVisible,
      group = l.isGroup,
      tilemap = l.isTilemap or false,
      opacity = l.opacity,
    }
    if l.isGroup then collect_layers(l.layers, out, prefix .. l.name .. "/") end
  end
end

function M.find_layer(sprite, name)
  local function search(layers, prefix)
    for i = #layers, 1, -1 do
      local l = layers[i]
      if name == nil then
        if l.isGroup then
          local r = search(l.layers, prefix .. l.name .. "/")
          if r then return r end
        elseif l.isImage then
          return l
        end
      else
        if l.name == name or prefix .. l.name == name then return l end
        if l.isGroup then
          local r = search(l.layers, prefix .. l.name .. "/")
          if r then return r end
        end
      end
    end
  end
  local l = search(sprite.layers, "")
  assert(l, "layer not found: " .. tostring(name))
  return l
end

function M.info(s)
  local frames, layers, tags = {}, {}, {}
  for i, f in ipairs(s.frames) do
    frames[i] = { frame = i, duration_ms = math.floor(f.duration * 1000 + 0.5) }
  end
  collect_layers(s.layers, layers, "")
  for i, t in ipairs(s.tags) do
    tags[i] = {
      name = t.name,
      from = t.fromFrame.frameNumber,
      to = t.toFrame.frameNumber,
      direction = M.dir_name(t.aniDir),
    }
  end
  local pal = s.palettes[1]
  local colors = {}
  for i = 0, math.min(#pal, 256) - 1 do
    colors[#colors + 1] = M.hex(pal:getColor(i))
  end
  return {
    path = s.filename,
    width = s.width,
    height = s.height,
    color_mode = M.mode_name(s.colorMode),
    placeholder = s.properties[M.PLACEHOLDER] == true,
    frames = frames,
    layers = layers, -- bottom to top
    tags = tags,
    palette = colors,
  }
end

------------------------------------------------------------------ colors

function M.parse_hex(c)
  local hex = tostring(c):gsub("#", "")
  assert(#hex == 6 or #hex == 8, "bad color '" .. tostring(c) .. "' (use #rrggbb or #rrggbbaa)")
  local r = tonumber(hex:sub(1, 2), 16)
  local g = tonumber(hex:sub(3, 4), 16)
  local b = tonumber(hex:sub(5, 6), 16)
  local a = (#hex == 8) and tonumber(hex:sub(7, 8), 16) or 255
  return r, g, b, a
end

function M.hex(color)
  if color.alpha == 255 then
    return string.format("#%02x%02x%02x", color.red, color.green, color.blue)
  end
  return string.format("#%02x%02x%02x%02x", color.red, color.green, color.blue, color.alpha)
end

function M.palette_from(colors)
  local pal = Palette(#colors)
  for i, c in ipairs(colors) do
    local r, g, b, a = M.parse_hex(c)
    pal:setColor(i - 1, Color { r = r, g = g, b = b, a = a })
  end
  return pal
end

-- Convert "#rrggbb[aa]" (or a raw palette index number) into a pixel value for the sprite's mode.
function M.pixel(sprite, c)
  if type(c) == "number" then return c end
  local r, g, b, a = M.parse_hex(c)
  local mode = sprite.colorMode
  if mode == ColorMode.INDEXED then
    if a == 0 then return sprite.transparentColor end
    local pal = sprite.palettes[1]
    local best, bestd = 0, math.huge
    for i = 0, #pal - 1 do
      local pc = pal:getColor(i)
      local d = (pc.red - r) ^ 2 + (pc.green - g) ^ 2 + (pc.blue - b) ^ 2
      if d < bestd and i ~= sprite.transparentColor then best, bestd = i, d end
    end
    return best
  elseif mode == ColorMode.GRAY then
    local v = math.floor(0.299 * r + 0.587 * g + 0.114 * b + 0.5)
    return app.pixelColor.graya(v, a)
  end
  return app.pixelColor.rgba(r, g, b, a)
end

------------------------------------------------------------------ editing

-- Returns a full-canvas copy of the cel at (layer, frame) plus a commit() that writes it back.
function M.canvas(sprite, layer, frame_no)
  assert(sprite.frames[frame_no], "frame " .. tostring(frame_no) .. " does not exist (frames are 1-based)")
  assert(not layer.isTilemap, "drawing on tilemap layers is not supported; draw on a normal layer")
  assert(not layer.isGroup, "cannot draw on a group layer")
  local cel = layer:cel(frame_no)
  local img = Image(sprite.width, sprite.height, sprite.colorMode)
  img:clear()
  if cel then img:drawImage(cel.image, cel.position) end
  local function commit()
    if cel then
      cel.image = img
      cel.position = Point(0, 0)
    else
      sprite:newCel(layer, frame_no, img, Point(0, 0))
    end
  end
  return img, commit
end

return M
