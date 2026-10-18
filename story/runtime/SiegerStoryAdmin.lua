-- Root-owned typed batch admin for the selected ACTIVE Story-enabled world.
-- No client commands, arbitrary Lua, dynamic code loading or forced chunks.
-- Two phases: preflight EVERY action, write durable attempt guard, then apply.
-- Network/game changes are NOT transactional: a failure after guard needs audit.
if isClient and isClient() then return end
local REQUEST="SiegerStoryAdminRequest.txt"
local RESULT="SiegerStoryAdminResult.txt"
local GUARD="SiegerStoryAdminGuard.txt"
local tick,initialized,processed=0,false,nil
local function log(s) print("SIEGER_STORY_ADMIN "..tostring(s)) end
local function split(line)
    local parts,first={},1
    while true do
        local n=line:find("\t",first,true)
        if not n then parts[#parts+1]=line:sub(first);return parts end
        parts[#parts+1]=line:sub(first,n-1);first=n+1
    end
end
local function validId(s)
    return type(s)=="string" and #s==32 and s:match("^[0-9a-f]+$")~=nil
end
local function validHash(s)
    return type(s)=="string" and #s==64 and s:match("^[0-9a-f]+$")~=nil
end
local function word(s)
    return type(s)=="string" and #s>0 and #s<=96
        and s:match("^[A-Za-z0-9_][A-Za-z0-9_.%-]*$")~=nil
end
local function itemName(s)
    return type(s)=="string" and #s<=96 and
        s:match("^[A-Za-z][A-Za-z0-9_]*%.[A-Za-z][A-Za-z0-9_]*$")~=nil
end
local function int(s,min,max)
    if type(s)~="string" or not s:match("^%d+$") then error("non_integer") end
    local n=tonumber(s)
    if not n or n~=math.floor(n) or n<min or (max and n>max) then
        error("invalid_integer") end
    return n
end
local function num(s,min,max)
    local n=tonumber(s)
    if not n or n~=n or n==math.huge or n==-math.huge or n<min or n>max then
        error("invalid_number") end
    return n
end
local function makeAck(id,world,hash,status,done,count,reason)
    local writer=getFileWriter(RESULT,true,false)
    if not writer then error("no_admin_response_writer") end
    writer:write(table.concat({"v2",id,world,hash,status,
        tostring(done),tostring(count),reason},"\t").."\n")
    writer:close()
end
local function loadGuard()
    local r=getFileReader(GUARD,false)
    if not r then return nil end
    local line=r:readLine();r:close()
    return line
end
local function guard(id,hash)
    if loadGuard()==id.."\t"..hash then error("uncertain_replay_refused") end
    local w=getFileWriter(GUARD,true,false)
    if not w then error("guard_not_writable") end
    w:write(id.."\t"..hash.."\n");w:close()
end
local function square(x,y,z)
    local cell=getCell()
    if not cell or not cell.getGridSquare then error("cell_api_unavailable") end
    local sq=cell:getGridSquare(x,y,z)
    if not sq then error("target_square_not_loaded") end
    return sq
end
local function players()
    if not getOnlinePlayers then error("online_player_api_missing") end
    local p=getOnlinePlayers()
    if not p or not p.size or not p.get then error("online_list_unavailable") end
    return p
end
local function player(username)
    local all=players()
    local result=nil
    for i=0,all:size()-1 do
        local p=all:get(i)
        if p and tostring(p:getUsername())==username then
            if result then error("duplicate_online_player") end
            result=p
        end
    end
    if not result then error("player_not_online") end
    return result
end
local function vehicle(id,script,x,y,z)
    local cell=getCell()
    if not cell or not cell.getVehicles then error("loaded_vehicle_api_missing") end
    local cars=cell:getVehicles()
    if not cars or not cars.iterator then error("vehicle_iterator_unavailable") end
    local iterator=cars:iterator()
    local found=nil
    while iterator:hasNext() do
        local car=iterator:next()
        if car and car:getId()==id then
            if found then error("duplicate_vehicle_id") end
            found=car
        end
    end
    if not found then error("vehicle_not_loaded") end
    if tostring(found:getScriptName())~=script then error("vehicle_script_mismatch") end
    if math.floor(found:getX())~=x or math.floor(found:getY())~=y or
        math.floor(found:getZ())~=z then error("vehicle_moved_or_position_mismatch") end
    return found
end
local function part(car,id)
    if not word(id) or not car.getPartById then error("part_id_invalid") end
    local p=car:getPartById(id)
    if not p or tostring(p:getId())~=id then error("missing_exact_vehicle_part") end
    return p
end
local function containerAt(sq,index,containerIndex,kind,expectedType)
    local objects=nil
    if kind=="s" then
        if not sq.getStaticMovingObjects then error("static_objects_unavailable") end
        objects=sq:getStaticMovingObjects()
    else
        if not sq.getObjects then error("square_objects_unavailable") end
        objects=sq:getObjects()
    end
    if not objects or index>=objects:size() then error("container_object_missing") end
    local obj=objects:get(index)
    if not obj then error("container_object_null") end
    local c=nil
    if obj.getContainerByIndex then c=obj:getContainerByIndex(containerIndex)
    elseif containerIndex==0 and obj.getContainer then c=obj:getContainer() end
    if not c or tostring(c:getType())~=expectedType then
        error("container_type_or_index_changed") end
    return c
end
local function validItem(fullType)
    if not itemName(fullType) or not instanceItem then error("item_script_unavailable") end
    -- Instance creation here has no game-world side effects; verifies actual
    -- installed item scripts, not a hard-coded test-world item allowlist.
    local sample=instanceItem(fullType)
    if not sample then error("item_script_not_installed") end
end
local function reserve(reserved,object)
    if reserved[object] then error("same_item_removed_twice") end
    reserved[object]=true
end
local function removeObjects(items,fullType,count,reserved,excluded)
    if not items or not items.size or not items.get then error("items_missing") end
    local matches={}
    for i=0,items:size()-1 do
        local obj=items:get(i)
        local item=obj and (obj.getItem and obj:getItem() or obj)
        if item and item.getFullType and tostring(item:getFullType())==fullType
            and not reserved[obj] and not (excluded and excluded(item)) then
            matches[#matches+1]=obj
            if #matches==count then break end
        end
    end
    if #matches~=count then error("missing_or_equipped_matching_items") end
    for _,obj in ipairs(matches) do reserve(reserved,obj) end
    return matches
end
local function inventoryTask(c,verb,fullType,count,reserved,excluded)
    if not c or not c.getItems then error("inventory_api_missing") end
    if verb=="add" then
        if not c.AddItem or not sendAddItemToContainer then
            error("inventory_add_sync_api_missing") end
        validItem(fullType)
        return function()
            for i=1,count do
                local new=instanceItem(fullType)
                if not new then error("item_spawn_failed") end
                local placed=c:AddItem(new)
                if not placed then error("container_add_failed") end
                sendAddItemToContainer(c,placed)
            end
        end
    end
    if not c.Remove or not sendRemoveItemFromContainer then
        error("inventory_remove_sync_api_missing") end
    local matches=removeObjects(c:getItems(),fullType,count,reserved,excluded)
    return function()
        for _,item in ipairs(matches) do
            c:Remove(item)
            sendRemoveItemFromContainer(c,item)
        end
    end
end
local function groundTask(sq,selector,verb,fullType,count,extra,reserved)
    local ground=sq:getWorldObjects()
    if not ground or not ground.size or not ground.get then
        error("world_object_list_unavailable") end
    if verb=="add" then
        if not sq.AddWorldInventoryItem then error("world_item_spawn_unavailable") end
        local px,py,pz=extra:match("^([0-9.]+),([0-9.]+),([0-9.]+)$")
        if not px then error("invalid_ground_offset") end
        px,py,pz=num(px,0,1),num(py,0,1),num(pz,0,1)
        validItem(fullType)
        return function()
            for i=1,count do
                local item=instanceItem(fullType)
                if not item or not sq:AddWorldInventoryItem(item,px,py,pz) then
                    error("ground_spawn_failed") end
            end
        end
    end
    if not sq.transmitRemoveItemFromSquare then
        error("world_remove_sync_api_missing") end
    local matches={}
    if selector~="-" then
        if count~=1 then error("indexed_ground_remove_requires_one") end
        local index=int(selector,0)
        local obj=index<ground:size() and ground:get(index) or nil
        local item=obj and obj.getItem and obj:getItem()
        if not item or tostring(item:getFullType())~=fullType then
            error("ground_index_or_type_changed") end
        matches={obj};reserve(reserved,obj)
    else
        matches=removeObjects(ground,fullType,count,reserved,nil)
    end
    return function()
        for _,obj in ipairs(matches) do sq:transmitRemoveItemFromSquare(obj) end
    end
end
local statNames={
    hunger={"getHunger","setHunger"},thirst={"getThirst","setThirst"},
    fatigue={"getFatigue","setFatigue"},stress={"getStress","setStress"}
}
local function makeTask(row,reserved,changed)
    if #row~=13 or row[1]~="a" then error("invalid_action_fields") end
    local kind,id,script,x,y,z,selector,verb,key,value,expect,extra=
        row[2],row[3],row[4],row[5],row[6],row[7],row[8],row[9],
        row[10],row[11],row[12],row[13]
    if (verb~="add" and verb~="remove" and verb~="condition"
        and verb~="fuel" and verb~="battery" and verb~="stat" and verb~="heal") then
        error("unsupported_admin_verb") end
    if kind=="vehicle" then
        if not itemName(script) then error("invalid_vehicle_script") end
        local car=vehicle(int(id,1),script,int(x,0),int(y,0),int(z,0))
        local partId=selector
        local p=part(car,partId)
        if verb=="condition" then
            if key~="-" or extra~="-" or not p.getCondition or not p.setCondition
                or not car.transmitPartCondition then error("condition_sync_api_missing") end
            local to,from=int(value,0,100),int(expect,0,100)
            if p:getCondition()~=from then error("condition_precondition_changed") end
            local address=id..":condition:"..partId
            if changed[address] then error("duplicate_vehicle_property") end
            changed[address]=true
            return function()p:setCondition(to);car:transmitPartCondition(p)end
        elseif verb=="fuel" then
            if partId~="GasTank" or key~="-" or extra~="-" or
                not p.getContainerContentAmount or not p.setContainerContentAmount or
                not p.getContainerCapacity or not car.transmitPartModData then
                error("fuel_sync_api_missing") end
            local to,from=num(value,0,1000000),num(expect,0,1000000)
            if to>p:getContainerCapacity() or math.abs(p:getContainerContentAmount()-from)>.001 then
                error("fuel_precondition_or_capacity_changed") end
            local address=id..":fuel:"..partId
            if changed[address] then error("duplicate_vehicle_property") end
            changed[address]=true
            return function()p:setContainerContentAmount(to);car:transmitPartModData(p)end
        elseif verb=="battery" then
            if partId~="Battery" or key~="-" or extra~="-" or
                not car.transmitPartUsedDelta or not p.getInventoryItem then
                error("battery_sync_api_missing") end
            local item=p:getInventoryItem()
            if not item or not item.getCurrentUsesFloat or not item.setCurrentUsesFloat then
                error("battery_item_api_missing") end
            local to,from=num(value,0,1),num(expect,0,1)
            if math.abs(item:getCurrentUsesFloat()-from)>.001 then
                error("battery_precondition_changed") end
            local address=id..":battery:"..partId
            if changed[address] then error("duplicate_vehicle_property") end
            changed[address]=true
            return function()item:setCurrentUsesFloat(to);car:transmitPartUsedDelta(p)end
        elseif verb=="add" or verb=="remove" then
            if extra~="-" or expect~="-" or not itemName(key) or not p.getItemContainer then
                error("vehicle_container_request_invalid") end
            return inventoryTask(p:getItemContainer(),verb,key,int(value,1),
                reserved,nil)
        end
        error("vehicle_operation_unsupported")
    elseif kind=="player" then
        if script~="-" or x~="-" or y~="-" or z~="-" or selector~="-" then
            error("invalid_player_fields") end
        local p=player(id)
        if verb=="heal" then
            if key~="-" or value~="0" or expect~="-" or extra~="-" then
                error("invalid_heal_fields") end
            local body=p:getBodyDamage()
            local parts=body and body:getBodyParts()
            if not parts or not parts.size or not parts.get then error("body_parts_api_missing") end
            for i=0,parts:size()-1 do
                local bp=parts:get(i)
                if not bp or not bp.RestoreToFullHealth then
                    error("healing_api_missing") end
            end
            local address="player:"..id..":heal"
            if changed[address] then error("duplicate_heal")end
            changed[address]=true
            return function()
                for i=0,parts:size()-1 do parts:get(i):RestoreToFullHealth() end
            end
        elseif verb=="stat" then
            if expect~="-" or extra~="-" or not statNames[key] then
                error("unsupported_player_stat") end
            local to=num(value,0,1)
            local stat=p:getStats()
            local getter,setter=statNames[key][1],statNames[key][2]
            if not stat or not stat[setter] then error("player_stat_setter_unavailable") end
            local address="player:"..id..":"..key
            if changed[address] then error("duplicate_player_stat")end
            changed[address]=true
            return function()stat[setter](stat,to)end
        elseif verb=="add" or verb=="remove" then
            if not itemName(key) or expect~="-" or extra~="-" then
                error("invalid_player_item_request") end
            return inventoryTask(p:getInventory(),verb,key,int(value,1),reserved,
                function(item)
                    return (p.getPrimaryHandItem and item==p:getPrimaryHandItem())
                        or (p.getSecondaryHandItem and item==p:getSecondaryHandItem())
                end)
        end
        error("player_operation_unsupported")
    elseif kind=="container" then
        if not word(script) or not id:match("^%d+$") then error("container_identity_invalid") end
        local idx,collection=selector:match("^(%d+)([qs])$")
        if not idx or (verb~="add" and verb~="remove") or
            not itemName(key) or expect~="-" or extra~="-" then
            error("container_selector_invalid") end
        local c=containerAt(square(int(x,0),int(y,0),int(z,0)),int(id,0),
                            int(idx,0),collection,script)
        return inventoryTask(c,verb,key,int(value,1),reserved,nil)
    elseif kind=="ground" then
        if id~="-" or script~="-" or not itemName(key) or
            expect~="-" or (verb~="add" and verb~="remove") then
            error("ground_action_invalid") end
        local sq=square(int(x,0),int(y,0),int(z,0))
        local count=int(value,1)
        if verb=="remove" and extra~="-" then error("invalid_ground_remove") end
        return groundTask(sq,selector,verb,key,count,extra,reserved)
    end
    error("unknown_action_target")
end
local function process(id,world,hash,rows)
    if not SiegerStoryScenes or SiegerStoryScenes.world~=world then
        error("active_world_mismatch") end
    -- No whitelist on active world, item script, inventory, vehicle occupancy
    -- or number of part/container operations; source must be loaded in game.
    local reserved,changed,tasks={},{},{}
    for _,fields in ipairs(rows) do
        tasks[#tasks+1]=makeTask(fields,reserved,changed)
    end
    -- Mark BEFORE first mutation. No automatic replay after partial failure.
    guard(id,hash)
    local done=0
    for _,apply in ipairs(tasks) do
        local ok,err=pcall(apply)
        if not ok then
            log("PARTIAL id="..id.." completed="..done.."/"..#tasks.." error="..tostring(err))
            return done,"error","partial_possible"
        end
        done=done+1
    end
    return done,"complete","server_applied"
end
local function poll()
    if not initialized then
        local r=getFileReader(RESULT,false)
        if r then
            local fields=split(r:readLine() or "")
            r:close()
            if fields[1]=="v2" and validId(fields[2]) then processed=fields[2] end
        end
        initialized=true
    end
    local reader=getFileReader(REQUEST,false)
    if not reader then return end
    local header=reader:readLine()
    if not header or #header>240 then reader:close();return end
    local h=split(header)
    if #h~=5 or h[1]~="v2" or not validId(h[2]) or
        not word(h[3]) or not validHash(h[4]) or
        not h[5]:match("^%d+$") then reader:close();return end
    if processed==h[2] then reader:close();return end
    local n=int(h[5],1,4096)
    local rows={}
    local ok,err=pcall(function()
        for i=1,n do
            local line=reader:readLine()
            if not line or #line>350 then error("invalid_admin_action_line") end
            local fields=split(line)
            if #fields~=13 then error("invalid_admin_action_columns") end
            rows[i]=fields
        end
        if reader:readLine()~=nil then error("unexpected_extra_admin_actions") end
    end)
    reader:close()
    processed=h[2]
    if not ok then
        log("ERROR request="..h[2].." error="..tostring(err))
        pcall(makeAck,h[2],h[3],h[4],"error",0,n,"malformed_request")
        return
    end
    local fine,applied,status,reason=pcall(process,h[2],h[3],h[4],rows)
    if not fine then
        log("ERROR request="..h[2].." "..tostring(applied))
        applied,status,reason=0,"error","preflight_or_guard"
    end
    local yes,why=pcall(makeAck,h[2],h[3],h[4],status,applied,n,reason)
    if not yes then log("ERROR unable to write admin ACK "..tostring(why)) end
end
if Events and Events.OnTick then
    Events.OnTick.Add(function()
        tick=tick+1
        if tick%120==0 then
            local ok,err=pcall(poll)
            if not ok then log("ERROR polling admin batch "..tostring(err)) end
        end
    end)
else log("ERROR no OnTick: batch editing disabled") end
