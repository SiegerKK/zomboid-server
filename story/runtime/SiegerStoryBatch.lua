-- Dedicated-server, root-issued typed batch edits. No client-originated
-- requests, arbitrary Lua evaluation or chunk loading. Any active Story world.
-- Preflight the complete plan before the FIRST mutation. No auto-rollback.
if isClient and isClient() then return end
local REQUEST="SiegerStoryBatchRequest.txt"
local RESULT="SiegerStoryBatchResult.txt"
local GUARD="SiegerStoryBatchGuard.txt"
local tickCount=0
local loaded=false
local processed=nil

local function log(m) print("SIEGER_STORY_BATCH "..tostring(m)) end
local function fields(line)
    local t,start={},1
    while true do
        local i=line:find("\t",start,true)
        if not i then t[#t+1]=line:sub(start);return t end
        t[#t+1]=line:sub(start,i-1);start=i+1
    end
end
local function idOk(id)
    return type(id)=="string" and #id==32 and id:match("^[0-9a-f]+$")~=nil
end
local function hashOk(s)
    return type(s)=="string" and #s==64 and s:match("^[0-9a-f]+$")~=nil
end
local function word(s)
    return type(s)=="string" and #s>0 and #s<=96
        and s:match("^[A-Za-z0-9_][A-Za-z0-9_.%-]*$")~=nil
end
local function typeName(s)
    return type(s)=="string" and #s<=96
        and s:match("^[A-Za-z][A-Za-z0-9_]*%.[A-Za-z][A-Za-z0-9_]*$")~=nil
end
local function value(s,lower,upper)
    local n=tonumber(s)
    if not n or n~=n or n==math.huge or n==-math.huge or n<lower or n>upper then
        error("invalid_numeric_value")
    end
    return n
end
local function integer(s,low,high)
    if type(s)~="string" then error("not_string") end
    local n=value(s,low,high)
    if n~=math.floor(n) or s:find("[^0-9%-]") then error("invalid_integer") end
    return n
end
local function ack(id,world,digest,state,applied,total,reason)
    local writer=getFileWriter(RESULT,true,false)
    if not writer then error("response_writer_unavailable") end
    writer:write(table.concat({"v1",id,world,digest,state,tostring(applied),
        tostring(total),reason},"\t").."\n")
    writer:close()
end
local function replayGuard(id,digest)
    local reader=getFileReader(GUARD,false)
    if reader then
        local previous=reader:readLine()
        reader:close()
        if previous==id.."\t"..digest then
            error("previous_mutation_uncertain")
        end
    end
    local writer=getFileWriter(GUARD,true,false)
    if not writer then error("mutation_guard_unavailable") end
    writer:write(id.."\t"..digest.."\n")
    writer:close()
end
local function loadedSquare(x,y,z)
    if not getCell then error("cell_unavailable") end
    local cell=getCell()
    if not cell or not cell.getGridSquare then error("square_api_unavailable") end
    local sq=cell:getGridSquare(x,y,z)
    if not sq then error("target_square_unloaded") end
    return sq
end
local function exactPlayer(username)
    if not word(username) or not getOnlinePlayers then error("player_api_unavailable") end
    local all=getOnlinePlayers()
    if not all then error("players_list_missing") end
    local found=nil
    for i=0,all:size()-1 do
        local p=all:get(i)
        if p and tostring(p:getUsername())==username then
            if found then error("duplicate_online_login") end
            found=p
        end
    end
    if not found then error("target_player_offline") end
    return found
end
local function exactCar(id,script,x,y,z)
    local cell=getCell()
    local all=cell and cell.getVehicles and cell:getVehicles()
    if not all or not all.iterator then error("vehicles_unavailable") end
    local iter=all:iterator()
    local found=nil
    while iter:hasNext() do
        local car=iter:next()
        if car and car:getId()==id then
            if found then error("duplicate_vehicle_id") end
            found=car
        end
    end
    if not found then error("vehicle_not_loaded") end
    if tostring(found:getScriptName())~=script then error("vehicle_script_changed") end
    if math.floor(found:getX())~=x or math.floor(found:getY())~=y
        or math.floor(found:getZ())~=z then error("vehicle_coordinates_changed") end
    return found
end
local function part(car,name)
    if not word(name) or not car.getPartById then error("part_api_unavailable") end
    local p=car:getPartById(name)
    if not p or tostring(p:getId())~=name then error("vehicle_part_not_found") end
    return p
end
local function exactContainer(sq,objIndex,selector,expected)
    local cIndex,mode=selector:match("^(%d+)([qs])$")
    if not cIndex then error("invalid_container_selector") end
    local objects=nil
    if mode=="q" then objects=sq:getObjects()
    elseif sq.getStaticMovingObjects then objects=sq:getStaticMovingObjects() end
    if not objects or objIndex>=objects:size() then error("world_container_missing") end
    local obj=objects:get(objIndex)
    if not obj then error("container_object_missing") end
    local index=integer(cIndex,0,2147483647)
    local c=nil
    if obj.getContainerByIndex then c=obj:getContainerByIndex(index)
    elseif index==0 and obj.getContainer then c=obj:getContainer() end
    if not c or tostring(c:getType())~=expected then
        error("container_type_or_index_changed")
    end
    return c
end
local function validItem(typeId)
    if not typeName(typeId) or not instanceItem then error("item_script_api_unavailable") end
    if not instanceItem(typeId) then error("item_script_missing") end
end
local function choose(items,typeId,count,reserved,unwrap,excluded)
    if not items or not items.size or not items.get then error("item_collection_missing") end
    local chosen={}
    for i=0,items:size()-1 do
        local obj=items:get(i)
        local actual=unwrap and obj and obj.getItem and obj:getItem() or obj
        if actual and actual.getFullType and
            tostring(actual:getFullType())==typeId and not reserved[obj] and
            not (excluded and excluded(actual)) then
            chosen[#chosen+1]=obj
            if #chosen==count then break end
        end
    end
    if #chosen~=count then error("insufficient_matching_items") end
    for _,item in ipairs(chosen) do reserved[item]=true end
    return chosen
end
local function inventory(c,op,typeId,count,reserved,excluded)
    if not c or not c.getItems then error("target_inventory_missing") end
    if op=="add" then
        if not c.AddItem or not sendAddItemToContainer then
            error("inventory_add_sync_missing") end
        validItem(typeId)
        return function()
            for i=1,count do
                local item=instanceItem(typeId)
                if not item then error("item_creation_failed") end
                local placed=c:AddItem(item)
                if not placed then error("item_add_failed") end
                sendAddItemToContainer(c,placed)
            end
        end
    end
    if not c.Remove or not sendRemoveItemFromContainer then
        error("inventory_remove_sync_missing") end
    local chosen=choose(c:getItems(),typeId,count,reserved,false,excluded)
    return function()
        for _,item in ipairs(chosen) do
            c:Remove(item)
            sendRemoveItemFromContainer(c,item)
        end
    end
end
local function ground(sq,selector,op,typeId,count,extra,reserved)
    local list=sq:getWorldObjects()
    if not list or not list.size or not list.get then
        error("ground_objects_unavailable") end
    if op=="add" then
        if selector~="-" or not sq.AddWorldInventoryItem then
            error("ground_add_api_missing") end
        local px,py,pz=extra:match("^([0-9.]+),([0-9.]+),([0-9.]+)$")
        if not px then error("ground_offset_invalid") end
        px,py,pz=value(px,0,1),value(py,0,1),value(pz,0,1)
        validItem(typeId)
        return function()
            for i=1,count do
                local item=instanceItem(typeId)
                if not item or not sq:AddWorldInventoryItem(item,px,py,pz) then
                    error("ground_add_failed") end
            end
        end
    end
    if extra~="-" or not sq.transmitRemoveItemFromSquare then
        error("ground_remove_sync_missing") end
    local selected={}
    if selector~="-" then
        if count~=1 then error("indexed_removal_must_be_one") end
        local idx=integer(selector,0,2147483647)
        local obj=idx<list:size() and list:get(idx) or nil
        local item=obj and obj.getItem and obj:getItem()
        if not item or tostring(item:getFullType())~=typeId or reserved[obj] then
            error("ground_index_or_item_changed") end
        reserved[obj]=true; selected={obj}
    else
        selected=choose(list,typeId,count,reserved,true,nil)
    end
    return function()
        for _,obj in ipairs(selected) do sq:transmitRemoveItemFromSquare(obj) end
    end
end
local function preflight(r,reserved,changed)
    if #r~=12 then error("wrong_batch_action_field_count") end
    local kind,id,script,x,y,z,selector,op,key,valueRaw,expected,extra=
        r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8],r[9],r[10],r[11],r[12]
    if kind=="vehicle" then
        if not typeName(script) then error("vehicle_script_invalid") end
        local car=exactCar(integer(id,1,2147483647),script,
            integer(x,0,200000),integer(y,0,200000),integer(z,-2,32))
        local p=part(car,selector)
        if op=="condition" then
            if key~="-" or extra~="-" or not p.setCondition or
                not car.transmitPartCondition then error("condition_sync_missing") end
            local before=integer(expected,0,100)
            local after=integer(valueRaw,0,100)
            if p:getCondition()~=before then error("part_condition_changed") end
            local address=id..":condition:"..selector
            if changed[address] then error("duplicate_part_edit") end
            changed[address]=true
            return function()p:setCondition(after);car:transmitPartCondition(p)end
        elseif op=="fuel" then
            if selector~="GasTank" or key~="-" or extra~="-" or
                not p.setContainerContentAmount or not p.getContainerCapacity or
                not car.transmitPartModData then error("fuel_sync_missing") end
            local before=value(expected,0,1000000)
            local after=value(valueRaw,0,1000000)
            if math.abs(p:getContainerContentAmount()-before)>.001 or
                after>p:getContainerCapacity() then error("fuel_precondition_changed") end
            local address=id..":fuel"
            if changed[address] then error("duplicate_fuel_edit") end
            changed[address]=true
            return function()p:setContainerContentAmount(after);car:transmitPartModData(p)end
        elseif op=="battery" then
            if selector~="Battery" or key~="-" or extra~="-" or
                not car.transmitPartUsedDelta then error("battery_sync_missing") end
            local item=p:getInventoryItem()
            if not item or not item.getCurrentUsesFloat or not item.setCurrentUsesFloat then
                error("battery_item_api_missing") end
            local before=value(expected,0,1)
            local after=value(valueRaw,0,1)
            if math.abs(item:getCurrentUsesFloat()-before)>.001 then
                error("battery_precondition_changed") end
            local address=id..":battery"
            if changed[address] then error("duplicate_battery_edit") end
            changed[address]=true
            return function()item:setCurrentUsesFloat(after);car:transmitPartUsedDelta(p)end
        elseif op=="add" or op=="remove" then
            if expected~="-" or extra~="-" or not typeName(key) then
                error("vehicle_container_edit_invalid") end
            return inventory(p:getItemContainer(),op,key,
                integer(valueRaw,1,2147483647),reserved,nil)
        end
        error("unknown_vehicle_edit")
    elseif kind=="player" then
        if script~="-" or x~="-" or y~="-" or z~="-" or selector~="-" then
            error("player_identity_fields_invalid") end
        local p=exactPlayer(id)
        if op=="heal" then
            if key~="-" or valueRaw~="0" or expected~="-" or extra~="-" then
                error("heal_payload_invalid") end
            local body=p:getBodyDamage()
            local parts=body and body:getBodyParts()
            if not parts or not parts.size then error("body_parts_unavailable") end
            for i=0,parts:size()-1 do
                local bp=parts:get(i)
                if not bp or not bp.RestoreToFullHealth then error("heal_api_unavailable") end
            end
            local address=id..":heal"
            if changed[address] then error("duplicate_heal") end
            changed[address]=true
            return function()
                for i=0,parts:size()-1 do parts:get(i):RestoreToFullHealth() end
            end
        elseif op=="stat" then
            if expected~="-" or extra~="-" then error("invalid_stat_payload") end
            local names={hunger="HUNGER",thirst="THIRST",fatigue="FATIGUE",stress="STRESS"}
            local enum=names[key] and CharacterStat and CharacterStat[names[key]]
            local stat=p:getStats()
            if not enum or not stat or not stat.set or not stat.get then
                error("player_stat_api_missing") end
            local after=value(valueRaw,0,1)
            local address=id..":"..key
            if changed[address] then error("duplicate_stat") end
            changed[address]=true
            return function()stat:set(enum,after);assert(math.abs(stat:get(enum)-after)<.0001,"stat_write_failed")end
        elseif op=="add" or op=="remove" then
            if expected~="-" or extra~="-" or not typeName(key) then
                error("player_inventory_edit_invalid") end
            return inventory(p:getInventory(),op,key,
                integer(valueRaw,1,2147483647),reserved,
                function(item)
                    return (p.getPrimaryHandItem and item==p:getPrimaryHandItem())
                        or (p.getSecondaryHandItem and item==p:getSecondaryHandItem())
                end)
        end
        error("unknown_player_edit")
    elseif kind=="container" then
        if not word(script) or not id:match("^%d+$") or
            expected~="-" or extra~="-" or (op~="add" and op~="remove")
            or not typeName(key) then error("world_container_edit_invalid") end
        local c=exactContainer(loadedSquare(integer(x,0,200000),
            integer(y,0,200000),integer(z,-2,32)),
            integer(id,0,2147483647),selector,script)
        return inventory(c,op,key,integer(valueRaw,1,2147483647),
            reserved,nil)
    elseif kind=="ground" then
        if id~="-" or script~="-" or expected~="-" or not typeName(key) or
            (op~="add" and op~="remove") then error("ground_edit_invalid") end
        local sq=loadedSquare(integer(x,0,200000),integer(y,0,200000),
            integer(z,-2,32))
        return ground(sq,selector,op,key,
            integer(valueRaw,1,2147483647),extra,reserved)
    end
    error("unknown_batch_target")
end
local function process(id,world,digest,actions)
    if not SiegerStoryScenes or SiegerStoryScenes.world~=world then
        error("active_story_world_mismatch") end
    local reserved,changed,operations={},{},{}
    -- Preflight every action before writing anything to the world.
    for _,action in ipairs(actions) do
        operations[#operations+1]=preflight(action,reserved,changed)
    end
    replayGuard(id,digest)
    local applied=0
    for _,apply in ipairs(operations) do
        local ok,err=pcall(apply)
        if not ok then
            log("PARTIAL id="..id.." applied="..applied.."/"..#operations..
                " reason="..tostring(err))
            return applied,"error","partial_possible"
        end
        applied=applied+1
    end
    return applied,"complete","server_applied"
end
local function poll()
    if not loaded then
        local r=getFileReader(RESULT,false)
        if r then
            local head=fields(r:readLine() or "")
            r:close()
            if head[1]=="v1" and idOk(head[2]) then processed=head[2] end
        end
        loaded=true
    end
    local reader=getFileReader(REQUEST,false)
    if not reader then return end
    local first=reader:readLine()
    if not first or #first>256 then reader:close();return end
    local head=fields(first)
    if #head~=5 or head[1]~="v1" or not idOk(head[2]) or
        not word(head[3]) or not hashOk(head[4]) or
        not head[5]:match("^%d+$") then reader:close();return end
    if processed==head[2] then reader:close();return end
    local count=integer(head[5],1,4096)
    local actions={}
    local readOk,readError=pcall(function()
        for i=1,count do
            local line=reader:readLine()
            if not line or #line>400 then error("malformed_batch_row") end
            local cells=fields(line)
            if #cells~=12 then error("invalid_action_columns") end
            actions[i]=cells
        end
        if reader:readLine() then error("extra_batch_rows") end
    end)
    reader:close()
    processed=head[2]
    if not readOk then
        log("ERROR malformed request "..head[2].." "..tostring(readError))
        pcall(ack,head[2],head[3],head[4],"error",0,count,"malformed_request")
        return
    end
    local ok,done,state,reason=pcall(process,head[2],head[3],head[4],actions)
    if not ok then
        log("ERROR preflight "..head[2].." "..tostring(done))
        done,state,reason=0,"error","preflight_failed"
    end
    if not pcall(ack,head[2],head[3],head[4],state,done,count,reason) then
        log("ERROR failed writing batch receipt "..head[2])
    end
end
if Events and Events.OnTick then
    Events.OnTick.Add(function()
        tickCount=tickCount+1
        if tickCount%120==0 then
            local ok,err=pcall(poll)
            if not ok then log("ERROR batch poll "..tostring(err))end
        end
    end)
else log("ERROR OnTick missing; batch disabled")end
