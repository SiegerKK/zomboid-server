-- One-shot full census of all CURRENTLY LOADED infected in story_test.
-- No background zombie hooks, per-zombie instrumentation, forced cell loads,
-- artificial sample cap or chunked multi-tick processing.
-- One file poll every 180 ticks when idle; each census is a single O(N) pass.
if isClient and isClient() then return end
local REQUEST="SiegerStoryTLOURequest.txt"
local RESPONSE="SiegerStoryTLOUResult.txt"
local TICK_INTERVAL=180
local TYPES={"TLOU_Runner","TLOU_Stalker","TLOU_Clicker","TLOU_Bloater"}
local SETTINGS={"VanillaSpawn","RunnerSpawnWeight","StalkerSpawnWeight",
    "ClickerSpawnWeight","BloaterSpawn","HideIndoors","OnlyUnexplored","WanderAtNight"}
local tickCount,processed=0,nil
local initialized=false
local function log(s) print("SIEGER_STORY_TLOU "..tostring(s)) end
local function split(line)
    local result,start={},1
    while true do
        local pos=line:find("\t",start,true)
        if not pos then result[#result+1]=line:sub(start);return result end
        result[#result+1]=line:sub(start,pos-1);start=pos+1
    end
end
local function validID(s)
    return type(s)=="string" and #s==32 and s:match("^[0-9a-f]+$")~=nil
end
local function scalar(v)
    if v==nil then return "-" end
    if type(v)=="boolean" then return tostring(v) end
    if type(v)=="number" and v==v and v>=0 and v<=1000000000 then
        return tostring(v)
    end
    return "-"
end
local function writeResult(id,mode,status,reason,rows,user)
    if user then
        local bytes=512
        for _,row in ipairs(rows) do bytes=bytes+#table.concat(row,"\t")+1 end
        if bytes>32*1024*1024 then error("roster_response_too_large") end
    end
    local writer=getFileWriter(RESPONSE,true,false)
    if not writer then error("result_writer_missing") end
    local ok,err=pcall(function()
        local header={user and "v3" or "v2",id,"story_test",mode,status,reason,tostring(#rows)}
        if user then header[#header+1]=user end
        writer:write(table.concat(header,"\t").."\n")
        for _,row in ipairs(rows) do
            writer:write(table.concat(row,"\t").."\n")
        end
        writer:write("end\n")
    end)
    writer:close()
    if not ok then error(err) end
end
local cachedForge=nil
local function getForge()
    -- Do not require() or initialize the Forge module as a side effect.
    if type(ZomboidForge)=="table" then return ZomboidForge end
    if package and package.loaded then
        local loaded=package.loaded["ZomboidForge_module"]
        if type(loaded)=="table" then return loaded end
    end
    if cachedForge then return cachedForge end
    -- B42 Kahlua has no standard package.loaded. Its already-loaded files
    -- and return values live in LuaManager.loaded / loadedReturn instead.
    -- The pinned RunLuaInternal returns loadedReturn BEFORE compilation.
    -- Only consult require after confirming this exact, fixed module was
    -- already loaded. Never initialize Forge merely to produce diagnostics.
    if getLoadedLuaCount and getLoadedLua and require then
        local ok,count=pcall(getLoadedLuaCount)
        if ok and type(count)=="number" and count>=0 and count<=100000
            and count==math.floor(count) then
            for i=0,count-1 do
                local valid,path=pcall(getLoadedLua,i)
                if valid and type(path)=="string" then
                    path=path:gsub("\\","/")
                    if path=="ZomboidForge_module.lua"
                        or path:match("/ZomboidForge_module%.lua$") then
                        local found,module=pcall(require,"ZomboidForge_module")
                        if found and type(module)=="table" then
                            cachedForge=module
                            return module
                        end
                        return nil
                    end
                end
            end
        end
    end
    return nil
end
local function registry(forge)
    local rows={}
    local entries=forge and forge.ZTypes
    rows[#rows+1]={"framework",entries and "available" or "unavailable",
        forge and type(forge.NonPersistentZData)=="table" and "yes" or "no"}
    for _,name in ipairs(TYPES) do
        local typeInfo=entries and entries[name]
        if type(typeInfo)=="table" then
            rows[#rows+1]={"ztype",name,scalar(typeInfo.chance),
                scalar(typeInfo.HP),scalar(typeInfo.walktype),
                scalar(typeInfo.hearing),scalar(typeInfo.sight),
                type(typeInfo.onTick)=="table" and tostring(#typeInfo.onTick) or "-"}
        else
            rows[#rows+1]={"ztype",name,"not_registered","-","-","-","-","-"}
        end
    end
    local sandbox=SandboxVars and SandboxVars.TLOU_infected
    for _,key in ipairs(SETTINGS) do
        rows[#rows+1]={"setting",key,scalar(sandbox and sandbox[key])}
    end
    return rows
end
local function bin()
    return {count=0,healthCount=0,healthTotal=0,movingCount=0,movingKnown=0,
        targetCount=0,targetKnown=0}
end
local function updateBin(b,z)
    b.count=b.count+1
    if z.getHealth then
        local ok,n=pcall(function()return z:getHealth()end)
        if ok and type(n)=="number" and n==n and n>=0 and n<=100000 then
            b.healthCount=b.healthCount+1;b.healthTotal=b.healthTotal+n
        end
    end
    if z.isMoving then
        local ok,value=pcall(function()return z:isMoving()end)
        if ok and type(value)=="boolean" then
            b.movingKnown=b.movingKnown+1
            if value then b.movingCount=b.movingCount+1 end
        end
    end
    if z.getTarget then
        local ok,value=pcall(function()return z:getTarget()end)
        if ok then
            b.targetKnown=b.targetKnown+1
            if value then b.targetCount=b.targetCount+1 end
        end
    end
end
local function classify(z,forge)
    -- Forge.GetZType is NOT a pure query: it initializes per-zombie cache
    -- and can dress z if its outfit id is zero. Read the EXISTING ZType
    -- cache only. Never initialize Forge metadata during diagnostics.
    local cache=forge and forge.NonPersistentZData
    local record=type(cache)=="table" and cache[z] or nil
    if type(record)=="table" and record.ZType~=nil then
        if type(record.ZType)~="string" then return "unknown",true,false end
        for _,key in ipairs(TYPES) do
            if record.ZType==key then return key,false,false end
        end
        return "other",false,false
    end
    if z.getPersistentOutfitID then
        local ok,id=pcall(function()return z:getPersistentOutfitID()end)
        if ok and type(id)=="number" and id==0 then
            return "unknown",false,true
        end
    end
    return "unknown",false,false
end
local function census(forge)
    if not getCell then error("cell_api_missing") end
    local cell=getCell()
    if not cell or not cell.getZombieList then error("loaded_zombies_api_missing") end
    local list=cell:getZombieList()
    if not list or not list.size or not list.get then error("zombie_list_unavailable") end
    local total=list:size()
    if type(total)~="number" or total<0 or total~=math.floor(total) then
        error("invalid_zombie_list_size")
    end
    local stats={other=bin(),unknown=bin()}
    for _,key in ipairs(TYPES) do stats[key]=bin() end
    local skipped,errors,uninitialized=0,0,0
    local start=nil
    if getTimestampMs then
        local ok,v=pcall(getTimestampMs)
        if ok and type(v)=="number" and v==v then start=v end
    end
    -- Snapshot the collection length once. Each slot is visited exactly
    -- once; no sampling, pagination, sleeping or persistent instrumentation.
    for i=0,total-1 do
        local z=list:get(i)
        if z then
            local kind,bad,unready=classify(z,forge)
            if bad then errors=errors+1 end
            if unready then uninitialized=uninitialized+1 end
            updateBin(stats[kind],z)
        else
            skipped=skipped+1
        end
    end
    local elapsed="-"
    if start and getTimestampMs then
        local ok,v=pcall(getTimestampMs)
        if ok and type(v)=="number" and v==v and v>=start then
            elapsed=tostring(math.floor(v-start))
        end
    end
    local result={{"census",tostring(total),tostring(total-skipped),
        tostring(skipped),tostring(errors),tostring(uninitialized),
        elapsed,"loaded_list_only"}}
    for _,key in ipairs(TYPES) do
        local b=stats[key]
        result[#result+1]={"observed",key,tostring(b.count),
            tostring(b.healthCount),
            b.healthCount>0 and string.format("%.2f",b.healthTotal/b.healthCount) or "-",
            tostring(b.movingCount),tostring(b.movingKnown),
            tostring(b.targetCount),tostring(b.targetKnown)}
    end
    for _,key in ipairs({"other","unknown"}) do
        local b=stats[key]
        result[#result+1]={"observed",key,tostring(b.count),
            tostring(b.healthCount),
            b.healthCount>0 and string.format("%.2f",b.healthTotal/b.healthCount) or "-",
            tostring(b.movingCount),tostring(b.movingKnown),
            tostring(b.targetCount),tostring(b.targetKnown)}
    end
    return result
end
-- One synchronous snapshot; IDs are session-local, not persistent identity.
local function roster(forge,user)
    if not getOnlinePlayers then error("players_api_missing") end
    local players=getOnlinePlayers()
    if not players or not players.size or not players.get then error("players_missing") end
    local player=nil
    for i=0,players:size()-1 do
        local p=players:get(i)
        if p and p:getUsername()==user then
            if player then error("ambiguous_player") end
            player=p
        end
    end
    if not player then error("target_player_offline") end
    local function coordinate(v)
        if type(v)~="number" or v~=v or math.abs(v)>1000000 then
            error("invalid_coordinate") end
        return v
    end
    local px,py,pz=coordinate(player:getX()),coordinate(player:getY()),coordinate(player:getZ())
    local function decimal(v) return string.format("%.6f",v) end
    local rows={{"origin",user,decimal(px),decimal(py),decimal(pz)}}
    if not getCell then error("cell_api_missing") end
    local cell=getCell()
    if not cell or not cell.getZombieList then error("loaded_zombies_api_missing") end
    local list=cell:getZombieList()
    if not list or not list.size or not list.get then error("zombie_list_unavailable") end
    local total=list:size()
    if type(total)~="number" or total<0 or total~=math.floor(total) then error("invalid_zombie_list_size") end
    local seen,skipped=0,0
    for i=0,total-1 do
        local z=list:get(i)
        if z then
            local kind=classify(z,forge)
            local record=forge and forge.NonPersistentZData and forge.NonPersistentZData[z]
            if record and type(record.ZType)=="string" then
                local raw=record.ZType
                if #raw>96 or not raw:match("^[A-Za-z0-9_%.%-]+$") then error("invalid_cached_type") end
                kind=raw
            end
            local x,y,zz=coordinate(z:getX()),coordinate(z:getY()),coordinate(z:getZ())
            local online="-"
            if z.getOnlineID then
                local ok,id=pcall(function()return z:getOnlineID()end)
                if ok and type(id)=="number" and id==math.floor(id) and id>=0 and id<=2147483647 then online=tostring(id) end
            end
            local dx,dy=x-px,y-py
            rows[#rows+1]={"zombie",tostring(i),online,kind,decimal(x),decimal(y),decimal(zz),
                decimal(math.sqrt(dx*dx+dy*dy)),decimal(zz-pz)}
            seen=seen+1
        else skipped=skipped+1 end
    end
    table.insert(rows,2,{"coverage",tostring(total),tostring(seen),tostring(skipped),"loaded_list_only"})
    return rows
end
local function poll()
    if not initialized then
        local previous=getFileReader(RESPONSE,false)
        if previous then
            local first=previous:readLine()
            previous:close()
            local f=split(first or "")
            if (f[1]=="v1" or f[1]=="v2" or f[1]=="v3") and validID(f[2]) then
                processed=f[2]
            end
        end
        initialized=true
    end
    local read=getFileReader(REQUEST,false)
    if not read then return end
    local line=read:readLine()
    local extra=read:readLine()
    read:close()
    if not line or #line>220 or extra then return end
    local fields=split(line)
    local user=nil
    if fields[1]=="v3" then
        if #fields~=5 or fields[4]~="roster" or not fields[5]
            or #fields[5]>40 or not fields[5]:match("^[A-Za-z0-9_][A-Za-z0-9_.%-]*$") then return end
        user=fields[5]
    elseif fields[1]~="v2" or #fields~=4 or
        (fields[4]~="registry" and fields[4]~="census") then return end
    if not validID(fields[2]) or fields[3]~="story_test" then return end
    if fields[2]==processed then return end
    processed=fields[2]
    local ok,err=pcall(function()
        if not SiegerStoryScenes or SiegerStoryScenes.world~="story_test" then
            error("story_world_mismatch") end
        local forge=getForge()
        local rows=user and roster(forge,user) or registry(forge)
        if fields[4]=="census" then
            for _,row in ipairs(census(forge)) do rows[#rows+1]=row end
        end
        writeResult(fields[2],fields[4],"complete",
            user and "complete_loaded_roster" or (fields[4]=="census" and "complete_loaded_census" or "server_registry"),rows,user)
    end)
    if not ok then
        log("ERROR id="..fields[2].." "..tostring(err))
        pcall(writeResult,fields[2],fields[4],"error","review_server_logs",{},user)
    end
end
if Events and Events.OnTick then
    Events.OnTick.Add(function()
        tickCount=tickCount+1
        if tickCount%TICK_INTERVAL==0 then
            local ok,err=pcall(poll)
            if not ok then log("ERROR poll "..tostring(err)) end
        end
    end)
else log("ERROR OnTick absent: TLOU diagnostics disabled") end
