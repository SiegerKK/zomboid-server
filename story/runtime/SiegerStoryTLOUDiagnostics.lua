-- Read-only, opt-in TLOU / Zomboid Forge diagnostics for story_test.
-- Idle overhead: one private request-file check every 180 ticks. No hooks in
-- zombie AI, no memory-backed accumulator, no mass scan, no client traffic.
if isClient and isClient() then return end
local REQUEST="SiegerStoryTLOURequest.txt"
local RESPONSE="SiegerStoryTLOUResult.txt"
local MAX_SLOTS=512
local PER_TICK=16
local TICK_INTERVAL=180
local TYPES={"TLOU_Runner","TLOU_Stalker","TLOU_Clicker","TLOU_Bloater"}
local SETTINGS={"VanillaSpawn","RunnerSpawnWeight","StalkerSpawnWeight",
    "ClickerSpawnWeight","BloaterSpawn","HideIndoors","OnlyUnexplored","WanderAtNight"}
local tickCount=0
local active=nil
local lastId=nil
local initialized=false
local function log(s) print("SIEGER_STORY_TLOU "..tostring(s)) end
local function split(line)
    local parts,start={},1
    while true do
        local at=line:find("\t",start,true)
        if not at then parts[#parts+1]=line:sub(start);return parts end
        parts[#parts+1]=line:sub(start,at-1);start=at+1
    end
end
local function validID(x)
    return type(x)=="string" and #x==32 and x:match("^[0-9a-f]+$")~=nil
end
local function validPlayer(x)
    return type(x)=="string" and #x>0 and #x<=31 and
        x:match("^[A-Za-z0-9_][A-Za-z0-9_.%-]*$")~=nil
end
local function uint(x,min,max)
    if type(x)~="string" or not x:match("^%d+$") then return nil end
    local value=tonumber(x)
    if value and value>=min and value<=max and value==math.floor(value) then
        return value
    end
end
local function scalar(x)
    if x==nil then return "-" end
    if type(x)=="boolean" then return tostring(x) end
    if type(x)=="number" and x==x and x>=0 and x<=100000 then
        return tostring(x)
    end
    return "-"
end
local function lines(id,mode,status,reason,rows)
    local f=getFileWriter(RESPONSE,true,false)
    if not f then error("response_writer_unavailable") end
    local ok,err=pcall(function()
        f:write(table.concat({"v1",id,"story_test",mode,status,reason,
            tostring(#rows)},"\t").."\n")
        for _,row in ipairs(rows) do f:write(table.concat(row,"\t").."\n") end
        f:write("end\n")
    end)
    f:close()
    if not ok then error(err) end
end
local function loadedForge()
    -- Never require/add callbacks or initialize a module just to diagnose it.
    if type(ZomboidForge)=="table" then return ZomboidForge end
    if package and package.loaded then
        local f=package.loaded["ZomboidForge_module"]
        if type(f)=="table" then return f end
    end
    return nil
end
local function staticRows()
    local rows={}
    local forge=loadedForge()
    local registry=forge and forge.ZTypes
    rows[#rows+1]={"framework",registry and "available" or "unavailable",
        forge and type(forge.GetZType)=="function" and "yes" or "no"}
    for _,typeKey in ipairs(TYPES) do
        local data=registry and registry[typeKey]
        if type(data)~="table" then
            rows[#rows+1]={"ztype",typeKey,"not_registered","-","-","-","-","-"}
        else
            local callbacks=type(data.onTick)=="table" and #data.onTick or 0
            rows[#rows+1]={"ztype",typeKey,scalar(data.chance),scalar(data.HP),
                scalar(data.walktype),scalar(data.hearing),scalar(data.sight),
                scalar(callbacks)}
        end
    end
    local settings=SandboxVars and SandboxVars.TLOU_infected
    for _,key in ipairs(SETTINGS) do
        rows[#rows+1]={"setting",key,settings and scalar(settings[key]) or "-"}
    end
    return rows
end
local function playerByName(username)
    if not getOnlinePlayers then error("player_api_missing") end
    local users=getOnlinePlayers()
    if not users or not users.size or not users.get then error("players_unavailable") end
    local count=users:size()
    if count<0 or count>64 then error("players_collection_limit") end
    local player=nil
    for i=0,count-1 do
        local p=users:get(i)
        if p and tostring(p:getUsername())==username then
            if player then error("duplicate_online_login") end
            player=p
        end
    end
    if not player then error("player_not_online") end
    return player
end
local function startSample(id,username,radius,limit)
    if not getCell then error("cell_api_missing") end
    local cell=getCell()
    if not cell or not cell.getZombieList then error("zombie_list_unavailable") end
    local list=cell:getZombieList()
    if not list or not list.size or not list.get then error("zombie_collection_unavailable") end
    local total=list:size()
    if type(total)~="number" or total<0 or total>10000 then
        error("loaded_zombie_census_over_limit")
    end
    local player=playerByName(username)
    local x,y,z=player:getX(),player:getY(),player:getZ()
    if type(x)~="number" or type(y)~="number" or type(z)~="number"
        or x~=x or y~=y or z~=z then error("invalid_player_coordinates") end
    local limitCount=math.min(total,limit)
    local observed={other=0,unknown=0}
    for _,key in ipairs(TYPES) do observed[key]=0 end
    active={id=id,username=username,radius=radius,limit=limit,
        size=total,slots=limitCount,cursor=0,
        ticks=0,x=x,y=y,z=z,collection=list,found=0,observed=observed,
        healthSum=0,healthValid=0,moving=0,movingValid=0,
        targeted=0,targetValid=0,classificationErrors=0,
        forge=loadedForge()}
end
local function scanOne(job)
    local offset=math.floor(job.cursor*job.size/job.slots)
    local zombie=job.collection:get(offset)
    job.cursor=job.cursor+1
    if not zombie then return end
    local x,y,z=zombie:getX(),zombie:getY(),zombie:getZ()
    if type(x)~="number" or type(y)~="number" or type(z)~="number"
        or x~=x or y~=y or z~=z then error("invalid_zombie_coordinates") end
    local dx,dy,dz=x-job.x,y-job.y,(z-job.z)*3
    if dx*dx+dy*dy+dz*dz>job.radius*job.radius then return end
    job.found=job.found+1
    local kind="unknown"
    if job.forge and type(job.forge.GetZType)=="function" then
        local ok,got=pcall(job.forge.GetZType,zombie)
        if ok and type(got)=="string" then
            kind=job.observed[got]~=nil and got or "other"
        else
            job.classificationErrors=job.classificationErrors+1
        end
    end
    job.observed[kind]=job.observed[kind]+1
    if zombie.getHealth then
        local ok,v=pcall(function()return zombie:getHealth()end)
        if ok and type(v)=="number" and v==v and v>=0 and v<=100000 then
            job.healthValid=job.healthValid+1
            job.healthSum=job.healthSum+v
        end
    end
    if zombie.isMoving then
        local ok,v=pcall(function()return zombie:isMoving()end)
        if ok and type(v)=="boolean" then
            job.movingValid=job.movingValid+1
            if v then job.moving=job.moving+1 end
        end
    end
    if zombie.getTarget then
        local ok,v=pcall(function()return zombie:getTarget()end)
        if ok then
            job.targetValid=job.targetValid+1
            if v then job.targeted=job.targeted+1 end
        end
    end
end
local function finish()
    local job=active
    active=nil
    local rows=staticRows()
    rows[#rows+1]={"sample",job.username,tostring(job.radius),tostring(job.size),
        tostring(job.cursor),tostring(job.found),tostring(job.ticks),
        tostring(PER_TICK),tostring(job.classificationErrors)}
    for _,kind in ipairs(TYPES) do
        rows[#rows+1]={"observed",kind,tostring(job.observed[kind])}
    end
    rows[#rows+1]={"observed","other",tostring(job.observed.other)}
    rows[#rows+1]={"observed","unknown",tostring(job.observed.unknown)}
    rows[#rows+1]={"activity",tostring(job.healthValid),
        job.healthValid>0 and string.format("%.2f",job.healthSum/job.healthValid) or "-",
        tostring(job.moving),tostring(job.movingValid),
        tostring(job.targeted),tostring(job.targetValid)}
    lines(job.id,"sample","complete","sampled_loaded_only",rows)
end
local function progress()
    if not active then return end
    local job=active
    job.ticks=job.ticks+1
    for i=1,PER_TICK do
        if job.cursor>=job.slots then break end
        scanOne(job)
    end
    if job.cursor>=job.slots then finish() end
end
local function poll()
    if not initialized then
        local r=getFileReader(RESPONSE,false)
        if r then
            local first=r:readLine()
            r:close()
            local f=split(first or "")
            if f[1]=="v1" and validID(f[2]) then lastId=f[2] end
        end
        initialized=true
    end
    local r=getFileReader(REQUEST,false)
    if not r then return end
    local line=r:readLine()
    local extra=r:readLine()
    r:close()
    if not line or #line>220 or extra then return end
    local f=split(line)
    if #f~=7 or f[1]~="v1" or not validID(f[2]) or
        f[3]~="story_test" or (f[4]~="registry" and f[4]~="sample") then
        return
    end
    if f[2]==lastId then return end
    local username,radius,limit=f[5],uint(f[6],0,30),uint(f[7],0,MAX_SLOTS)
    if not radius or not limit then return end
    if (f[4]=="registry" and (username~="-" or radius~=0 or limit~=0))
        or (f[4]=="sample" and (not validPlayer(username) or
            radius<1 or limit<16)) then return end
    lastId=f[2]
    local ok,err=pcall(function()
        if not SiegerStoryScenes or SiegerStoryScenes.world~="story_test" then
            error("world_mismatch") end
        if f[4]=="registry" then
            lines(f[2],f[4],"complete","server_registry",staticRows())
        else
            startSample(f[2],username,radius,limit)
            if active.slots==0 then finish() end
        end
    end)
    if not ok then
        active=nil
        log("ERROR request="..f[2].." "..tostring(err))
        local saved,why=pcall(lines,f[2],f[4],"error","review_server_logs",{})
        if not saved then log("ERROR result_writer "..tostring(why))end
    end
end
if Events and Events.OnTick then
    Events.OnTick.Add(function()
        tickCount=tickCount+1
        if active then
            local ok,err=pcall(progress)
            if not ok then
                local job=active
                active=nil
                log("ERROR sample="..job.id.." "..tostring(err))
                pcall(lines,job.id,"sample","error","review_server_logs",{})
            end
        elseif tickCount%TICK_INTERVAL==0 then
            local ok,err=pcall(poll)
            if not ok then log("ERROR poll "..tostring(err)) end
        end
    end)
else
    log("ERROR missing OnTick: diagnostics disabled")
end
