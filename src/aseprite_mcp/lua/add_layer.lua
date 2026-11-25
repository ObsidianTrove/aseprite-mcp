-- Add a layer or layer group on top of the stack, optionally inside an existing group.
-- Params: path, name, group?, opacity?, parent?

local C = dofile(app.params.lib)

C.run(function(p)
  local s = C.open(p.path)
  local l
  if p.group then l = s:newGroup() else l = s:newLayer() end
  l.name = p.name
  if p.opacity then l.opacity = p.opacity end
  if p.parent then l.parent = C.find_layer(s, p.parent) end
  C.save(s)
  return C.info(s)
end)
