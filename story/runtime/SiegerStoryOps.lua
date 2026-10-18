-- B42 dedicated server. Root-only, bounded read-only live operator snapshots.
-- Requests are private files under the selected story_test world /Lua dir.
-- No client commands, arbitrary Lua, chunk loading or game-state mutation.
if isClient and isClient() then return end

local REQUEST="SiegerStoryOpsRequest.txt"
local RESPONSE="SiegerStoryOpsResult.txt"
local tickCount=0
local initialized=false
local processed=nil
local MAX_PLAYERS=64
local MAX_ZOMBIES=10000
local MAX_VEHICLES=256

local function log(message)
    print("SIEGER_STORY_OPS "..tostring(message))
end
local function split(line)
    local result,offset={},1
    while true do
        local pos=line:find("\t",offset,true)
        if not pos then
            result[#result+1]=line:sub(offset)
            return result
        end
        result[#result+1]=line:sub(offset,pos-1)
        offset=pos+1
    end
end
local function validId(s)
    return type(s)=="string" and #s==32 and s:match("^[0-9a-f]+$")~=nil
end
local function validUser(s)
    return type(s)=="string" and #s>=1 and #s<=31
        and s:match("^[A-Za-z0-9_][A-Za-z0-9_.%-]*$")~=nil
end
local function integer(s,min,max)
    if type(s)~="string" or not s:match("^%d+$") then return nil end
    local n=tonumber(s)
    if n and n>=min and n<=max and n==math.floor(n) then return n end
end
local function finite(n)
    return type(n)=="number" and n==n and n>-100000 and n<200000
end
local function coordinate(n)
    if not finite(n) then error("invalid_world_coordinate") end
    return string.format("%.1f",n)
end
local function writeResult(id,op,status,reason,rows)
    local w=getFileWriter(RESPONSE,true,false)
    if not w then error("response_writer_missing") end
    local ok,err=pcall(function()
        w:write(table.concat({"v1",id,"story_test",op,status,reason,tostring(#rows)},"\t").."\n")
        for _,row in ipairs(rows) do w:write(table.concat(row,"\t").."\n") end
        w:write("end\n")
    end)
    w:close()
    if not ok then error(err) end
end
local function online()
    if not getOnlinePlayers then error("online_players_api_missing") end
    local list=getOnlinePlayers()
    if not list or not list.size or not list.get then error("online_players_unavailable") end
    local size=list:size()
    if not size or size<0 or size>MAX_PLAYERS then error("online_player_limit") end
    return list,size
end
local function snapshot(op,username,radius)
    if not SiegerStoryScenes or SiegerStoryScenes.world~="story_test" then
        error("story_world_mismatch")
    end
    local players,count=online()
    local rows={}
    local seen={}
    local target=nil
    for i=0,count-1 do
        local p=players:get(i)
        if not p then error("null_online_player") end
        local user=tostring(p:getUsername())
        if not validUser(user) or seen[user] then error("invalid_online_player_name") end
        seen[user]=true
        if user==username then target=p end
        if op=="players" then
            local vehicleId="-"
            if p.getVehicle then
                local car=p:getVehicle()
                if car then
                    if not car.getId then error("online_car_id_unavailable") end
                    local id=car:getId()
                    if not finite(id) or id<1 or id~=math.floor(id) then
                        error("invalid_online_car_id")
                    end
                    vehicleId=tostring(id)
                end
            end
            rows[#rows+1]={"player",user,coordinate(p:getX()),
                coordinate(p:getY()),coordinate(p:getZ()),vehicleId}
        end
    end
    if op=="players" then
        table.sort(rows,function(a,b)return a[2]<b[2]end)
        return rows
    end
    if not target then error("target_player_not_online") end
    if not getCell then error("world_cell_api_missing") end
    local cell=getCell()
    if not cell or not cell.getZombieList or not cell.getVehicles
        or not cell.getGridSquare then error("world_census_api_missing") end
    local px,py,pz=target:getX(),target:getY(),target:getZ()
    if not finite(px) or not finite(py) or not finite(pz) then
        error("invalid_target_coordinates") end
    local range2=radius*radius
    local function sq(x,y,z)
        if not finite(x) or not finite(y) or not finite(z) then
            error("invalid_entity_coordinates") end
        local dx,dy,dz=x-px,y-py,3*(z-pz)
        return dx*dx+dy*dy+dz*dz
    end
    local zombies=cell:getZombieList()
    if not zombies or not zombies.size or not zombies.get then
        error("zombie_collection_unavailable") end
    local total=zombies:size()
    if total<0 or total>MAX_ZOMBIES then error("zombie_census_limit") end
    local countZ,nearest=0,nil
    for i=0,total-1 do
        local z=zombies:get(i)
        if z then
            local d2=sq(z:getX(),z:getY(),z:getZ())
            if d2<=range2 then
                countZ=countZ+1
                if not nearest or d2<nearest then nearest=d2 end
            end
        end
    end
    local cars=cell:getVehicles()
    if not cars or not cars.iterator then error("vehicle_iterator_unavailable") end
    local iter=cars:iterator()
    local checked,countV=0,0
    while iter:hasNext() do
        checked=checked+1
        if checked>MAX_VEHICLES then error("vehicle_census_limit") end
        local car=iter:next()
        if car and sq(car:getX(),car:getY(),car:getZ())<=range2 then
            countV=countV+1
        end
    end
    local nearbyPlayers=0
    for i=0,count-1 do
        local p=players:get(i)
        if p~=target and sq(p:getX(),p:getY(),p:getZ())<=range2 then
            nearbyPlayers=nearbyPlayers+1
        end
    end
    -- Coverage counts loaded tiles only; never force-load unloaded squares.
    local loaded,checkedTiles=0,0
    local tx,ty,tz=math.floor(px),math.floor(py),math.floor(pz)
    for x=tx-radius,tx+radius do
        for y=ty-radius,ty+radius do
            local dx,dy=x-tx,y-ty
            if dx*dx+dy*dy<=range2 then
                checkedTiles=checkedTiles+1
                if cell:getGridSquare(x,y,tz) then loaded=loaded+1 end
            end
        end
    end
    rows[1]={"nearby",username,tostring(radius),tostring(countZ),
        nearest and string.format("%.1f",math.sqrt(nearest)) or "-",
        tostring(countV),tostring(nearbyPlayers),tostring(loaded),tostring(checkedTiles)}
    return rows
end

local function poll()
    if not initialized then
        local ok,r=pcall(getFileReader,RESPONSE,false)
        if ok and r then
            local head=r:readLine()
            r:close()
            local f=split(head or "")
            if f[1]=="v1" and validId(f[2]) then processed=f[2] end
        end
        initialized=true
    end
    local reader=getFileReader(REQUEST,false)
    if not reader then return end
    local line=reader:readLine()
    local extra=reader:readLine()
    reader:close()
    if not line or #line>200 or extra then return end
    local f=split(line)
    if #f~=6 or f[1]~="v1" or not validId(f[2])
        or f[3]~="story_test" or (f[4]~="players" and f[4]~="nearby") then
        return
    end
    if processed==f[2] then return end
    local radius=integer(f[6],0,20)
    if not radius or (f[4]=="players" and (f[5]~="-" or radius~=0))
        or (f[4]=="nearby" and (not validUser(f[5]) or radius<1)) then
        return
    end
    processed=f[2]
    local ok,rows=pcall(snapshot,f[4],f[5],radius)
    if not ok then
        log("ERROR id="..f[2].." reason="..tostring(rows))
        rows={}
    end
    local success,err=pcall(writeResult,f[2],f[4],ok and "complete" or "error",
        ok and "server_snapshot" or "review_server_logs",rows)
    if not success then log("ERROR write failed "..tostring(err)) end
end
if Events and Events.OnTick then
    Events.OnTick.Add(function()
        tickCount=tickCount+1
        if tickCount%120==0 then
            local ok,err=pcall(poll)
            if not ok then log("ERROR poll "..tostring(err)) end
        end
    end)
else
    log("ERROR OnTick missing: ops disabled")
end
