-- Root-operated, one-shot zombie clearance of EXACT Smokey's building only.
-- No permanent OnTick zombie scan: idle load is a file check every 120 ticks.
-- Does not target story_test elsewhere, nor any object/item/vehicle/player.
if isClient and isClient() then return end
local REQUEST="SiegerStoryBarRequest.txt"
local RESPONSE="SiegerStoryBarResult.txt"
local GUARD="SiegerStoryBarGuard.txt"
local X0,X1,Y0,Y1,Z0,Z1=10615,10628,9212,9235,0,1
local TICK=0
local processed=nil
local function fields(line)
    local t={}
    for s in tostring(line or ""):gmatch("[^\t]+") do t[#t+1]=s end
    return t
end
local function validID(id) return id and #id==32 and id:match("^[0-9a-f]+$") end
local function writeResult(id,op,status,count,removed,reason)
    local w=getFileWriter(RESPONSE,true,false)
    if not w then error("Response file inaccessible") end
    w:write(table.concat({"v1",id,"story_test",op,status,
        tostring(count),tostring(removed),reason or "-"},"\t").."\n")
    w:close()
end
local function log(msg) print("SIEGER_STORY_BAR "..tostring(msg)) end
local function inspectLoaded()
    local cell=getCell()
    if not cell or not cell.getGridSquare or not cell.getZombieList then
        error("Loaded-cell or zombie API unavailable")
    end
    -- Four known floor cells (including upper residential room) must be loaded.
    for _,p in ipairs({
       {10617,9217,0},{10623,9228,0},
       {10617,9218,1},{10623,9229,1}
    }) do
        if not cell:getGridSquare(p[1],p[2],p[3]) then
            error("Smokey's floor not sufficiently loaded; no clearance attempted")
        end
    end
    local all=cell:getZombieList()
    if not all then error("Zombie list unavailable") end
    if all:size()>10000 then error("Loaded zombie population exceeds safe audit limit") end
    local targets={}
    for i=0,all:size()-1 do
        local obj=all:get(i)
        if obj and instanceof(obj,"IsoZombie") then
            local x,y,z=obj:getX(),obj:getY(),obj:getZ()
            if type(x)=="number" and type(y)=="number" and type(z)=="number"
                and x>=X0 and x<X1+1 and y>=Y0 and y<Y1+1
                and z>=Z0 and z<Z1+1 then
                if #targets>=256 then error("Bar zombie count >256; review before clearing") end
                targets[#targets+1]=obj
            end
        end
    end
    return targets
end
local function guard(id)
    local r=getFileReader(GUARD,false)
    if r then
        local prior=r:readLine()
        r:close()
        if prior==id then error("Previous clearance attempt uncertain; no retry") end
    end
    local w=getFileWriter(GUARD,true,false)
    if not w then error("Durable clearance guard unavailable") end
    w:write(id.."\n")
    w:close()
end
local function noNearbyPlayers()
    local players=getOnlinePlayers()
    if not players then error("Cannot inspect connected players") end
    for i=0,players:size()-1 do
        local p=players:get(i)
        if p then
            local x,y=p:getX(),p:getY()
            if x>=X0-8 and x<=X1+8 and y>=Y0-8 and y<=Y1+8 then
                error("Player too close to Smokey's; ask all players to stand outside 8-cell buffer")
            end
        end
    end
end
local function execute(id,op,expected)
    if not SiegerStoryScenes or SiegerStoryScenes.world~="story_test" then
        error("World mismatch; story_test only")
    end
    local targets=inspectLoaded()
    if op=="inspect" then return #targets,0 end
    if op~="clear" then error("Invalid bar operation") end
    noNearbyPlayers()
    if expected~=#targets then error("Zombie population changed since preview") end
    if not VirtualZombieManager or not VirtualZombieManager.instance
        or not VirtualZombieManager.instance.removeZombieFromWorld then
        error("Pinned Build 42 zombie removal API missing")
    end
    guard(id)
    local removed=0
    for _,z in ipairs(targets) do
        if not VirtualZombieManager.instance:removeZombieFromWorld(z) then
            error("Zombie removal failed after "..removed.."; manual audit required")
        end
        removed=removed+1
    end
    return #targets,removed
end
local function poll()
    local r=getFileReader(REQUEST,false)
    if not r then return end
    local line=r:readLine()
    local extra=r:readLine()
    r:close()
    if extra or not line or #line>100 then return end
    local f=fields(line)
    if #f~=5 or f[1]~="v1" or not validID(f[2])
        or f[3]~="story_test" or (f[4]~="inspect" and f[4]~="clear")
        or not f[5]:match("^%d+$") then return end
    if f[2]==processed then return end
    local count=tonumber(f[5])
    if not count or count<0 or count>256 or (f[4]=="inspect" and count~=0) then return end
    processed=f[2]
    local ok,found,removed=pcall(execute,f[2],f[4],count)
    local status=ok and "complete" or "error"
    local reason=ok and "server_ack" or "manual_review_game_logs"
    if not ok then
        log("ERROR id="..f[2].." reason="..tostring(found))
        found=0;removed=0
    end
    local written,err=pcall(writeResult,f[2],f[4],status,found,removed,reason)
    if not written then log("ERROR result file write "..tostring(err)) end
end
local function tick()
    TICK=TICK+1
    if TICK%120==0 then
        local ok,err=pcall(poll)
        if not ok then log("ERROR poll "..tostring(err))end
    end
end
if Events and Events.OnTick then Events.OnTick.Add(tick)
else log("ERROR OnTick unavailable; module disabled") end
