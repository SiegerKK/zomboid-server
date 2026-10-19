-- Sieger Story Director: root-file-driven player administration for story_test.
-- No client commands, arbitrary Lua/RCON code, timers, or continuous inventory sweeps.
-- B42 multiplayer synchronization of health remains experimental.
if isClient and isClient() then return end

local REQUEST="SiegerStoryPlayerRequest.txt"
local RESPONSE="SiegerStoryPlayerResult.txt"
local GUARD="SiegerStoryPlayerGuard.txt"
local tickNumber=0
local processed=nil
local loaded=false
local MAX_ITEMS=256
local TYPES={["Base.Bandage"]=true,["Base.Disinfectant"]=true,
    ["Base.RippedSheets"]=true,["Base.Notebook"]=true,
    ["Base.Plank"]=true,["Base.Hammer"]=true,
    ["Base.Screwdriver"]=true,["Base.WaterBottleFull"]=true}

local function log(msg)
    print("SIEGER_STORY_PLAYER "..tostring(msg))
end
local function split(line)
    local t,start={},1
    while true do
        local i=line:find("\t",start,true)
        if not i then t[#t+1]=line:sub(start);return t end
        t[#t+1]=line:sub(start,i-1);start=i+1
    end
end
local function validName(s)
    return type(s)=="string" and #s<=40 and #s>=1
        and s:match("^[A-Za-z0-9_][A-Za-z0-9_.%-]*$")~=nil
end
local function validID(s)
    return type(s)=="string" and #s==32 and s:match("^[0-9a-f]+$")~=nil
end
local function clean(s)
    s=tostring(s or "")
    if #s>180 or s:find("[\t\r\n]") then error("Invalid player response field") end
    return s
end
local function writeResult(id,world,user,operation,status,fields,items,message)
    local writer=getFileWriter(RESPONSE,true,false)
    if not writer then error("Player response writer missing") end
    local ok,err=pcall(function()
        writer:write(table.concat({"v1",id,world,user,operation,status,clean(message)},"\t").."\n")
        for _,field in ipairs(fields or {}) do
            writer:write("field\t"..clean(field[1]).."\t"..clean(field[2]).."\n")
        end
        for _,item in ipairs(items or {}) do
            writer:write("item\t"..clean(item[1]).."\t"..clean(item[2]).."\t"..
                clean(item[3]).."\n")
        end
        writer:write("end\n")
    end)
    writer:close()
    if not ok then error(err) end
end
local function findOnline(username)
    local users=getOnlinePlayers()
    if not users then return nil end
    for i=0,users:size()-1 do
        local p=users:get(i)
        if p and tostring(p:getUsername())==username then return p end
    end
    return nil
end
local function optionalMetric(fields,key,fn)
    local ok,value=pcall(fn)
    if ok and type(value)=="number" and value==value and
        math.abs(value)<10000000 then
        fields[#fields+1]={key,tostring(value)}
    else
        fields[#fields+1]={key,"unavailable"}
    end
end
local function inspect(player)
    local fields,items={},{}
    optionalMetric(fields,"x",function()return player:getX()end)
    optionalMetric(fields,"y",function()return player:getY()end)
    optionalMetric(fields,"z",function()return player:getZ()end)
    optionalMetric(fields,"health",function()return player:getBodyDamage():getOverallBodyHealth()end)
    optionalMetric(fields,"hunger",function()return player:getStats():get(CharacterStat.HUNGER)end)
    optionalMetric(fields,"thirst",function()return player:getStats():get(CharacterStat.THIRST)end)
    optionalMetric(fields,"fatigue",function()return player:getStats():get(CharacterStat.FATIGUE)end)
    optionalMetric(fields,"stress",function()return player:getStats():get(CharacterStat.STRESS)end)
    local inventory=player:getInventory()
    if not inventory then error("No player inventory") end
    local content=inventory:getItems()
    if not content then error("No player inventory item collection") end
    if content:size()>MAX_ITEMS then error("Inventory exceeds bounded admin report") end
    fields[#fields+1]={"inventory_scope","top_level_only"}
    fields[#fields+1]={"inventory_count",tostring(content:size())}
    for i=0,content:size()-1 do
        local item=content:get(i)
        if item then
            local fullType=tostring(item:getFullType())
            local md=item:getModData()
            local token=md and md.SiegerStoryToken or "-"
            items[#items+1]={tostring(i),fullType,tostring(token)}
        end
    end
    local ok,bodyParts=pcall(function()return player:getBodyDamage():getBodyParts()end)
    if ok and bodyParts and bodyParts:size()<=128 then
        local injured=0
        for i=0,bodyParts:size()-1 do
            local part=bodyParts:get(i)
            local okH,h=pcall(function()return part:getHealth()end)
            if okH and type(h)=="number" and h<100 then injured=injured+1 end
        end
        fields[#fields+1]={"injured_body_parts",tostring(injured)}
    else
        fields[#fields+1]={"injured_body_parts","unavailable"}
    end
    return fields,items
end
local function guardAttempt(id,world,user,operation)
    local writer=getFileWriter(GUARD,true,false)
    if not writer then error("Player mutation guard writer unavailable") end
    writer:write(table.concat({id,world,user,operation},"\t").."\n")
    writer:close()
end
local function priorGuard(id)
    local reader=getFileReader(GUARD,false)
    if not reader then return false end
    local line=reader:readLine()
    reader:close()
    return line and line:sub(1,32)==id
end
local function grant(player,id,world,user,itemType,count)
    if not TYPES[itemType] or count<1 or count>5 then error("Item grant not allowlisted") end
    if not sendAddItemToContainer then error("Inventory sync method unavailable") end
    local inventory=player:getInventory()
    if not inventory then error("Player has no inventory") end
    -- Preflight all items before irreversible mutation.
    local instances={}
    for i=1,count do
        local item=instanceItem(itemType)
        if not item then error("Unavailable item script: "..itemType) end
        local md=item:getModData()
        if not md then error("Item has no modData") end
        md.SiegerStoryToken="SiegerStory:admin_player_ops:grant_item:"..id..":"..i
        md.SiegerStoryQuest="admin_player_ops"
        md.SiegerStoryAction="grant_item"
        md.SiegerStoryKind="item"
        instances[i]=item
    end
    guardAttempt(id,world,user,"grant")
    for _,item in ipairs(instances) do
        local added=inventory:AddItem(item)
        if not added then error("Inventory AddItem failed; inspect guard before retry") end
        sendAddItemToContainer(inventory,added)
    end
    return {{"granted_type",itemType},{"granted_count",tostring(count)}}
end
local function removeTagged(player,id,world,user,token)
    if #token<18 or #token>180 or not token:match("^SiegerStory:[A-Za-z0-9_:.-]+$") then
        error("Only a specific Story-owned token may be removed")
    end
    if not sendRemoveItemFromContainer then error("Inventory remove sync unavailable") end
    local inv=player:getInventory()
    if not inv then error("No player inventory") end
    local items=inv:getItems()
    local found=nil
    for i=0,items:size()-1 do
        local candidate=items:get(i)
        local md=candidate and candidate:getModData()
        if md and md.SiegerStoryToken==token then
            if found then error("Multiple items share Story token") end
            found=candidate
        end
    end
    if not found then error("Story-tagged item not found in top-level inventory") end
    if found==player:getPrimaryHandItem() or found==player:getSecondaryHandItem() then
        error("Unequip this item before removing it")
    end
    guardAttempt(id,world,user,"remove-tagged")
    inv:Remove(found)
    sendRemoveItemFromContainer(inv,found)
    return {{"removed_token",token}}
end
local function heal(player,id,world,user)
    local body=player:getBodyDamage()
    if not body then error("BodyDamage unavailable") end
    local parts=body:getBodyParts()
    if not parts or parts:size()<1 or parts:size()>128 then
        error("Body parts unavailable/invalid")
    end
    -- Explicitly experimental: do not infer MP synchronization from local call.
    for i=0,parts:size()-1 do
        local part=parts:get(i)
        if not part or not part.RestoreToFullHealth then
            error("RestoreToFullHealth unavailable in game VM")
        end
    end
    guardAttempt(id,world,user,"heal")
    for i=0,parts:size()-1 do parts:get(i):RestoreToFullHealth()end
    return {{"health_action","restored_body_parts"},{"count",tostring(parts:size())},
            {"sync","experimental_verify_client"}}
end
local function process(id,world,user,operation,arg,count)
    if not SiegerStoryScenes or SiegerStoryScenes.world~=world or world~="story_test" then
        error("World mismatch; only active story_test is allowed")
    end
    local player=findOnline(user)
    if not player then error("Player not online") end
    if operation=="inspect" then return inspect(player) end
    if priorGuard(id) then error("Previous mutation attempt uncertain; manual review") end
    if operation=="grant" then return grant(player,id,world,user,arg,count),{} end
    if operation=="remove-tagged" then
        return removeTagged(player,id,world,user,arg),{}
    end
    if operation=="heal" then return heal(player,id,world,user),{} end
    error("Unsupported player operation")
end
local function poll()
    if not loaded then
        local reader=getFileReader(RESPONSE,false)
        if reader then
            local head=reader:readLine()
            reader:close()
            if head then
                local row=split(head)
                if row[1]=="v1" and validID(row[2]) then processed=row[2] end
            end
        end
        loaded=true
    end
    local reader=getFileReader(REQUEST,false)
    if not reader then return end
    local line=reader:readLine()
    local extra=reader:readLine()
    reader:close()
    if not line or #line>256 or extra then return end
    local row=split(line)
    if #row~=7 or row[1]~="v1" or not validID(row[2])
        or not validName(row[3]) or not validName(row[4]) then return end
    local id,world,user,operation,arg,count=row[2],row[3],row[4],row[5],row[6],tonumber(row[7])
    if id==processed or count==nil or count~=math.floor(count) then return end
    if (operation=="inspect" and (arg~="-" or count~=0)) or
        (operation=="heal" and (arg~="-" or count~=0)) or
        (operation=="remove-tagged" and count~=1) or
        (operation=="grant" and (count<1 or count>5 or not TYPES[arg])) or
        (operation~="inspect" and operation~="heal" and operation~="remove-tagged"
            and operation~="grant") then return end
    -- Mark this request in memory before mutation; on error report an explicit failure.
    processed=id
    local ok,fields,items=pcall(process,id,world,user,operation,arg,count)
    local status=ok and "complete" or "error"
    local message=ok and "server_ack" or "server_side_error_review_logs"
    if not ok then fields={} end
    if not ok then items={} end
    local saved,err=pcall(writeResult,id,world,user,operation,status,fields,items,message)
    if not saved then log("ERROR report write failed "..tostring(err))end
end
local function tick()
    tickNumber=tickNumber+1
    if tickNumber%120==0 then
        local ok,err=pcall(poll)
        if not ok then log("ERROR poll failed "..tostring(err)) end
    end
end
if Events and Events.OnTick then Events.OnTick.Add(tick)
else log("ERROR OnTick missing; player control disabled")end
