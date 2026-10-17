-- Sieger Story Director: bounded read-only area survey around ONE online player.
-- v1: legacy 25x25x5; v2: 25/51/101 sides with explicit loaded/nil squares.
-- Build 42 dedicated-server only. No RCON Lua execution, no client commands,
-- no map/chunk loading, no item creation, no inventory modification.
-- Request and JSONL response live in <world>/Lua/ on the active world mount.
if isClient and isClient() then return end

local REQUEST = "SiegerStoryScanRequest.txt"
-- B42.21 getFileWriter rejects .jsonl; JSON Lines is stored in allowed .txt.
local RESPONSE = "SiegerStoryScanResult.txt"
local ACK = "SiegerStoryScanProcessed.txt"
local DEFAULT_SIDE = 25
local LEVELS = 5
local ALLOWED_SIDES = {[25]=true, [51]=true, [101]=true}
local PER_TICK = 20
local WORK_PER_TICK = 200
local MAX_RECORDS = 140000
local SCAN_MODE_KEYS = {squares=true,objects=true,containers=true,items=true,
    ground=true,actors=true,corpses=true,vehicles=true,windows=true,blood=true}
local MAX_VEHICLES = 128
local MAX_VEHICLE_PARTS = 160
local MAX_VEHICLE_CONTAINER_ITEMS = 200
local MAX_BYTES = 24 * 1024 * 1024
local lastRequestId = nil
local active = nil
local tickCount = 0
local ackLoaded = false

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

local function byteUpperBound(s)
    local size=0
    for i=1,#s do
        local ch=s:sub(i,i)
        -- Three bytes per non-ASCII unit is conservative for UTF-16 Kahlua
        -- (a surrogate pair uses six budget bytes) and byte-based Lua 5.1.
        size=size+(ch<'\128' and 1 or 3)
    end
    return size
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

local function getClass(value,job)
    -- B42 exposes getClass() but not Class.getSimpleName(); even pcall logs
    -- an engine stack trace per object. Use exposed instanceof only.
    if instanceof then
        for _,cls in ipairs({"IsoWindow","IsoDoor","IsoThumpable","IsoBarricade","IsoDeadBody","IsoWorldInventoryObject","IsoObject"}) do
            if instanceof(value,cls) then return cls end
        end
    end
    job.errors=job.errors+1
    return "<unknown>"
end

local function getSprite(value,job)
    local ok,s=pcall(function()
        local sprite=value:getSprite()
        return sprite and sprite:getName() or "<none>"
    end)
    if not ok then job.errors=job.errors+1 end
    return ok and s or "<unknown>"
end

local function getRoom(sq,job)
    local ok,s=pcall(function()
        local room=sq:getRoom()
        return room and room:getName() or ""
    end)
    if not ok then job.errors=job.errors+1 end
    return ok and s or ""
end

local function itemType(item,job)
    local ok,v=pcall(function() return item:getFullType() end)
    if not ok then job.errors=job.errors+1 end
    return ok and tostring(v or "") or "<unknown>"
end

local function itemName(item,job)
    local ok,v=pcall(function() return item:getName() end)
    if not ok then job.errors=job.errors+1 end
    return ok and tostring(v or "") or "<unknown>"
end

local function questTags(value,job)
    if not value or not value.getModData then return nil end
    local ok,md=pcall(function() return value:getModData() end)
    if not ok then job.errors=job.errors+1;return nil end
    if not md or not md["SiegerStoryToken"] then return nil end
    return {story_token=tostring(md["SiegerStoryToken"]),
            story_quest=tostring(md["SiegerStoryQuest"] or ""),
            story_action=tostring(md["SiegerStoryAction"] or ""),
            story_kind=tostring(md["SiegerStoryKind"] or "")}
end

local function mergeTags(row,tags)
    if tags then for k,v in pairs(tags) do row[k]=v end end
    return row
end

local function emit(job, values, force)
    if not force then
        for _,v in pairs(values) do
            if type(v)=="string" and #v>512 then
                job.truncated=true
                return false -- never silently clip an inventory name
            end
        end
    end
    local row=objectJson(values).."\n"
    local rowBytes=byteUpperBound(row)
    if not force and (job.records >= MAX_RECORDS or job.bytes+rowBytes > MAX_BYTES) then
        job.truncated=true
        return false
    end
    job.writer:write(row)
    job.bytes=job.bytes+rowBytes
    if not force then job.records=job.records+1 end
    return true
end

local function readBoolean(job,callback)
    local ok,result=pcall(callback)
    if not ok or type(result)~="boolean" then
        job.errors=job.errors+1
        return nil
    end
    return result
end

local function windowState(job,obj)
    return {
        window_smashed=readBoolean(job,function() return obj:isSmashed() end),
        window_glass_removed=readBoolean(job,function() return obj:isGlassRemoved() end),
        window_open=readBoolean(job,function() return obj:IsOpen() end),
        window_barricaded_same=readBoolean(job,function()
            return obj:getBarricadeOnSameSquare()~=nil end),
        window_barricaded_opposite=readBoolean(job,function()
            return obj:getBarricadeOnOppositeSquare()~=nil end)
    }
end

local function squareState(job,sq,x,y,z)
    local row={kind="square",x=x,y=y,z=z,
               loaded=true,room=getRoom(sq,job)}
    if job.modes.blood and sq.haveBloodFloor then
        row.blood_floor=readBoolean(job,function()return sq:haveBloodFloor() end)
    end
    if job.modes.blood and sq.haveBloodWall then
        row.blood_wall=readBoolean(job,function()return sq:haveBloodWall() end)
    end
    return row
end

local function inventory(job, container, pos, objectIndex, containerIndex, sourceKind)
    local contents=container:getItems()
    if not contents then return end
    for index=0,contents:size()-1 do
        coroutine.yield()
        local item=contents:get(index)
        if item then
            job.items=job.items+1
            if not job.truncated then
                if job.modes.items then emit(job,mergeTags({
                    kind="container_item", x=pos.x, y=pos.y, z=pos.z,
                    source=sourceKind, object_index=objectIndex,
                    container_index=containerIndex, slot=index,
                    full_type=itemType(item,job), name=itemName(item,job)
                },questTags(item,job))) end
            end
        end
    end
end

local function containers(job, obj, pos, objectIndex, sourceKind)
    local count=obj:getContainerCount()
    for ci=0,math.min(count-1,63) do
        coroutine.yield()
        local c=obj:getContainerByIndex(ci)
        if c then
            job.containers=job.containers+1
            local ok,name=pcall(function() return c:getType() end)
            if not ok then job.errors=job.errors+1 end
            if not job.truncated then
                emit(job,{
                    kind="container", x=pos.x, y=pos.y, z=pos.z,
                    source=sourceKind, object_index=objectIndex,
                    container_index=ci, container_type=ok and tostring(name) or "<unknown>",
                    item_count=(c:getItems() and c:getItems():size()) or 0
                })
            end
            if job.modes.items then inventory(job,c,pos,objectIndex,ci,sourceKind) end
        end
    end
    if count>64 then job.errors=job.errors+1 end
end

local function scanSquare(job,x,y,z)
    local sq=getCell():getGridSquare(x,y,z)
    if not sq then
        job.unloaded=job.unloaded+1
        if job.includeSquares and not job.truncated then
            emit(job,{kind="square",x=x,y=y,z=z,loaded=false})
        end
        return
    end
    job.loaded=job.loaded+1
    if job.includeSquares and not job.truncated then
        emit(job,squareState(job,sq,x,y,z))
    end
    local pos={x=x,y=y,z=z}
    local objects=sq:getObjects()
    if objects then
        for index=0,objects:size()-1 do
            coroutine.yield()
            local obj=objects:get(index)
            if obj then
                if job.modes.objects or job.modes.windows then
                    local cls=getClass(obj,job)
                    if job.modes.objects or cls=="IsoWindow" then
                        job.objects=job.objects+1
                        if not job.truncated then
                            local row={
                                kind="object",x=x,y=y,z=z,object_index=index,
                                sprite=getSprite(obj,job),class=cls,room=getRoom(sq,job)
                            }
                            if cls=="IsoWindow" and job.modes.windows then
                                mergeTags(row,windowState(job,obj))
                            end
                            emit(job,row)
                        end
                    end
                end
                if job.modes.containers then
                    containers(job,obj,pos,index,"square")
                end
            end
        end
    end
    local ground=job.modes.ground and sq:getWorldObjects() or nil
    if ground then
        for index=0,ground:size()-1 do
            coroutine.yield()
            local entity=ground:get(index)
            local item=entity and entity:getItem()
            if item then
                job.ground=job.ground+1
                if not job.truncated then
                    emit(job,mergeTags({
                        kind="ground_item",x=x,y=y,z=z,world_index=index,
                        full_type=itemType(item,job),name=itemName(item,job)
                    },questTags(item,job)))
                end
            end
        end
    end
    -- Only tagged live zombies are included: this is a quest-ownership
    -- inspector, not a world zombie census.
    if job.modes.actors and sq.getMovingObjects then
        local moving=sq:getMovingObjects()
        if moving then
            for index=0,moving:size()-1 do
                coroutine.yield()
                local entity=moving:get(index)
                if entity and instanceof and instanceof(entity,"IsoZombie") then
                    local tags=questTags(entity,job)
                    if tags and tags.story_kind=="infected" and not job.seenQuestZombies[tags.story_token] then
                        job.seenQuestZombies[tags.story_token]=true
                        job.zombies=job.zombies+1
                        local ident=-1
                        local ok,id=pcall(function() return entity:getOnlineID() end)
                        if ok and id then ident=id end
                        if not job.truncated then
                            emit(job,mergeTags({kind="quest_zombie",
                                x=math.floor(entity:getX()),y=math.floor(entity:getY()),
                                z=math.floor(entity:getZ()),online_id=ident},tags))
                        end
                    end
                end
            end
        end
    end
    -- Authored bodies are saved as IsoDeadBody, separate from live zombies.
    -- Only publish Story-tagged corpses; natural dead bodies stay private.
    if job.modes.corpses and sq.getDeadBodys then
        local bodies=sq:getDeadBodys()
        if bodies then
            for index=0,bodies:size()-1 do
                coroutine.yield()
                local body=bodies:get(index)
                local tags=questTags(body,job)
                if tags and tags.story_kind=="corpse" and not job.seenQuestCorpses[tags.story_token] then
                    job.seenQuestCorpses[tags.story_token]=true
                    job.corpses=job.corpses+1
                    if not job.truncated then
                        emit(job,mergeTags({
                            kind="quest_corpse", x=x,y=y,z=z,body_index=index
                        },tags))
                    end
                end
            end
        end
    end
    local static=job.modes.objects and sq:getStaticMovingObjects() or nil
    if static then
        for index=0,static:size()-1 do
            coroutine.yield()
            local obj=static:get(index)
            if obj then
                job.static=job.static+1
                if not job.truncated then
                    emit(job,{
                        kind="static_object",x=x,y=y,z=z,static_index=index,
                        class=getClass(obj,job)
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
                    if job.modes.items then inventory(job,c,pos,index,0,"static") end
                end
            end
        end
    end
end

-- Read-only vehicle census. Java Set.iterator() is used instead of
-- assuming a Lua array. Only loaded vehicles whose CENTRE is in the survey
-- bounding box are emitted. This is not vehicle spawning or chunk loading.
local function scanVehicles(job)
    local cell=getCell()
    if not cell or not cell.getVehicles then error("IsoCell.getVehicles is unavailable") end
    local vehicles=cell:getVehicles()
    if not vehicles then error("Vehicle collection unavailable") end
    local iterator=nil
    if vehicles.iterator then
        iterator=vehicles:iterator()
    elseif vehicles.size and vehicles.get then
        local index=0
        iterator={hasNext=function()return index<vehicles:size() end,
            next=function()local car=vehicles:get(index);index=index+1;return car end}
    end
    if not iterator then error("Vehicle Set/List iteration unavailable") end
    while iterator:hasNext() do
        coroutine.yield()
        local car=iterator:next()
        if car then
            local x,y,z=car:getX(),car:getY(),car:getZ()
            if type(x)~="number" or type(y)~="number" or type(z)~="number" then
                error("Invalid vehicle coordinates")
            end
            local tx,ty,tz=math.floor(x),math.floor(y),math.floor(z)
            if tx>=job.x-job.radius and tx<=job.x+job.radius
                and ty>=job.y-job.radius and ty<=job.y+job.radius
                and tz>=job.z_start and tz<job.z_start+job.levels then
                if job.vehicles>=MAX_VEHICLES then
                    job.truncated=true
                    return
                end
                local id=car:getId()
                local script=car:getScriptName()
                local n=car:getPartCount()
                if type(id)~="number" or type(n)~="number" or n<0
                    or n>MAX_VEHICLE_PARTS or not script then
                    error("Invalid vehicle ID, script or part count")
                end
                if job.seenVehicleIds[id] then error("Duplicate vehicle ID in loaded set") end
                job.seenVehicleIds[id]=true
                job.vehicles=job.vehicles+1
                if not job.truncated then
                    emit(job,mergeTags({
                        kind="vehicle",x=tx,y=ty,z=tz,world_x=x,world_y=y,
                        vehicle_id=id,script=tostring(script),part_count=n
                    },questTags(car,job)))
                end
                for i=0,n-1 do
                    coroutine.yield()
                    local part=car:getPartByIndex(i)
                    if not part then error("Missing vehicle part at index "..i) end
                    local pid=part:getId()
                    local condition=part:getCondition()
                    if not pid or type(condition)~="number" then
                        error("Invalid vehicle part ID/condition")
                    end
                    local fitted=part:getInventoryItem()
                    local installed_type=fitted and itemType(fitted,job) or ""
                    local c=part:getItemContainer()
                    local has_container=c~=nil
                    job.vehicleParts=job.vehicleParts+1
                    if not job.truncated then
                        emit(job,{
                            kind="vehicle_part",x=tx,y=ty,z=tz,
                            vehicle_id=id,part_id=tostring(pid),part_index=i,
                            condition=condition,installed_item=installed_type,
                            has_container=has_container
                        })
                    end
                    if c then
                        job.vehicleContainers=job.vehicleContainers+1
                        local contents=c:getItems()
                        if not contents then error("Missing vehicle container items") end
                        local count=contents:size()
                        if count>MAX_VEHICLE_CONTAINER_ITEMS then
                            job.truncated=true
                            return
                        end
                        if not job.truncated then
                            emit(job,{
                                kind="vehicle_container",x=tx,y=ty,z=tz,
                                vehicle_id=id,part_id=tostring(pid),
                                container_type=tostring(c:getType()),
                                item_count=count
                            })
                        end
                        for index=0,count-1 do
                            coroutine.yield()
                            local item=contents:get(index)
                            if item then
                                job.vehicleItems=job.vehicleItems+1
                                if not job.truncated then
                                    emit(job,mergeTags({
                                        kind="vehicle_item",x=tx,y=ty,z=tz,
                                        vehicle_id=id,part_id=tostring(pid),
                                        slot=index,full_type=itemType(item,job),
                                        name=itemName(item,job)
                                    },questTags(item,job)))
                                end
                            end
                        end
                    end
                end
            end
        end
    end
end

local function finishVehicles(job)
    if job.vehicleFinished then return end
    if not job.vehicleTask then
        job.vehicleTask=coroutine.create(function()scanVehicles(job)end)
    end
    for i=1,WORK_PER_TICK do
        if job.truncated then return end
        local ok,err=coroutine.resume(job.vehicleTask)
        if not ok then
            job.errors=job.errors+1
            log("WARN vehicle scan: "..clippedString(err))
            job.vehicleFinished=true
            return
        end
        if coroutine.status(job.vehicleTask)=="dead" then
            job.vehicleFinished=true
            return
        end
    end
end

local function finish(job, status, reason)
    emit(job,{
        kind="summary", request_id=job.id, status=status,
        reason=reason or "", requested_squares=job.cells,
        loaded_squares=job.loaded, unloaded_squares=job.unloaded,
        scanned_squares=job.cursor, objects=job.objects, containers=job.containers,
        container_items=job.items, ground_items=job.ground,
        static_objects=job.static, quest_zombies=job.zombies,
        quest_corpses=job.corpses, vehicles=job.vehicles,
        vehicle_parts=job.vehicleParts,vehicle_containers=job.vehicleContainers,
        vehicle_items=job.vehicleItems,
        vehicle_snapshot=(job.modes.vehicles and
                          (job.vehicleFinished and "complete" or "incomplete")
                          or "not_requested"), errors=job.errors,
        records=job.records, truncated=job.truncated, bytes=job.bytes
    },true)
    job.writer:close()
    local ok,ack=pcall(getFileWriter,ACK,true,false)
    if ok and ack then ack:write(job.id.."\n");ack:close()
    else log("ERROR unable to persist completed request ID") end
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

local function beginScan(id,username,side,includeSquares,params)
    local ok,writer=pcall(getFileWriter,RESPONSE,true,false)
    if not ok or not writer then
        log("ERROR unable to open response file id="..id)
        return false
    end
    local levels=params and params.levels or LEVELS
    local modes=params and params.modes or {
        squares=includeSquares,objects=true,containers=true,items=true,
        ground=true,actors=true,corpses=true,vehicles=includeSquares,
        windows=includeSquares,blood=includeSquares}
    local job={
        id=id,username=username,writer=writer,cursor=0,
        side=side,radius=math.floor(side/2),levels=levels,cells=side*side*levels,
        includeSquares=includeSquares,modes=modes,modeString=params and params.modeString or "legacy",
        loaded=0,unloaded=0,objects=0,containers=0,items=0,ground=0,static=0,
        errors=0,records=0,bytes=0,truncated=false,zombies=0,seenQuestZombies={},
        corpses=0,seenQuestCorpses={},
        vehicles=0,vehicleParts=0,vehicleContainers=0,vehicleItems=0,
        seenVehicleIds={},vehicleFinished=not modes.vehicles
    }
    local player=findPlayer(username)
    if not player then
        job.cursor=0
        emit(job,{kind="meta",request_id=id,player=username,status="error",reason="player_not_online"},true)
        finish(job,"error","player_not_online")
        return true
    end
    local px,py=math.floor(player:getX()),math.floor(player:getY())
    job.x=params and params.x or px
    job.y=params and params.y or py
    job.z=math.floor(player:getZ())
    if math.abs(job.x-px)>100 or math.abs(job.y-py)>100 then
        job.cursor=0
        emit(job,{kind="meta",request_id=id,player=username,status="error",
                  reason="center_far_from_online_player"},true)
        finish(job,"error","center_far_from_online_player")
        return true
    end
    job.z_start=params and params.zmin or math.max(-2,math.min(job.z-2,12))
    emit(job,{
        kind="meta",request_id=id,player=username,status="scanning",
        center_x=job.x,center_y=job.y,center_z=job.z,
        min_x=job.x-job.radius,max_x=job.x+job.radius,
        min_y=job.y-job.radius,max_y=job.y+job.radius,
        min_z=job.z_start,max_z=job.z_start+job.levels-1,
        side=job.side,levels=job.levels,requested_squares=job.cells,
        modes=job.modeString,
        inventory_scope="top_level_only",missing_square_meaning="unloaded_or_nonexistent",
        snapshot_mode="incremental",square_coverage=job.includeSquares,
        vehicle_snapshot=job.modes.vehicles and "bounded_loaded_vehicle_centres" or "not_requested"
    },true)
    active=job
    log("START id="..id.." player="..username.." center="..
        job.x..","..job.y..","..job.z.." volume="..job.side.."x"..job.side.."x"..job.levels)
    return true
end

local function readRequest()
    if not ackLoaded then
        local ok,reader=pcall(getFileReader,ACK,false)
        if ok and reader then
            local id=reader:readLine();reader:close()
            if id and #id==32 and id:match("^[0-9a-f]+$") then lastRequestId=id end
        end
        ackLoaded=true
    end
    local ok,reader=pcall(getFileReader,REQUEST,false)
    if not ok or not reader then return end
    local extra=nil
    local okline,line=pcall(function()
        local first=reader:readLine();extra=reader:readLine();return first
    end)
    pcall(function() reader:close() end)
    if not okline or not line then return end
    if #line>256 or extra~=nil then log("ERROR oversized/multiline scan request");return end
    local version,id,username,side,levels=line:match("^(v[12])\t([0-9a-f]+)\t([%w_.%-]+)\t(%d+)\t(%d+)$")
    local params=nil
    if not version then
        local radius,zmin,zmax,modeString,cx,cy
        id,username,cx,cy,radius,zmin,zmax,modeString=
            line:match("^v3\t([0-9a-f]+)\t([%w_.%-]+)\t([%d%-]+)\t([%d%-]+)\t(%d+)\t([%d%-]+)\t([%d%-]+)\t([a-z,]+)$")
        radius,zmin,zmax=tonumber(radius),tonumber(zmin),tonumber(zmax)
        if not id or not radius or radius<1 or radius>50 or not zmin or not zmax
            or zmin< -2 or zmax>16 or zmax<zmin or zmax-zmin>=5
            or (cx=="-")~=(cy=="-") then
            log("ERROR invalid v3 scan bounds")
            return
        end
        if cx~="-" then
            cx,cy=tonumber(cx),tonumber(cy)
            if not cx or not cy or cx<0 or cx>40000 or cy<0 or cy>40000 then
                log("ERROR invalid v3 center")
                return
            end
        end
        local modes,count={},0
        for mode in modeString:gmatch("[^,]+") do
            if not SCAN_MODE_KEYS[mode] or modes[mode] then
                log("ERROR invalid or duplicate scan mode")
                return
            end
            modes[mode]=true
            count=count+1
        end
        if count==0 or (modes.blood and not modes.squares)
            or (modes.items and not modes.containers) then
            log("ERROR invalid mode dependencies")
            return
        end
        params={x=cx~="-" and cx or nil,y=cy~="-" and cy or nil,
            zmin=zmin,levels=zmax-zmin+1,modes=modes,modeString=modeString}
        side=2*radius+1
        version="v3"
    else
        side=tonumber(side)
        if tonumber(levels)~=LEVELS or not ((version=="v1" and side==DEFAULT_SIDE)
            or (version=="v2" and ALLOWED_SIDES[side])) then
            log("ERROR invalid v1/v2 scan dimensions")
            return
        end
    end
    if not id or #id~=32 or not username or #username>31
        or not username:match("^[A-Za-z0-9_][A-Za-z0-9_.%-]*$") then
        log("ERROR invalid request id or account")
        return
    end
    if id==lastRequestId then return end
    if beginScan(id,username,side,version~="v1" and (not params or params.modes.squares),params) then lastRequestId=id end
end

local function tick()
    tickCount=tickCount+1
    if not active then
        if tickCount%120==0 then
            local ok,err=pcall(readRequest)
            if not ok then log("ERROR request processing: "..clippedString(err)) end
        end
        return
    end
    local job=active
    local cellsDone=0
    for i=1,WORK_PER_TICK do
        if job.truncated then finish(job,"partial","report_limit");return end
        if job.cursor>=job.cells then
            finishVehicles(job)
            if job.vehicleFinished or job.truncated then
                finish(job,(job.errors>0 or job.truncated) and "partial" or "complete",
                       job.truncated and "report_limit" or "")
            end
            return
        end
        local idx=job.cursor
        local layer=math.floor(idx/(job.side*job.side))
        local offset=idx%(job.side*job.side)
        local x=job.x + (offset%job.side)-job.radius
        local y=job.y + math.floor(offset/job.side)-job.radius
        local z=job.z_start+layer
        if cellsDone>=PER_TICK then return end
        if not job.task then
            job.task=coroutine.create(function() scanSquare(job,x,y,z) end)
        end
        local ok,err=coroutine.resume(job.task)
        if not ok then
            job.errors=job.errors+1
            if job.errors<=5 then log("WARN cell="..x..","..y..","..z.." "..clippedString(err)) end
        end
        if not ok or coroutine.status(job.task)=="dead" then
            job.task=nil
            job.cursor=job.cursor+1
            cellsDone=cellsDone+1
        end
    end
    if job.cursor>=job.cells then
        finishVehicles(job)
        if job.vehicleFinished or job.truncated then
            finish(job,(job.errors>0 or job.truncated) and "partial" or "complete",
                   job.truncated and "report_limit" or "")
        end
    end
end

if Events and Events.OnTick then
    Events.OnTick.Add(tick)
else
    log("ERROR OnTick missing, disabled")
end
