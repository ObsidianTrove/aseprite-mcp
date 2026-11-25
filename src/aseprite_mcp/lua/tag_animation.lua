-- Create (or replace) a named animation tag over a frame range.
-- Params: path, name, from_frame, to_frame, direction?, repeat?

local C = dofile(app.params.lib)

C.run(function(p)
  local s = C.open(p.path)
  for _, t in ipairs(s.tags) do
    if t.name == p.name then
      s:deleteTag(t)
      break
    end
  end
  assert(
    s.frames[p.from_frame] and s.frames[p.to_frame],
    "tag frame range out of bounds (frames are 1-based)"
  )
  local t = s:newTag(p.from_frame, p.to_frame)
  t.name = p.name
  t.aniDir = C.DIRS[p.direction or "forward"] or AniDir.FORWARD
  if p["repeat"] and p["repeat"] > 0 then t.repeats = p["repeat"] end
  C.save(s)
  return C.info(s)
end)
