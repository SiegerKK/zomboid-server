-- Minimal, opt-in client bridge for server-commanded Route 17 audio.
-- Receives registered cues through portable, installed IsoRadio furniture
-- and powered vehicle radio parts, without world-wide sound leakage.
-- Nearby speakers use a 3D emitter. Audio is client-local, server sequenced.
if isServer and isServer() then return end

local VERSION="sr17-v1-3793697ee41b"
local CLIENT_BUILD="radio-merge10"
local MODULE="SiegerRadio"
local SOUNDS={
    -- BEGIN RADIO CATALOG
    north_track_01="SiegerRadio_NorthTrack01",
    north_track_02="SiegerRadio_NorthTrack02",
    north_track_03="SiegerRadio_NorthTrack03",
    north_track_04="SiegerRadio_NorthTrack04",
    north_track_05="SiegerRadio_NorthTrack05",
    north_track_06="SiegerRadio_NorthTrack06",
    north_track_07="SiegerRadio_NorthTrack07",
    north_track_08="SiegerRadio_NorthTrack08",
    north_track_09="SiegerRadio_NorthTrack09",
    north_track_10="SiegerRadio_NorthTrack10",
    north_track_11="SiegerRadio_NorthTrack11",
    north_track_12="SiegerRadio_NorthTrack12",
    north_track_13="SiegerRadio_NorthTrack13",
    north_track_14="SiegerRadio_NorthTrack14",
    north_track_15="SiegerRadio_NorthTrack15",
    north_track_16="SiegerRadio_NorthTrack16",
    north_track_17="SiegerRadio_NorthTrack17",
    north_track_18="SiegerRadio_NorthTrack18",
    north_track_19="SiegerRadio_NorthTrack19",
    north_track_20="SiegerRadio_NorthTrack20",
    north_track_21="SiegerRadio_NorthTrack21",
    north_track_22="SiegerRadio_NorthTrack22",
    north_track_23="SiegerRadio_NorthTrack23",
    north_track_24="SiegerRadio_NorthTrack24",
    north_track_25="SiegerRadio_NorthTrack25",
    north_track_26="SiegerRadio_NorthTrack26",
    north_track_27="SiegerRadio_NorthTrack27",
    north_track_28="SiegerRadio_NorthTrack28",
    north_track_29="SiegerRadio_NorthTrack29",
    north_track_30="SiegerRadio_NorthTrack30",
    north_track_31="SiegerRadio_NorthTrack31",
    north_track_32="SiegerRadio_NorthTrack32",
    north_track_33="SiegerRadio_NorthTrack33",
    north_track_34="SiegerRadio_NorthTrack34",
    north_track_35="SiegerRadio_NorthTrack35",
    north_track_36="SiegerRadio_NorthTrack36",
    north_track_37="SiegerRadio_NorthTrack37",
    north_track_38="SiegerRadio_NorthTrack38",
    north_track_39="SiegerRadio_NorthTrack39",
    north_track_40="SiegerRadio_NorthTrack40",
    north_track_41="SiegerRadio_NorthTrack41",
    test_tone="SiegerRadio_TestTone",
    -- END RADIO CATALOG
}
local tickCount=0
local acked=false
local STATION_FREQ=101200
local RANGE=12
local VEHICLE_RANGE=30  -- cars only; stationary furniture stays at 12
local lastSourceScan=0
local active=nil
local station=nil
local stationPlayback=nil -- One on-demand native stream; absent without reception.
local helloTries=0
local played={}
local playedOrder={}

local function log(message)
    print("SIEGER_RADIO_CLIENT "..tostring(message))
end

local function playerLocal()
    if getSpecificPlayer then return getSpecificPlayer(0) end
    return getPlayer and getPlayer() or nil
end

local function sendHello()
    if acked or helloTries>=10 or not sendClientCommand then return end
    -- No false-ready handshake from an outdated/unapproved client Java bridge.
    if type(siegradioBridgeReady)~="function"
        or type(siegradioBridgeBuild)~="function" then return end
    local ok,ready=pcall(siegradioBridgeReady)
    local valid,build=pcall(siegradioBridgeBuild)
    if not ok or ready~=true or not valid or build~=CLIENT_BUILD then return end
    local p=playerLocal()
    if not p then return end
    helloTries=helloTries+1
    sendClientCommand(p,MODULE,"HELLO",{version=VERSION,build=CLIENT_BUILD})
end

local function deviceTuned(device,frequency,kind)
    if not device then return false end
    local ok,result=pcall(function()
        if not (device:getIsTurnedOn()==true
            and device:getChannel()==frequency
            and device:getDeviceVolume()>0
            and device:getIsTelevision()~=true) then return false end
        if kind=="vehicle" then return true end  -- VehiclePart.hasDevicePower checked separately
        if kind=="furniture" then
            return device:canBePoweredHere()==true or device:getPower()>0
        end
        return device:getPower()>0
    end)
    return ok and result==true
end

-- Return an actual active receiver, not merely a visual world item.
local function inspectedDevice(device,frequency,kind)
    if not deviceTuned(device,frequency,kind) then return nil end
    local volume=0.5
    local ok,value=pcall(function()return device:getDeviceVolume()end)
    if ok and type(value)=="number" then volume=math.min(1,math.max(0.01,value))end
    return volume
end

local function radioInInventory(player,frequency)
    if not player or not player.getInventory then return nil end
    local inventory=player:getInventory()
    if not inventory or not inventory.getItems then return nil end
    local entries=inventory:getItems()
    if not entries or entries:size()>512 then return nil end
    local function check(item)
        if not item or not item.getDeviceData then return nil end
        local ok,device=pcall(function()return item:getDeviceData()end)
        if not ok then return nil end
        return inspectedDevice(device,frequency,"portable")
    end
    for i=0,entries:size()-1 do
        local v=check(entries:get(i))
        if v then return {kind="portable",object=player,volume=v} end
    end
    -- A held device already in top-level inventory is the same receiver.
    for _,item in ipairs({player:getPrimaryHandItem(),player:getSecondaryHandItem()}) do
        local v=check(item)
        if v then return {kind="portable",object=player,volume=v} end
    end
end

local function sqDistance(player,x,y,z)
    local dx=player:getX()-x
    local dy=player:getY()-y
    local dz=(player:getZ()-z)*3
    return dx*dx+dy*dy+dz*dz
end

local function radioInWorld(player,frequency)
    if not getCell then return nil end
    local cell=getCell()
    if not cell or not cell.getGridSquare then return nil end
    local px,py,pz=math.floor(player:getX()),math.floor(player:getY()),math.floor(player:getZ())
    local best,bestDistance=nil,RANGE*RANGE
    -- Fixed bounded 25x25x3 scan; do not truncate upper floors.
    for z=math.max(0,pz-1),pz+1 do
        for x=px-RANGE,px+RANGE do
            for y=py-RANGE,py+RANGE do
                if sqDistance(player,x+0.5,y+0.5,z)<bestDistance then
                    local square=cell:getGridSquare(x,y,z) -- never force-load chunks
                    local objects=square and square:getObjects()
                    if objects and objects:size()<=255 then
                        for i=0,objects:size()-1 do
                            local obj=objects:get(i)
                            if obj and instanceof and instanceof(obj,"IsoRadio")
                                and obj.getDeviceData then
                                local ok,d=pcall(function()return obj:getDeviceData()end)
                                local v=ok and inspectedDevice(d,frequency,"furniture")
                                if v then
                                    local dist=sqDistance(player,x+0.5,y+0.5,z)
                                    if dist<bestDistance then
                                        bestDistance=dist
                                        best={kind="furniture",object=obj,volume=v,
                                              x=x+0.5,y=y+0.5,z=z}
                                    end
                                end
                            end
                        end
                    end
                end
            end
        end
    end
    return best
end

local function radioInVehicle(player,car,frequency,occupied)
    if not car or not car.getX or not car.getPartCount then return nil end
    local x,y,z=car:getX(),car:getY(),car:getZ()
    -- The seated player's render/game coordinates can lag vehicle physics.
    -- getVehicle is authoritative membership, not an excuse to extend range
    -- for any outside listener.
    if not occupied and sqDistance(player,x,y,z)>=VEHICLE_RANGE*VEHICLE_RANGE then return nil end
    local count=car:getPartCount()
    if type(count)~="number" or count<0 or count>128 then return nil end
    for j=0,count-1 do
        local part=car:getPartByIndex(j)
        if part and part.getDeviceData and part.hasDevicePower then
            local ok,d=pcall(function()return part:getDeviceData()end)
            local vol=ok and inspectedDevice(d,frequency,"vehicle")
            if vol and part:hasDevicePower()==true then
                return {kind="vehicle",object=car,part=part,volume=vol,x=x,y=y,z=z}
            end
        end
    end
end

local function radioInVehicles(player,frequency)
    if not getCell then return nil end
    local cell=getCell()
    if not cell or not cell.getVehicles then return nil end
    local vehicles=cell:getVehicles()
    if not vehicles or vehicles:size()>256 or not vehicles.iterator then return nil end
    local best,bestDistance=nil,VEHICLE_RANGE*VEHICLE_RANGE
    local iterator=vehicles:iterator()
    local countVisited=0
    while iterator:hasNext() and countVisited<256 do
        countVisited=countVisited+1
        local candidate=radioInVehicle(player,iterator:next(),frequency,false)
        if candidate then
            local dist=sqDistance(player,candidate.x,candidate.y,candidate.z)
            if dist<bestDistance then best=candidate;bestDistance=dist end
        end
    end
    return best
end

local function radioSource(player,frequency)
    -- Never lose the occupied car because the cell's Set is rebuilding at a
    -- chunk boundary, or prefer a neighbouring workshop radio over this car.
    if player and player.getVehicle then
        local ok,car=pcall(function()return player:getVehicle()end)
        if ok and car then
            local own=radioInVehicle(player,car,frequency,true)
            if own then return own end
        end
    end
    local portable=radioInInventory(player,frequency)
    local world=radioInWorld(player,frequency)
    local vehicle=radioInVehicles(player,frequency)
    -- Prefer the nearest real 3D speaker when it is audible, but keep
    -- personally carried radios working with the original one-shot cues.
    local best=world
    if vehicle and (not best or
        sqDistance(player,vehicle.x,vehicle.y,vehicle.z)<
        sqDistance(player,best.x,best.y,best.z)) then best=vehicle end
    return best or portable
end

local function stopAudio()
    if not active then return end
    if active.emitter then
        pcall(function()active.emitter:stopSound(active.handle)end)
        if getWorld then
            pcall(function()getWorld():returnOwnershipOfEmitter(active.emitter)end)
        end
    elseif active.sound and getSoundManager then
        pcall(function()getSoundManager():StopSound(active.sound)end)
    end
    active=nil
end

local function startAudio(soundName,source,requestId,frequency)
    if not source then return false end
    stopAudio()
    if source.kind=="vehicle" then
        -- The registered short cue has its own 30-tile GameSound definition.
        soundName=soundName.."_Vehicle"
    end
    if source.kind=="portable" or source.kind=="global" then
        local sm=getSoundManager and getSoundManager()
        if not sm or not sm.PlaySound then return false end
        local ok,sound=pcall(function()
            return sm:PlaySound(soundName,false,math.min(.65,source.volume or .5))
        end)
        if not ok or not sound then return false end
        active={id=requestId,source=source,sound=sound,name=soundName,frequency=frequency or STATION_FREQ}
        return true
    end
    local world=getWorld and getWorld()
    if not world or not world.getFreeEmitter then return false end
    local ok,emitter=pcall(function()
        return world:getFreeEmitter(source.x,source.y,source.z)
    end)
    if not ok or not emitter then return false end
    local success,handle=pcall(function()
        world:takeOwnershipOfEmitter(emitter)
        emitter:setPos(source.x,source.y,source.z)
        local h=emitter:playSound(soundName)
        if not h or h==0 then error("Emitter returned empty audio handle") end
        emitter:setVolume(h,math.min(.70,source.volume))
        emitter:tick() -- ownership removes this emitter from IsoWorld auto-updates
        return h
    end)
    if not success then
        pcall(function()emitter:stopAll()end)
        pcall(function()world:returnOwnershipOfEmitter(emitter)end)
        log("ERROR positional speaker sound unavailable: "..tostring(handle))
        return false
    end
    active={id=requestId,source=source,emitter=emitter,handle=handle,name=soundName,frequency=frequency or STATION_FREQ}
    return true
end

-- FMOD streaming and native millisecond seek are performed only on
-- request by the explicitly approved CLIENT Java bridge (ZombieBuddy).
-- No silent audio channel, no background WAV decode, no arbitrary paths.
local bridgeWarned=false
local function hasBridge()
    if type(siegradioBridgeReady)~="function" then return false end
    local ok,ready=pcall(siegradioBridgeReady)
    return ok and ready==true
end

local function stopStationStream(reason)
    if stationPlayback then
        if type(siegradioBridgeStop)=="function" then pcall(siegradioBridgeStop) end
        log("STREAM STOP reason="..tostring(reason or "receiver_changed"))
        stationPlayback=nil
    end
end

local function stationCoordinates(player,source)
    local spatial=source.kind~="portable"
    if source.kind=="vehicle" then
        return spatial,source.object:getX(),source.object:getY(),source.object:getZ()
    end
    if spatial then return spatial,source.x,source.y,source.z end
    return false,player:getX(),player:getY(),player:getZ()
end

local function stationOffset(track,now)
    -- remainingMs is measured by the server when STATION_TRACK is sent.
    -- Client monotonically advances the same timeline after receipt.
    return math.max(0,math.min(track.durationMs-1,
        math.floor(track.durationMs-math.max(0,track.endsAt-now))))
end

local function syncCabin(stream,player,source)
    local inside=source.kind=="vehicle" and player.getVehicle
        and player:getVehicle()==source.object or false
    if stream.cabin==inside then return end
    stream.cabin=inside -- one attempt per transition, no per-frame retry on unsupported API
    if type(siegradioBridgeSetCabin)=="function" then
        local ok,applied=pcall(siegradioBridgeSetCabin,inside)
        if not ok or applied~=true then log("WARN cabin width unavailable; ordinary 3D retained") end
    end
end

local function startStationStream(track,player,source,now)
    if not hasBridge() then
        if not bridgeWarned then
            log("ERROR approved client Java SiegerRadioBridge missing/incompatible; no silent fallback")
            bridgeWarned=true
        end
        track.failed=true -- Java mod can only be loaded on game restart.
        return false
    end
    local is3d,x,y,z=stationCoordinates(player,source)
    local gain=math.min(.65,source.volume or 0)
    local offset=stationOffset(track,now)
    local ok,started=pcall(siegradioBridgePlay,
        track.clipId,offset,is3d,x,y,z,gain,source.kind=="vehicle")
    if not ok or started~=true then
        log("ERROR client native PCM streaming/seek refused; inspect bridge status")
        track.failed=true -- one terminal native failure, not a per-tick retry loop
        return false
    end
    stationPlayback={id=track.id,clipId=track.clipId,source=source,spatial=is3d,cabin=false}
    if source.kind=="vehicle" then syncCabin(stationPlayback,player,source) end
    log("STREAM START receiver="..source.kind.." clip="..track.clipId..
        " offset_ms="..tostring(offset))
    if type(siegradioBridgeDetails)=="function" then
        local success,value=pcall(siegradioBridgeDetails)
        if success then log("SPATIAL "..tostring(value)) end
    end
    return true
end

local function routeStationStream(track,player,source,now)
    if track.failed then stopStationStream();return false end
    if not source then stopStationStream();return true end
    local stream=stationPlayback
    local is3d,x,y,z=stationCoordinates(player,source)
    if not stream or stream.id~=track.id or stream.spatial~=is3d then
        stopStationStream()
        return startStationStream(track,player,source,now)
    end
    local gain=math.min(.65,source.volume or 0)
    local ok,updated=pcall(siegradioBridgeUpdate,
                          track.clipId,is3d,x,y,z,gain,source.kind=="vehicle")
    if not ok or updated~=true then
        stopStationStream()
        log("ERROR FMOD source update refused; no ambiguous native replay")
        track.failed=true -- one failed native update, manual review
        return false
    end
    syncCabin(stream,player,source)
    stream.source=source
    return true
end

local function markOnce(id)
    if played[id] then return false end
    played[id]=true
    playedOrder[#playedOrder+1]=id
    if #playedOrder>32 then
        local oldest=table.remove(playedOrder,1)
        played[oldest]=nil
    end
    return true
end

-- Move the EXISTING 3D emitter every game tick. The expensive receiver census
-- remains throttled; its 30-frame interval must not also freeze a moving car's
-- FMOD position behind the listener. No stream reopen or seek on movement.
local function updateMovingStation()
    local stream=stationPlayback
    if not stream or stream.source.kind~="vehicle" then return end
    local player=playerLocal()
    if not player then stopStationStream("no_player");return end
    local ok,source=pcall(function()
        local current=stream.source
        local car,part=current.object,current.part
        if not car or not part or not part.getDeviceData or not part.hasDevicePower then return nil end
        local seated=player.getVehicle and player:getVehicle()==car
        local x,y,z=car:getX(),car:getY(),car:getZ()
        if not seated and sqDistance(player,x,y,z)>=VEHICLE_RANGE*VEHICLE_RANGE then return nil end
        local volume=inspectedDevice(part:getDeviceData(),
            station and station.freq or STATION_FREQ,"vehicle")
        if not volume or part:hasDevicePower()~=true then return nil end
        current.x=x;current.y=y;current.z=z;current.volume=volume
        return current
    end)
    if not ok or not source then stopStationStream("vehicle_reception_lost");return end
    local spatial,x,y,z=stationCoordinates(player,source)
    local success,updated=pcall(siegradioBridgeUpdate,stream.clipId,spatial,x,y,z,
        math.min(.65,source.volume or 0),true)
    if not success or updated~=true then
        stopStationStream("native_update_failed")
        if station then station.failed=true end
        return
    end
    syncCabin(stream,player,source)
    stream.source=source
end

local function receive(module,command,args)
    if module~=MODULE or type(args)~="table" then return end
    if command=="HELLO_ACK" and args.version==VERSION and args.build==CLIENT_BUILD then
        acked=true
        return
    end
    if command=="STATION_STOP" and args.version==VERSION then
        station=nil
        stopStationStream("track_end")
        stopAudio()
        return
    end
    if (command~="CUE" and command~="STATION_TRACK")
        or args.version~=VERSION then return end
    if type(args.requestId)~="string" or #args.requestId~=32
        or not args.requestId:match("^[0-9a-f]+$") then return end
    local clip=SOUNDS[args.clip]
    if not clip then return end
    local freq=tonumber(args.frequency)
    if not freq or freq<88000 or freq>108000 or freq%100~=0 then return end
    if command=="STATION_TRACK" then
        if args.scope~="tuned" or freq~=STATION_FREQ then return end
        if type(args.durationMs)~="number"
            or args.durationMs<5000 or args.durationMs>720000 then return end
        if type(args.remainingMs)~="number" or args.remainingMs<=0
            or args.remainingMs>args.durationMs then return end
        if station and station.id==args.requestId then return end
        if played[args.requestId] then return end
        -- A delayed packet from a previous song must never take us back.
        if station and station.id:sub(1,16)==args.requestId:sub(1,16)
            and args.requestId<station.id then return end
        stopStationStream()
        if active then stopAudio() end
        local now=getTimestampMs and getTimestampMs() or tickCount*16
        station={id=args.requestId,clipId=args.clip,freq=freq,
                 durationMs=args.durationMs,
                 endsAt=now+args.remainingMs,failed=false}
        markOnce(args.requestId)
        -- No sound is created until a live, powered, tuned radio is in range.
        -- Late join/reentry seeks the CURRENT on-air time, not track start.
        return
    end
    if args.scope~="tuned" and args.scope~="global" then return end
    local p=playerLocal()
    if not p then return end
    local source=args.scope=="global" and {kind="global",volume=.50}
        or radioSource(p,freq)
    if not source then
        log("CUE no powered tuned receiver frequency="..tostring(freq))
        return
    end
    if type(args.durationMs)~="number" or args.durationMs>60000
        or args.durationMs<=0 or args.clip:match("^north_track_") then return end
    if played[args.requestId] then return end
    log("CUE receiver="..source.kind.." frequency="..tostring(freq))
    stopStationStream("cue_priority") -- narration takes priority immediately
    if startAudio(clip,source,args.requestId,freq) then
        if type(args.durationMs)=="number" and args.durationMs>0
            and args.durationMs<=720000 then
            local now=getTimestampMs and getTimestampMs() or tickCount*16
            active.expiresAt=now+args.durationMs
        end
        markOnce(args.requestId)
    else log("ERROR audio clip not registered/started: "..tostring(args.clip)) end
end

local function tick()
    tickCount=tickCount+1
    local now=getTimestampMs and getTimestampMs() or tickCount*16
    -- Keep existing short narrated CUEs independent from the music bridge.
    if active and active.emitter then
        local ok,err=pcall(function()
            if active.source.kind=="vehicle" then
                local car=active.source.object
                active.emitter:setPos(car:getX(),car:getY(),car:getZ())
            end
            active.emitter:tick()
        end)
        if not ok then
            log("ERROR one-shot CUE emitter: "..tostring(err))
            stopAudio()
        end
    end
    if tickCount%120==0 then sendHello() end
    if station and now>=station.endsAt then
        station=nil
        stopStationStream("track_end")
    end
    if active and active.expiresAt and now>=active.expiresAt then stopAudio() end
    updateMovingStation()
    -- Inactive radios: search once per ~second, not every frame.
    -- Active receiver: check twice per second for power/retune/range.
    local interval=(stationPlayback or active) and 30 or 60
    if tickCount%interval~=0 then return end
    local player=playerLocal()
    if not player then stopStationStream();stopAudio();return end
    if station then
        if active or station.failed then
            stopStationStream() -- Narration takes priority over the station.
        else
            routeStationStream(station,player,radioSource(player,station.freq),now)
        end
    end
    if active and active.source.kind~="global" then
        local source=radioSource(player,active.frequency or STATION_FREQ)
        if not source or source.object~=active.source.object
            or source.kind~=active.source.kind then stopAudio() end
    end
end

if Events then
    if Events.OnGameStart then Events.OnGameStart.Add(function()
        log("BUILD "..CLIENT_BUILD)
        sendHello()
    end) end
    if Events.OnTick then Events.OnTick.Add(tick) end
    if Events.OnServerCommand then Events.OnServerCommand.Add(receive) end
    if Events.OnGameExit then Events.OnGameExit.Add(stopStationStream) end
end
