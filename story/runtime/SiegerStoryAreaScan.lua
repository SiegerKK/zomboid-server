-- Sieger Story Director: read-only on-demand area scan around ONE online player.
-- Build 42 dedicated-server only. No RCON Lua execution, no client commands,
-- no map/chunk loading, no item creation, no inventory modification.
-- Request and JSONL response live in <world>/Lua/ on the active world mount.
if isClient and isClient() then return end

local REQUEST = "SiegerStoryScanRequest.txt"
local RESPONSE = "SiegerStoryScanResult.jsonl"
local SIDE = 25
local LEVELS = 5
local CELLS = SIDE * SIDE * LEVELS
local PER_TICK = 20
local MAX_RECORDS = 90000
local MAX_BYTES = 24 * 1024 * 1024
local lastRequestId = nil
local active = nil
local tickCount = 0

local function log(msg)
    print("SIEGER_STORY_SCAN " .. tostring(msg))
end

local function clippedString(value)
    if value == nil then return "" end
    local s = tostring(value)
    if #s <= 512 then return s end
    local n = 512
    while n > 1 and s:byte(n) >= 128 and s:byte(n) <= 191 do n = n - 1 end
    return s:sub(1,n - 1) .. "..."
end

local function jsonString(value)
    local s = clippedString(value)
    local out = {'"'}
    for i=1,#s do
        local n=s:byte(i)
        if n == 34 then out[#out + 1] = '\\"'
        elseif n == 92 then out[#out + 1] = '\\\\'
        elseif n == 10 then out[#out + 1] = '\\n'
        elseif n == 13 then out[#out + 1] = '\\r'
        elseif n == 9 then out[#out + 1] = '\\t'
        elseif n < 32 then out[#out + 1] = string.format("\\u%04x",n)
        else out[#out + 1] = string.char(n) end
    end
    out[#out + 1] = '"'
    return table.concat(out)
end

local function jsonValue(value)
    local kind=type(value)
    if kind=="string" then return jsonString(value) end
    if kind=="boolean" then return value and "true" or "false" end
    if kind=="number" and value==value and value~=math.huge and value~=-math.huge then return tostring(value) end
    return "null"
end

local function objectJson(values)
    local fields={}
    for k,v in pairs(values) do
        fields[#fields+1] = jsonString(k) .. ":" .. jsonValue(v)
    end
    table.sort(fields)
    return "{" .. table.concat(fields,",") .. "}"
end

local function getClass(value)
    local ok,c=pcall(function() return value:getClass():getSimpleName() end)
    if ok and c then return tostring(c) end
    return "<unknown>"
end

local function getSprite(value)
    local ok,s=pcall(function()
        local sprite=value:getSprite()
        return sprite and sprite:getName() or "<none>"
    end)
    return ok and s or "<unknown>"
end

local function getRoom(sq)
    local ok,s=pcall(function()
        local room=sq:getRoom()
        return room and room:getName() or ""
    end)
    return ok and s or ""
end

local function itemType(item)
    local ok,v=pcall(function() return item:getFullType() end)
    return ok and tostring(v or "") or "<unknown>"
end

local function itemName(item)
    local ok,v=pcall(function() return item:getName() end)
    return ok and tostring(v or "") or "<unknown>"
end

local function emit(job, values, force)
    local row=objectJson(values).."\n"
    if not force and (job.records >= MAX_RECORDS or job.bytes+#row > MAX_BYTES) then
        job.truncated=true
        return false
    end
    job.writer:write(row)
    job.bytes=job.bytes+#row
    if not force then job.records=job.records+1 end
    return true
end

local function inventory(job, container, pos, objectIndex, containerIndex, sourceKind)
    local contents=container:getItems()
    if not contents then return end
    for index=0,contents:size()-1 do
        local item=contents:get(index)
        if item then
            job.items=job.items+1
            if not job.truncated then
                emit(job,{
                    kind="container_item", x=pos.x, y=pos.y, z=pos.z,
                    source=sourceKind, object_index=objectIndex,
                    container_index=containerIndex, slot=index,
                    full_type=itemType(item), name=itemName(item)
                })
            end
        end
    end
end

local function containers(job, obj, pos, objectIndex, sourceKind)
    local count=obj:getContainerCount()
    for ci=0,math.min(count-1,63) do
        local c=obj:getContainerByIndex(ci)
        if c then
            job.containers=job.containers+1
            local ok,name=pcall(function() return c:getType() end)
            if not job.truncated then
                emit(job,{
                    kind="container", x=pos.x, y=pos.y, z=pos.z,
                    source=sourceKind, object_index=objectIndex,
                    container_index=ci, container_type=ok and tostring(name) or "<unknown>",
                    item_count=(c:getItems() and c:getItems():size()) or 0
                })
            end
            inventory(job,c,pos,objectIndex,ci,sourceKind)
        end
    end
    if count>64 then job.errors=job.errors+1 end
end

local function scanSquare(job,x,y,z)
    local sq=getCell():getGridSquare(x,y,z)
    if not sq then job.unloaded=job.unloaded+1 return end
    job.loaded=job.loaded+1
    local pos={x=x,y=y,z=z}
    local objects=sq:getObjects()
    if objects then
        for index=0,objects:size()-1 do
            local obj=objects:get(index)
            if obj then
                job.objects=job.objects+1
                if not job.truncated then
                    emit(job,{
                        kind="object", x=x,y=y,z=z,object_index=index,
                        sprite=getSprite(obj), class=getClass(obj), room=getRoom(sq)
                    })
                end
                containers(job,obj,pos,index,"square")
            end
        end
    end
    local ground=sq:getWorldObjects()
    if ground then
        for index=0,ground:size()-1 do
            local entity=ground:get(index)
            local item=entity and entity:getItem()
            if item then
                job.ground=job.ground+1
                if not job.truncated then
                    emit(job,{
                        kind="ground_item",x=x,y=y,z=z,world_index=index,
                        full_type=itemType(item),name=itemName(item)
                    })
                end
            end
        end
    end
    local static=sq:getStaticMovingObjects()
    if static then
        for index=0,static:size()-1 do
            local obj=static:get(index)
            if obj then
                job.static=job.static+1
                if not job.truncated then
                    emit(job,{
                        kind="static_object",x=x,y=y,z=z,static_index=index,
                        class=getClass(obj)
                    })
                end
                -- Some static objects are corpses with their own inventories.
                local ok,c=pcall(function() return obj:getContainer() end)
                if ok and c then
                    job.containers=job.containers+1
                    if not job.truncated then
                        emit(job,{
                            kind="container",x=x,y=y,z=z,source="static",
                            object_index=index,container_index=0,
                            container_type=tostring(c:getType()),
                            item_count=(c:getItems() and c:getItems():size()) or 0
                        })
                    end
                    inventory(job,c,pos,index,0,"static")
                end
            end
        end
    end
end

local function finish(job, status, reason)
    emit(job,{
        kind="summary", request_id=job.id, status=status,
        reason=reason or "", requested_squares=CELLS,
        loaded_squares=job.loaded, unloaded_squares=job.unloaded,
        scanned_squares=job.cursor, objects=job.objects, containers=job.containers,
        container_items=job.items, ground_items=job.ground,
        static_objects=job.static, errors=job.errors,
        records=job.records, truncated=job.truncated, bytes=job.bytes
    },true)
    job.writer:close()
    log("FINISH id="..job.id.." status="..status.." player="..job.username..
        " loaded="..job.loaded.." unloaded="..job.unloaded..
        " records="..job.records.." truncated="..tostring(job.truncated))
    active=nil
end

local function findPlayer(username)
    local players=getOnlinePlayers()
    if not players then return nil end
    for i=0,players:size()-1 do
        local player=players:get(i)
        if player and tostring(player:getUsername())==username then
            return player
        end
    end
    return nil
end

local function beginScan(id,username)
    local ok,writer=pcall(getFileWriter,RESPONSE,true,false)
    if not ok or not writer then
        log("ERROR unable to open response file id="..id)
        return
    end
    local job={
        id=id,username=username,writer=writer,cursor=0,
        loaded=0,unloaded=0,objects=0,containers=0,items=0,ground=0,static=0,
        errors=0,records=0,bytes=0,truncated=false
    }
    local player=findPlayer(username)
    if not player then
        job.cursor=0
        emit(job,{kind="meta",request_id=id,player=username,status="error",reason="player_not_online"},true)
        finish(job,"error","player_not_online")
        return
    end
    job.x=math.floor(player:getX())
    job.y=math.floor(player:getY())
    job.z=math.floor(player:getZ())
    job.z_start=math.max(-2,math.min(job.z-2,12))
    emit(job,{
        kind="meta",request_id=id,player=username,status="scanning",
        center_x=job.x,center_y=job.y,center_z=job.z,
        min_x=job.x-12,max_x=job.x+12,
        min_y=job.y-12,max_y=job.y+12,
        min_z=job.z_start,max_z=job.z_start+4,
        side=SIDE,levels=LEVELS,requested_squares=CELLS
    },true)
    active=job
    log("START id="..id.." player="..username.." center="..
        job.x..","..job.y..","..job.z.." volume="..SIDE.."x"..SIDE.."x"..LEVELS)
end

local function readRequest()
    local ok,reader=pcall(getFileReader,REQUEST,false)
    if not ok or not reader then return end
    local okline,line=pcall(function() return reader:readLine() end)
    pcall(function() reader:close() end)
    if not okline or not line then return end
    local id,username,side,levels=line:match("^v1\t([0-9a-f]+)\t([%w_.%-]+)\t(%d+)\t(%d+)$")
    if not id or #id~=32 or tonumber(side)~=SIDE or tonumber(levels)~=LEVELS then
        log("ERROR invalid scan request, expected v1 + 32-hex-id + username + 25 + 5")
        return
    end
    if id==lastRequestId then return end
    lastRequestId=id
    beginScan(id,username)
end

local function tick()
    tickCount=tickCount+1
    if not active then
        if tickCount%120==0 then pcall(readRequest) end
        return
    end
    local job=active
    for i=1,PER_TICK do
        if job.cursor>=CELLS then
            finish(job,job.errors>0 and "partial" or "complete","")
            return
        end
        local idx=job.cursor
        local layer=math.floor(idx/(SIDE*SIDE))
        local offset=idx%(SIDE*SIDE)
        local x=job.x + (offset%SIDE)-12
        local y=job.y + math.floor(offset/SIDE)-12
        local z=job.z_start+layer
        local ok,err=pcall(scanSquare,job,x,y,z)
        if not ok then
            job.errors=job.errors+1
            if job.errors<=5 then log("WARN cell="..x..","..y..","..z.." "..clippedString(err)) end
        end
        job.cursor=job.cursor+1
    end
    if job.cursor>=CELLS then finish(job,job.errors>0 and "partial" or "complete","") end
end

if Events and Events.OnTick then
    Events.OnTick.Add(tick)
else
    log("ERROR OnTick missing, disabled")
end
