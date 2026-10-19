-- Bounded identity snapshot shared by server and client. No inventory mutation.
local M={}
function M.snapshot(inv)
 local rows,index,seen={},{},{}
 local function walk(container,path,depth)
  assert(depth<=4 and not seen[container],"inventory_depth_or_cycle")
  seen[container]=true
  local items=container:getItems()
  for i=0,items:size()-1 do
   assert(#rows<512,"inventory_limit")
   local item=items:get(i);local id=item:getID();local kind=tostring(item:getFullType())
   assert(type(id)=="number" and id==math.floor(id) and id>=-2147483648 and id<=2147483647,"invalid_item_id")
   assert(not index[tostring(id)],"duplicate_item_id")
   local row={id=id,kind=kind,path=path,condition=item:getCondition()}
   rows[#rows+1]=row;index[tostring(id)]={row=row,item=item,container=container}
   if item.getItemContainer then
    local nested=item:getItemContainer()
    if nested then walk(nested,path.."/"..tostring(id),depth+1)end
   end
  end
 end
 walk(inv,"main",0)
 return rows,index
end
function M.rows(rows)
 assert(type(rows)=="table" and #rows<=512,"invalid_snapshot")
 local index={}
 for _,row in ipairs(rows)do
  assert(type(row)=="table" and type(row.id)=="number" and row.id==math.floor(row.id)
   and row.id>=-2147483648 and row.id<=2147483647,"invalid_remote_id")
  assert(type(row.kind)=="string" and #row.kind<=96
   and row.kind:match("^[A-Za-z][A-Za-z0-9_]*%.[A-Za-z0-9_]+$"),"invalid_remote_type")
  assert(type(row.path)=="string" and #row.path<=96
   and (row.path=="main" or row.path:match("^main/[%d%-%/]+$")),"invalid_remote_path")
  assert(type(row.condition)=="number" and row.condition>=0 and row.condition<=100000,"invalid_condition")
  assert(not index[tostring(row.id)],"duplicate_remote_id");index[tostring(row.id)]=row
 end
 return index
end
return M
