-- Build 42.21: server read-only metadata, stepped on OnTickEvenPaused.
-- ALL buildings and all queried chunks are visited; only work PER GAME TICK is
-- bounded. Never invoke chunk creation/AI/player mutation or scan while idle.
if isClient and isClient() then return end
local REQUEST="SiegerAdminAtlasRequest.txt"
local ACK="SiegerAdminAtlasResult.txt"
local STOP="SiegerAdminAtlasStop.txt"
local GUARD="SiegerAdminAtlasGuard.txt"
local CHUNK_SIZE=8
local WORK_PER_TICK=256
local lastPoll=nil
local initialized=false
local processed=nil
local job=nil

local function log(message) print("SIEGER_ADMIN_ATLAS "..tostring(message)) end
local function split(s)
    local a={}
    for field in (s.."\t"):gmatch("(.-)\t") do a[#a+1]=field end
    return a
end
local function valid(s,pattern,max)
    return type(s)=="string" and #s>0 and #s<=max and s:match(pattern)~=nil
end
local function integer(s,min,max)
    if type(s)~="string" or not s:match("^%-?%d+$") then error("invalid_integer") end
    local n=tonumber(s)
    if not n or n~=math.floor(n) or n<min or n>max then error("integer_out_of_range") end
    return n
end
local function now()
    if not getTimestampMs then error("clock_unavailable") end
    local v=getTimestampMs()
    if type(v)~="number" or v~=v or v<1 or v>9999999999999 then
        error("invalid_wall_clock") end
    return v
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
    if not w then error("control_writer_missing") end
    local ok,err=pcall(function()w:write(line.."\n")end)
    w:close()
    if not ok then error(err) end
end
local function filename(id) return "SiegerAdminAtlas-"..id..".txt" end
local function hex(value)
    return (tostring(value or ""):gsub(".",function(c)
        return string.format("%02x",string.byte(c))
    end))
end
local function bounds(obj)
    if not obj or not obj.getX or not obj.getY or
        not obj.getX2 or not obj.getY2 then error("meta_bounds_api_missing") end
    local a,b,c,d=obj:getX(),obj:getY(),obj:getX2(),obj:getY2()
    if type(a)~="number" or type(b)~="number" or
        type(c)~="number" or type(d)~="number" or
        a~=math.floor(a) or b~=math.floor(b) or
        c~=math.floor(c) or d~=math.floor(d) or c<=a or d<=b then
        error("invalid_meta_rectangle") end
    return a,b,c,d
end
local function overlaps(a,b,c,d,r)
    return a<r.x1 and c>r.x0 and b<r.y1 and d>r.y0
end
local function emit(fields)
    if job.rows>=job.maxRows then error("atlas_row_budget_exhausted") end
    local line=table.concat(fields,"\t").."\n"
    if #line>1500 then error("atlas_row_oversized") end
    job.writer:write(line)
    job.rows=job.rows+1
end
local function writer(open)
    if open then
        job.writer=getFileWriter(filename(job.id),true,true)
        if not job.writer then error("atlas_writer_unavailable") end
    elseif job and job.writer then
        job.writer:close()
        job.writer=nil
    end
end
local function progress(state,reason)
    local j=job
    writeOne(ACK,table.concat({"v1",j.id,j.world,state,tostring(j.matched),
        tostring(j.rooms),tostring(j.rectangles),tostring(j.chunks),
        tostring(j.rows),filename(j.id),reason},"\t"))
end
local function worker()
    local world=getWorld and getWorld()
    local grid=world and world.getMetaGrid and world:getMetaGrid()
    local buildings=grid and grid.getBuildings and grid:getBuildings()
    if not buildings or not buildings.size or not buildings.get then
        error("building_metagrid_api_unavailable") end
    local cell=getCell and getCell()
    -- Only the B42.21 read-only dedicated GameServer->ServerMap lookup.
    -- IsoCell:getChunk(wx,wy) is CLIENT chunkMap-only and gives false zeros.
    local coverage=(cell and cell.getChunkForGridSquare) and
        "server_loaded_chunks" or "unknown"
    job.coverage=coverage
    local total=buildings:size()
    if type(total)~="number" or total<0 or total~=math.floor(total) then
        error("invalid_building_count") end
    job.totalBuildings=total
    job.writer:write(table.concat({"v2",job.id,job.world,
        tostring(job.x0),tostring(job.y0),tostring(job.x1),tostring(job.y1),
        tostring(job.z0),tostring(job.z1),coverage,tostring(total),
        tostring(CHUNK_SIZE)},"\t").."\n")
    for i=0,total-1 do
        local building=buildings:get(i)
        if building then
            local a,b,c,d=bounds(building)
            if overlaps(a,b,c,d,job) then
                local rooms=building.getRooms and building:getRooms()
                if not rooms or not rooms.size or not rooms.get then
                    error("building_rooms_api_unavailable") end
                local id="b"..tostring(i)
                local sourceId="-"
                if building.getIDString then
                    local ok,val=pcall(function()return building:getIDString()end)
                    if ok and val then sourceId=hex(val) end
                end
                emit({"b",id,tostring(a),tostring(b),tostring(c),
                    tostring(d),sourceId})
                job.matched=job.matched+1
                for j=0,rooms:size()-1 do
                    local room=rooms:get(j)
                    if room then
                        if not room.getZ then error("room_floor_api_unavailable") end
                        local floor=room:getZ()
                        if floor>=job.z0 and floor<=job.z1 then
                            local rects=room.getRects and room:getRects()
                            if not rects or not rects.size or not rects.get then
                                error("room_rects_api_unavailable") end
                            local used=false
                            for k=0,rects:size()-1 do
                                local ra=rects:get(k)
                                local rx,ry,rx2,ry2=bounds(ra)
                                if overlaps(rx,ry,rx2,ry2,job) then
                                    emit({"r",id,id.."_r"..tostring(j),tostring(floor),
                                        tostring(rx),tostring(ry),
                                        tostring(rx2),tostring(ry2),
                                        hex(room.getName and room:getName()or"")})
                                    job.rectangles=job.rectangles+1
                                    used=true
                                end
                                coroutine.yield()
                            end
                            if used then job.rooms=job.rooms+1 end
                        end
                    end
                    coroutine.yield()
                end
            end
        end
        coroutine.yield()
    end
    if coverage=="server_loaded_chunks" then
        job.coverageStart=now()
        local cx0,cy0=math.floor(job.x0/CHUNK_SIZE),math.floor(job.y0/CHUNK_SIZE)
        local cx1,cy1=math.floor((job.x1-1)/CHUNK_SIZE),math.floor((job.y1-1)/CHUNK_SIZE)
        for cx=cx0,cx1 do
            for cy=cy0,cy1 do
                if cell:getChunkForGridSquare(cx*CHUNK_SIZE,cy*CHUNK_SIZE,0) then
                    emit({"c",tostring(cx),tostring(cy)})
                    job.chunks=job.chunks+1
                end
                coroutine.yield()
            end
        end
        job.coverageEnd=now()
    end
    local completed=now()
    job.writer:write(table.concat({"end",tostring(job.rows),
        tostring(job.matched),tostring(job.rooms),tostring(job.rectangles),
        tostring(job.chunks),string.format("%.0f",job.started),
        job.coverageStart and string.format("%.0f",job.coverageStart) or "-",
        job.coverageEnd and string.format("%.0f",job.coverageEnd) or "-",
        string.format("%.0f",completed)},"\t").."\n")
end
local function endJob(state,reason)
    local closed=pcall(writer,false)
    if not closed then log("ERROR atlas writer close failed") end
    local ok,err=pcall(progress,state,reason)
    if not ok then log("ERROR result_write="..tostring(err)) end
    job=nil
end
local function step()
    if not job then return end
    if readOne(STOP)==job.id then
        endJob("error","operator_stopped")
        return
    end
    local successful,why=pcall(writer,true)
    if not successful then
        log("ERROR opening writer "..tostring(why))
        endJob("error","review_server_logs")
        return
    end
    for i=1,WORK_PER_TICK do
        local ok,err=coroutine.resume(job.co)
        if not ok then
            log("ERROR id="..job.id.." detail="..tostring(err))
            endJob("error","review_server_logs")
            return
        end
        if coroutine.status(job.co)=="dead" then
            endJob("complete","meta_buildings")
            return
        end
    end
    local closed,reason=pcall(writer,false)
    if not closed then
        log("ERROR close="..tostring(reason))
        endJob("error","review_server_logs")
        return
    end
    local ok,err=pcall(progress,"running","scan_in_progress")
    if not ok then log("ERROR progress="..tostring(err))end
end
local function parse(line)
    if not line then return nil end
    local f=split(line)
    if #f~=12 or f[1]~="v1" or not valid(f[2],"^[0-9a-f]+$",32)
        or #f[2]~=32 or not valid(f[3],"^[A-Za-z0-9_][A-Za-z0-9_%-]*$",40)
        or f[12]~="end" then return nil end
    return {
        id=f[2],world=f[3],
        x0=integer(f[4],-100000,1000000),y0=integer(f[5],-100000,1000000),
        x1=integer(f[6],-100000,1000000),y1=integer(f[7],-100000,1000000),
        z0=integer(f[8],-16,32),z1=integer(f[9],-16,32),
        maxRows=integer(f[10],1,1000000),expires=integer(f[11],1,9999999999999)
    }
end
local function poll(t)
    if not initialized then
        local prev=readOne(ACK)
        if prev then
            local f=split(prev)
            if f[1]=="v1" and valid(f[2],"^[0-9a-f]+$",32) and #f[2]==32 then
                processed=f[2]
                if f[4]=="running" and #f==11 then
                    -- Never reuse a partial capture as a finished scan.
                    writeOne(ACK,table.concat({"v1",f[2],f[3],"error",
                        f[5],f[6],f[7],f[8],f[9],f[10],
                        "runtime_interrupted"},"\t"))
                end
            end
        end
        initialized=true
    end
    if job then step();return end
    if lastPoll and t>=lastPoll and t-lastPoll<1000 then return end
    lastPoll=t
    local req=parse(readOne(REQUEST))
    if not req or req.id==processed then return end
    processed=req.id
    if not SiegerStoryScenes or SiegerStoryScenes.world~=req.world or
       req.x0>=req.x1 or req.y0>=req.y1 or req.z0>req.z1 or
       t>req.expires or t<req.expires-60000 then
        writeOne(ACK,table.concat({"v1",req.id,req.world,"error",
            "0","0","0","0","0",filename(req.id),"rejected_request"},"\t"))
        return
    end
    if readOne(GUARD)==req.id then
        writeOne(ACK,table.concat({"v1",req.id,req.world,"error",
            "0","0","0","0","0",filename(req.id),"replay_refused"},"\t"))
        return
    end
    local exists=getFileReader(filename(req.id),false)
    if exists then
        exists:close()
        writeOne(ACK,table.concat({"v1",req.id,req.world,"error",
            "0","0","0","0","0",filename(req.id),"result_already_exists"},"\t"))
        return
    end
    writeOne(GUARD,req.id)
    if readOne(GUARD)~=req.id then error("atlas_guard_write_failed") end
    job=req
    job.started=t
    job.rows=0;job.matched=0;job.rooms=0;job.rectangles=0;job.chunks=0
    job.co=coroutine.create(worker)
    step()
end
if Events and Events.OnTickEvenPaused then
    Events.OnTickEvenPaused.Add(function()
        local ok,t=pcall(now)
        if not ok then return end
        local worked,err=pcall(poll,t)
        if not worked then
            log("ERROR poll="..tostring(err))
            if job then endJob("error","review_server_logs")end
        end
    end)
else log("ERROR OnTickEvenPaused missing: Atlas disabled")end
