-- Server-only root-issued, one-shot existing vehicle operations on story_test.
-- Never listens for client commands, never loads chunks, no arbitrary Lua input.
if isClient and isClient() then return end
local REQUEST="SiegerStoryVehicleRequest.txt"
local RESULT="SiegerStoryVehicleResult.txt"
local GUARD="SiegerStoryVehicleGuard.txt"
local tickCount=0
local processed=nil
local initialized=false
local ALLOWED={inspect=true,condition=true,fuel=true,battery=true,add=true,remove=true}
local TYPES={["Base.Bandage"]=true,["Base.WaterBottleEmpty"]=true,
    ["Base.Cigarettes"]=true,["Base.Pen"]=true,["Base.Pencil"]=true,
    ["Base.Lighter"]=true,["Base.Paperclip"]=true,["Base.Notebook"]=true,
    ["Base.Hammer"]=true,["Base.Screwdriver"]=true}
local function log(s) print("SIEGER_STORY_VEHICLE "..tostring(s)) end
local function fields(line)
    local out={}
    for str in (tostring(line or "").."\t"):gmatch("(.-)\t") do out[#out+1]=str end
    return out
end
local function token(s) return type(s)=="string" and #s==32 and s:match("^[0-9a-f]+$")~=nil end
local function number(s,min,max)
    local n=tonumber(s)
    if not n or n~=n or n<min or n>max then return nil end
    return n
end
local function safe(s)
    return tostring(s or ""):gsub("[^%w_.:-]","_"):sub(1,100)
end
local function write(id,operation,status,reason,detail)
    local out=getFileWriter(RESULT,true,false)
    if not out then error("result_writer_unavailable") end
    out:write(table.concat({"v1",id,"story_test",operation,status,safe(reason),
        safe(detail)},"\t").."\n")
    out:close()
end
local function exactCar(vehicleId,script,x,y,z)
    local cell=getCell()
    if not cell or not cell.getVehicles then error("vehicle_set_unavailable") end
    local collection=cell:getVehicles()
    if not collection or not collection.iterator then error("vehicle_iterator_unavailable") end
    local iter=collection:iterator()
    local found=nil
    local seen=0
    while iter:hasNext() do
        seen=seen+1
        if seen>256 then error("vehicle_scan_bound_exceeded") end
        local car=iter:next()
        if car and car:getId()==vehicleId then
            if found then error("duplicate_vehicle_id") end
            found=car
        end
    end
    if not found then error("vehicle_not_loaded") end
    if found:getScriptName()~=script then error("vehicle_script_mismatch") end
    if math.floor(found:getX())~=x or math.floor(found:getY())~=y
        or math.floor(found:getZ())~=z then error("vehicle_position_mismatch") end
    if not found.getPartById then error("part_lookup_unavailable") end
    return found
end
local function noPlayerInCar(car)
    local players=getOnlinePlayers()
    if not players then error("player_list_unavailable") end
    for i=0,players:size()-1 do
        local p=players:get(i)
        if p and p.getVehicle and p:getVehicle()==car then
            error("occupied_vehicle_refused")
        end
    end
end
local function checkGuard(id)
    local read=getFileReader(GUARD,false)
    if read then
        local line=read:readLine()
        read:close()
        if line==id then error("previous_mutation_uncertain") end
    end
    local w=getFileWriter(GUARD,true,false)
    if not w then error("guard_writer_unavailable") end
    w:write(id.."\n")
    w:close()
end
local function partFor(car,key)
    if not key:match("^[%w_]+$") or #key>50 then error("bad_part_id") end
    local p=car:getPartById(key)
    if not p or p:getId()~=key then error("part_missing") end
    return p
end
local function process(f)
    if not SiegerStoryScenes or SiegerStoryScenes.world~="story_test" then
        error("wrong_active_story_world") end
    local id,op,vehicleId,script=f[2],f[4],number(f[5],1,2147483647),f[6]
    local x,y,z=number(f[7],0,200000),number(f[8],0,200000),number(f[9],0,32)
    if not vehicleId or vehicleId~=math.floor(vehicleId)
        or not script:match("^Base%.[%w_]+$") or #script>90
        or not x or not y or not z or x~=math.floor(x) or y~=math.floor(y)
        or z~=math.floor(z) then error("invalid_identity") end
    local car=exactCar(vehicleId,script,x,y,z)
    local key,expected,value=f[10],f[11],f[12]
    local part=nil
    if op~="inspect" then
        noPlayerInCar(car)
        part=partFor(car,key)
    end
    if op=="inspect" then
        local tank=car:getPartById("GasTank")
        local battery=car:getPartById("Battery")
        local fuel=tank and tank.getContainerContentAmount and tank:getContainerContentAmount() or nil
        local bat=battery and battery:getInventoryItem()
        local charge=bat and bat.getUsedDelta and bat:getUsedDelta() or nil
        return "fuel_"..safe(fuel).."__battery_"..safe(charge),"inspect"
    elseif op=="condition" then
        local before=part:getCondition()
        local a,b=number(expected,0,100),number(value,0,100)
        if not a or not b or a~=math.floor(a) or b~=math.floor(b)
            or before~=a or not part.setCondition
            or not car.transmitPartCondition then error("part_condition_precheck_failed") end
        checkGuard(id)
        part:setCondition(b)
        car:transmitPartCondition(part)
        return "condition_"..b,key
    elseif op=="fuel" then
        if key~="GasTank" or not part.getContainerContentAmount
            or not part.setContainerContentAmount or not car.transmitPartModData
            or not part.getContainerCapacity then error("fuel_sync_api_unavailable") end
        local before=part:getContainerContentAmount()
        local a,b=number(expected,0,1000),number(value,0,1000)
        if not a or not b or math.abs(before-a)>0.001
            or b>part:getContainerCapacity() then error("fuel_precheck_failed") end
        checkGuard(id)
        part:setContainerContentAmount(b)
        car:transmitPartModData(part)
        return "fuel_"..b,key
    elseif op=="battery" then
        if key~="Battery" or not car.transmitPartUsedDelta then
            error("battery_sync_api_unavailable") end
        local item=part:getInventoryItem()
        if not item or not item.getUsedDelta or not item.setUsedDelta then
            error("battery_item_api_unavailable") end
        local a,b=number(expected,0,1),number(value,0,1)
        if not a or not b or math.abs(item:getUsedDelta()-a)>0.001 then
            error("battery_precheck_failed") end
        checkGuard(id)
        item:setUsedDelta(b)
        car:transmitPartUsedDelta(part)
        return "battery_"..b,key
    elseif op=="add" or op=="remove" then
        local container=part:getItemContainer()
        if not container or not container.getItems then error("container_not_found") end
        local items=container:getItems()
        if not items or items:size()>200 then error("container_bound_exceeded") end
        local typ=expected
        if not TYPES[typ] then error("item_not_allowlisted") end
        local count=number(value,1,5)
        if not count or count~=math.floor(count) then error("invalid_item_count") end
        local matches={}
        for i=0,items:size()-1 do
            local item=items:get(i)
            if item and item:getFullType()==typ then matches[#matches+1]=item end
        end
        if op=="remove" and #matches<count then error("insufficient_exact_items") end
        if op=="add" and (not container.AddItem or not sendAddItemToContainer) then
            error("add_sync_api_unavailable") end
        if op=="remove" and (not container.Remove or not sendRemoveItemFromContainer) then
            error("remove_sync_api_unavailable") end
        checkGuard(id)
        for i=1,count do
            if op=="add" then
                local item=container:AddItem(typ)
                if not item then error("item_add_failed_partial_review") end
                sendAddItemToContainer(container,item)
            else
                container:Remove(matches[i])
                sendRemoveItemFromContainer(container,matches[i])
            end
        end
        return op.."_"..count,key
    end
    error("unsupported_operation")
end
local function poll()
    if not initialized then
        local r=getFileReader(RESULT,false)
        if r then
            local f=fields(r:readLine())
            r:close()
            if f[1]=="v1" and token(f[2]) then processed=f[2] end
        end
        initialized=true
    end
    local r=getFileReader(REQUEST,false)
    if not r then return end
    local line=r:readLine()
    local extra=r:readLine()
    r:close()
    if not line or #line>400 or extra then return end
    local f=fields(line)
    if #f~=12 or f[1]~="v1" or not token(f[2]) or f[3]~="story_test"
        or not ALLOWED[f[4]] then return end
    if processed==f[2] then return end
    processed=f[2] -- never retry an ambiguous mutation within this process
    local ok,reason,detail=pcall(process,f)
    if not ok then
        log("FAILED request="..f[2].." reason="..safe(reason))
        reason,detail="manual_review_server_logs","-"
    end
    local saved,err=pcall(write,f[2],f[4],ok and "complete" or "error",reason,detail)
    if not saved then log("response_write_failed "..safe(err)) end
end
if Events and Events.OnTick then
    Events.OnTick.Add(function()
        tickCount=tickCount+1
        if tickCount%120==0 then
            local ok,err=pcall(poll)
            if not ok then log("poll_failed "..safe(err)) end
        end
    end)
else log("OnTick missing: vehicle control unavailable") end
