-- Minimal, opt-in client bridge for server-commanded Route 17 audio.
-- Receives registered cues through portable, installed IsoRadio furniture
-- and powered vehicle radio parts, without world-wide sound leakage.
-- Nearby speakers use a 3D emitter. Audio is client-local, server sequenced.
if isServer and isServer() then return end

local VERSION="sr17-v1-3029217cad73"
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
local STATION_FREQ=101300
local RANGE=12
local lastSourceScan=0
local active=nil
local station=nil
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
    local p=playerLocal()
    if not p then return end
    helloTries=helloTries+1
    sendClientCommand(p,MODULE,"HELLO",{version=VERSION})
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
    local visited=0
    for z=math.max(0,pz-1),pz+1 do
        for x=px-RANGE,px+RANGE do
            for y=py-RANGE,py+RANGE do
                if sqDistance(player,x+0.5,y+0.5,z)<bestDistance then
                    visited=visited+1
                    if visited>1200 then return best end
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

local function radioInVehicles(player,frequency)
    if not getCell then return nil end
    local cell=getCell()
    if not cell or not cell.getVehicles then return nil end
    local vehicles=cell:getVehicles()
    if not vehicles or vehicles:size()>256 then return nil end
    local best,bestDistance=nil,RANGE*RANGE
    for i=0,vehicles:size()-1 do
        local car=vehicles:get(i)
        if car and car.getX and car.getPartCount then
            local x,y,z=car:getX(),car:getY(),car:getZ()
            local distance=sqDistance(player,x,y,z)
            if distance<bestDistance then
                local count=car:getPartCount()
                if type(count)=="number" and count>=0 and count<=128 then
                    for j=0,count-1 do
                        local part=car:getPartByIndex(j)
                        if part and part.getDeviceData then
                            local ok,d=pcall(function()return part:getDeviceData()end)
                            local vol=ok and inspectedDevice(d,frequency,"vehicle")
                            local power=part.hasDevicePower and part:hasDevicePower()
                            if vol and power==true then
                                best={kind="vehicle",object=car,volume=vol,x=x,y=y,z=z}
                                bestDistance=distance
                                break
                            end
                        end
                    end
                end
            end
        end
    end
    return best
end

local function radioSource(player,frequency)
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
        return h
    end)
    if not success then
        pcall(function()world:returnOwnershipOfEmitter(emitter)end)
        log("ERROR positional speaker sound unavailable: "..tostring(handle))
        return false
    end
    active={id=requestId,source=source,emitter=emitter,handle=handle,name=soundName,frequency=STATION_FREQ}
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

local function receive(module,command,args)
    if module~=MODULE or type(args)~="table" then return end
    if command=="HELLO_ACK" and args.version==VERSION then
        acked=true
        return
    end
    if command=="STATION_STOP" and args.version==VERSION then
        station=nil
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
        -- Do not start a song mid-way on late join / late tuning without
        -- sample-accurate FMOD seek; wait for the next globally timed song.
        station={id=args.requestId,clip=clip,freq=freq,created=0,
                 timeLeft=args.durationMs,ready=false}
        if type(args.remainingMs)=="number"
            and args.remainingMs<args.durationMs-1500 then
            station.ready=false
        else station.ready=true end
        if active then stopAudio() end
        return
    end
    if args.scope~="tuned" and args.scope~="global" then return end
    local p=playerLocal()
    if not p then return end
    local source=args.scope=="global" and {kind="global",volume=.50}
        or radioSource(p,freq)
    if not source then return end
    if played[args.requestId] then return end
    if startAudio(clip,source,args.requestId,freq) then
        markOnce(args.requestId)
    else log("ERROR audio clip not registered/started: "..tostring(args.clip)) end
end

local function tick()
    tickCount=tickCount+1
    if tickCount%120==0 then sendHello() end
    if tickCount%30~=0 then return end -- bounded periodic receiver state
    local player=playerLocal()
    if not player then stopAudio();return end
    if station then
        local now=getTimestampMs and getTimestampMs() or tickCount*16
        if station.created==0 then station.created=now end
        if now-station.created>=station.timeLeft then
            station=nil
            stopAudio()
            return
        end
        if station.ready then
            -- Sound seeking is not in this MVP: only begin within the first
            -- ~2 seconds of a server-announced song; late tuning waits for next.
            if now-station.created>2000 and not active then station.ready=false end
            local source=radioSource(player,station.freq)
            if active and (not source or active.source.object~=source.object
                or active.source.kind~=source.kind) then stopAudio() end
            if not active and source and not played[station.id] then
                if startAudio(station.clip,source,station.id,station.freq) then
                    markOnce(station.id)
                end
            end
        end
    elseif active and active.source.kind~="global" then
        local source=radioSource(player,active.frequency or STATION_FREQ)
        if not source or source.object~=active.source.object then stopAudio() end
    end
    if active and active.source.kind=="vehicle" then
        local car=active.source.object
        if car and active.emitter then
            pcall(function()active.emitter:setPos(car:getX(),car:getY(),car:getZ())end)
        end
    end
end

if Events then
    if Events.OnGameStart then Events.OnGameStart.Add(sendHello) end
    if Events.OnTick then Events.OnTick.Add(tick) end
    if Events.OnServerCommand then Events.OnServerCommand.Add(receive) end
end
