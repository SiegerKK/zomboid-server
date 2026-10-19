-- On-demand, read-only BUILDING METADATA and loaded-chunk presence.
-- Supports ANY active Story world and rectangular area; no chunk generation,
-- item/player/zombie mutation, AI hooks, or global scanning while idle.
if isClient and isClient() then return end
local REQ="SiegerAdminAtlasRequest.txt"
local ACK="SiegerAdminAtlasResult.txt"
local GUARD="SiegerAdminAtlasGuard.txt"
local lastPoll=nil
local processed=nil
local initialized=false
local function log(s) print("SIEGER_ADMIN_ATLAS "..tostring(s)) end
local function split(s)
    local result={}
    for field in (s.."\t"):gmatch("(.-)\t") do result[#result+1]=field end
    return result
end
local function valid(s,pattern,maxlen)
    return type(s)=="string" and #s>0 and #s<=maxlen and s:match(pattern)~=nil
end
local function integer(s,min,max)
    if type(s)~="string" or not s:match("^%-?%d+$") then error("invalid_integer") end
    local n=tonumber(s)
    if not n or n~=math.floor(n) or n<min or n>max then error("integer_out_of_range") end
    return n
end
local function now()
    if not getTimestampMs then error("wall_clock_unavailable") end
    local n=getTimestampMs()
    if type(n)~="number" or n~=n then error("invalid_wall_clock") end
    return n
end
local function readOne(name)
    local r=getFileReader(name,false)
    if not r then return nil end
    local a,b=r:readLine(),r:readLine()
    r:close()
    if not a or b or #a>320 then error("invalid_control_file") end
    return a
end
local function writeOne(name,line)
    local w=getFileWriter(name,true,false)
    if not w then error("control_writer_unavailable") end
    w:write(line.."\n")
    w:close()
end
local function filename(id)
    return "SiegerAdminAtlas-"..id..".txt"
end
local function hex(value)
    return (tostring(value or ""):gsub(".",function(c)
        return string.format("%02x",string.byte(c))
    end))
end
local function bounds(object)
    if not (object and object.getX and object.getY and
        object.getX2 and object.getY2) then error("meta_bounds_api_missing") end
    local x0,y0,x1,y1=object:getX(),object:getY(),object:getX2(),object:getY2()
    if type(x0)~="number" or type(y0)~="number" or
        type(x1)~="number" or type(y1)~="number" or
        x0~=math.floor(x0) or y0~=math.floor(y0) or
        x1~=math.floor(x1) or y1~=math.floor(y1) or
        x1<=x0 or y1<=y0 then error("invalid_meta_rectangle") end
    return x0,y0,x1,y1
end
local function overlaps(x0,y0,x1,y1,req)
    return x0<req.x1 and x1>req.x0 and y0<req.y1 and y1>req.y0
end
local function survey(req)
    if not SiegerStoryScenes or SiegerStoryScenes.world~=req.world then
        error("selected_story_world_mismatch") end
    local world=getWorld and getWorld()
    local grid=world and world.getMetaGrid and world:getMetaGrid()
    local buildings=grid and grid.getBuildings and grid:getBuildings()
    if not buildings or not buildings.size or not buildings.get then
        error("building_metagrid_api_unavailable") end
    local cell=getCell and getCell()
    local coverage=(cell and cell.getChunk) and "chunk_presence" or "unknown"
    local filenameForRequest=filename(req.id)
    local exists=getFileReader(filenameForRequest,false)
    if exists then exists:close();error("atlas_result_already_exists") end
    local w=getFileWriter(filenameForRequest,true,false)
    if not w then error("atlas_writer_unavailable") end
    local rows,matched,roomCount,rectCount,loadedChunks=0,0,0,0,0
    local inspected=buildings:size()
    local function emit(columns)
        if rows>=req.maxRows then error("atlas_record_budget_exhausted") end
        local line=table.concat(columns,"\t").."\n"
        if #line>1500 then error("atlas_row_oversized") end
        w:write(line)
        rows=rows+1
    end
    local ok,why=pcall(function()
        w:write(table.concat({"v1",req.id,req.world,
            tostring(req.x0),tostring(req.y0),tostring(req.x1),tostring(req.y1),
            tostring(req.z0),tostring(req.z1),coverage,tostring(inspected)},"\t").."\n")
        for index=0,inspected-1 do
            local b=buildings:get(index)
            if b then
                local x0,y0,x1,y1=bounds(b)
                if overlaps(x0,y0,x1,y1,req) then
                    local rooms=b.getRooms and b:getRooms()
                    if not rooms or not rooms.size or not rooms.get then
                        error("building_rooms_api_unavailable") end
                    local id="b"..tostring(index)
                    local sourceId="-"
                    if b.getIDString then
                        local validId,val=pcall(function()return b:getIDString()end)
                        if validId and val then sourceId=hex(val) end
                    end
                    emit({"b",id,tostring(x0),tostring(y0),tostring(x1),tostring(y1),
                        sourceId})
                    matched=matched+1
                    for j=0,rooms:size()-1 do
                        local room=rooms:get(j)
                        if room then
                            if not room.getZ then error("room_floor_api_missing") end
                            local floor=room:getZ()
                            if floor>=req.z0 and floor<=req.z1 then
                                local rects=room.getRects and room:getRects()
                                if not rects or not rects.size or not rects.get then
                                    error("room_rects_api_unavailable") end
                                local roomId=id.."_r"..tostring(j)
                                local name=room.getName and room:getName() or ""
                                local used=false
                                for k=0,rects:size()-1 do
                                    local rect=rects:get(k)
                                    local a,bx,c,d=bounds(rect)
                                    if overlaps(a,bx,c,d,req) then
                                        emit({"r",id,roomId,tostring(floor),tostring(a),
                                            tostring(bx),tostring(c),tostring(d),hex(name)})
                                        rectCount=rectCount+1
                                        used=true
                                    end
                                end
                                if used then roomCount=roomCount+1 end
                            end
                        end
                    end
                end
            end
        end
        if coverage=="chunk_presence" then
            local cx0,cy0=math.floor(req.x0/10),math.floor(req.y0/10)
            local cx1,cy1=math.floor((req.x1-1)/10),math.floor((req.y1-1)/10)
            for cx=cx0,cx1 do
                for cy=cy0,cy1 do
                    if cell:getChunk(cx,cy) then
                        emit({"c",tostring(cx),tostring(cy)})
                        loadedChunks=loadedChunks+1
                    end
                end
            end
        end
        w:write(table.concat({"end",tostring(rows),tostring(matched),
            tostring(roomCount),tostring(rectCount),tostring(loadedChunks)},"\t").."\n")
    end)
    w:close()
    if not ok then error(tostring(why)) end
    return matched,roomCount,rectCount,loadedChunks,rows
end
local function poll()
    if not initialized then
        local prior=readOne(ACK)
        if prior then
            local f=split(prior)
            if f[1]=="v1" and valid(f[2],"^[0-9a-f]+$",32) and #f[2]==32 then
                processed=f[2]
            end
        end
        initialized=true
    end
    local line=readOne(REQ)
    if not line then return end
    local f=split(line)
    if #f~=12 or f[1]~="v1" or not valid(f[2],"^[0-9a-f]+$",32)
        or #f[2]~=32 or not valid(f[3],"^[A-Za-z0-9_][A-Za-z0-9_%-]*$",40)
        or f[12]~="end" then return end
    if f[2]==processed then return end
    processed=f[2]
    local function handle()
        local req={id=f[2],world=f[3],
            x0=integer(f[4],-100000,1000000),y0=integer(f[5],-100000,1000000),
            x1=integer(f[6],-100000,1000000),y1=integer(f[7],-100000,1000000),
            z0=integer(f[8],-16,32),z1=integer(f[9],-16,32),
            maxRows=integer(f[10],1,1000000)}
        local expires=integer(f[11],1,9999999999999)
        local time=now()
        if time>expires or time<expires-60000 then error("request_expired") end
        if req.x0>=req.x1 or req.y0>=req.y1 or req.z0>req.z1 then
            error("invalid_atlas_query_bounds") end
        if not SiegerStoryScenes or SiegerStoryScenes.world~=req.world then
            error("world_mismatch") end
        local prior=readOne(GUARD)
        if prior==req.id then error("replay_refused") end
        writeOne(GUARD,req.id)
        return survey(req)
    end
    local ok,b,rooms,rects,chunks,rows=pcall(handle)
    if not ok then log("ERROR id="..f[2].." reason="..tostring(b)) end
    local status=ok and "complete" or "error"
    local reason=ok and "meta_buildings" or "review_server_logs"
    local line=table.concat({"v1",f[2],f[3],status,
        tostring(ok and b or 0),tostring(ok and rooms or 0),
        tostring(ok and rects or 0),tostring(ok and chunks or 0),
        tostring(ok and rows or 0),filename(f[2]),reason},"\t")
    local saved,err=pcall(writeOne,ACK,line)
    if not saved then log("ERROR result_write="..tostring(err)) end
end
if Events and Events.OnTickEvenPaused then
    Events.OnTickEvenPaused.Add(function()
        local ok,time=pcall(now)
        if not ok then return end
        if lastPoll and time>=lastPoll and time-lastPoll<1000 then return end
        lastPoll=time
        local good,why=pcall(poll)
        if not good then log("ERROR poll="..tostring(why)) end
    end)
else log("ERROR OnTickEvenPaused missing; atlas disabled")end
