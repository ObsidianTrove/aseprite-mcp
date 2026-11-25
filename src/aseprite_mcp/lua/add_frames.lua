-- Append frames (empty or copied from an existing frame) and/or set frame durations.
-- Params: path, count?, copy_from?, duration_ms?, duration_from?, duration_to?

local C = dofile(app.params.lib)

C.run(function(p)
  local s = C.open(p.path)
  local count = p.count or 0

  -- Aseprite extends a tag that ends on the last frame when frames are appended.
  -- Record existing tag ranges so appending never changes an existing animation.
  local ranges = {}
  for _, t in ipairs(s.tags) do
    ranges[#ranges + 1] = { t, t.fromFrame.frameNumber, t.toFrame.frameNumber }
  end

  local src = p.copy_from and s.frames[p.copy_from]
  assert(src or not p.copy_from, "copy_from frame does not exist (frames are 1-based)")
  for _ = 1, count do
    local f = s:newEmptyFrame(#s.frames + 1)
    if src then
      f.duration = src.duration
      for _, cel in ipairs(s.cels) do
        if cel.frameNumber == p.copy_from and not cel.layer.isTilemap then
          s:newCel(cel.layer, f.frameNumber, cel.image, cel.position)
        end
      end
    end
  end

  for _, r in ipairs(ranges) do
    r[1].fromFrame = r[2]
    r[1].toFrame = r[3]
  end

  if p.duration_ms then
    local from = p.duration_from or 1
    local to = p.duration_to or #s.frames
    for i = from, to do s.frames[i].duration = p.duration_ms / 1000 end
  end

  C.save(s)
  return C.info(s)
end)
