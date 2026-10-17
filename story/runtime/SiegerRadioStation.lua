-- SiegerRadio: root-operated, server-authoritative random-order radio playlist.
-- Separate from the one-shot FM text/cue system; no auto-start on installation.
-- PLAYLIST generated from story/radio/catalog.json; no arbitrary client audio.
if isClient and isClient() then return end
local VERSION="sr17-v1-18e25a69cca3"
local PLAYLIST={
    -- BEGIN RADIO PLAYLIST
    -- END RADIO PLAYLIST
}
local REQ="SiegerRadioStationRequest.txt"
local RESP="SiegerRadioStationResult.txt"
local STATE="SiegerRadioStationState.txt"
local FREQ=101300
local MAX_PLAYERS=32
local enabled=false
local lastReq=nil
local bag={}
local previous=nil
local track=nil
local nextAt=0
local sequence=0
local lastPoll=0
local initialized=false

local function log(m) print("SIEGER_RADIO_STATION "..tostring(m)) end
local function validID(s) return type(s)=="string" and #s==32 and s:match("^[0-9a-f]+$")~=nil end
local function fields(line)
    local out={}
    for field in (tostring(line or "").."\t"):gmatch("([^\t]*)\t") do out[#out+1]=field end
    return out
end
local function emit(mode,id,status,detail)
    local f=getFileWriter(RESP,true,false)
    if not f then error("Station response writer unavailable") end
    f:write(table.concat({"v1",id,mode,status,detail or "-"},"\t").."\n")
    f:close()
end
local function persist()
    local f=getFileWriter(STATE,true,false)
    if not f then error("Station state storage unavailable") end
    f:write("v1\t"..(enabled and "on" or "off").."\n")
    f:close()
end
local function readState()
    if initialized then return end
    initialized=true
    local previous=getFileReader(RESP,false)
    if previous then
        local line=previous:readLine()
        previous:close()
        local fieldsBefore=fields(line)
        if #fieldsBefore==5 and validID(fieldsBefore[2]) then lastReq=fieldsBefore[2] end
    end
    local r=getFileReader(STATE,false)
    if not r then return end
    local line=r:readLine()
    r:close()
    if line=="v1\ton" then enabled=true end
end
local function refill()
    bag={}
    for i,e in ipairs(PLAYLIST) do
        if type(e)~="table" or type(e.id)~="string"
           or e.id:match("^[a-z][a-z0-9_]+$")==nil
           or type(e.duration)~="number" or e.duration<5000
           or e.duration>720000 then error("Unapproved station playlist entry") end
        bag[i]=e
    end
    if #bag<2 or #bag>64 then error("Station needs 2..64 preinstalled music clips") end
    for i=#bag,2,-1 do
        local j=ZombRand(i)+1
        bag[i],bag[j]=bag[j],bag[i]
    end
    if previous and bag[#bag].id==previous then
        bag[1],bag[#bag]=bag[#bag],bag[1]
    end
end
local function currentPacket(nowMs)
    if not track then return nil end
    return {requestId=track.id,clip=track.clip,frequency=FREQ,
       scope="tuned",version=VERSION,durationMs=track.duration,
       remainingMs=math.max(0,nextAt-nowMs)}
end
local function nextTrack(nowMs)
    if #bag==0 then refill() end
    local e=table.remove(bag)
    previous=e.id
    sequence=sequence+1
    track={id=string.format("%032x",sequence),clip=e.id,duration=e.duration}
    nextAt=nowMs+e.duration
    if sendServerCommand then
        sendServerCommand("SiegerRadio","STATION_TRACK",currentPacket(nowMs))
    end
    log("TRACK "..e.id.." ms="..e.duration.." seq="..sequence)
end
local function checkWorld()
    if not SiegerStoryScenes or SiegerStoryScenes.world~="story_test" then
        error("Station only allowed in story_test")
    end
end
local function command()
    local r=getFileReader(REQ,false)
    if not r then return end
    local line=r:readLine()
    local extra=r:readLine()
    r:close()
    if extra or not line or #line>150 then return end
    local f=fields(line)
    if #f~=5 or f[1]~="v1" or not validID(f[2]) or f[3]~="story_test"
       or (f[4]~="start" and f[4]~="stop") or f[5]~=VERSION then return end
    if f[2]==lastReq then return end
    local id,mode=f[2],f[4]
    local ok,err=pcall(function()
        checkWorld()
        if mode=="start" then
            if enabled then error("Station already running") end
            refill() -- validate the actual installed playlist before any mutation
            enabled=true
            persist()
            nextTrack(getTimestampMs())
        else
            enabled=false
            persist()
            bag={}; track=nil; nextAt=0
            if sendServerCommand then
                sendServerCommand("SiegerRadio","STATION_STOP",{version=VERSION})
            end
        end
    end)
    lastReq=id
    local respOk,respErr=pcall(emit,mode,id,ok and "complete" or "error",
                              ok and (enabled and "on" or "off") or "review_server_log")
    if not respOk then log("ERROR writing ACK: "..tostring(respErr)) end
    if not ok then log("ERROR command "..mode..": "..tostring(err)) end
end
local function onHello(module,command,player,args)
    if module~="SiegerRadio" or command~="HELLO" or not player
        or not args or args.version~=VERSION or not enabled or not track then return end
    if sendServerCommand then
        sendServerCommand(player,"SiegerRadio","STATION_TRACK",currentPacket(getTimestampMs()))
    end
end
local function update()
    local now=getTimestampMs()
    if now<lastPoll or now-lastPoll<400 then return end
    lastPoll=now
    local ok,err=pcall(function()
        readState()
        checkWorld()
        command()
        if enabled and now>=nextAt then nextTrack(now) end
    end)
    if not ok then log("ERROR poll: "..tostring(err)) end
end
if Events then
    if Events.OnTick then Events.OnTick.Add(update) end
    if Events.OnClientCommand then Events.OnClientCommand.Add(onHello) end
end
