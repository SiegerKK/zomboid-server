-- Minimal, opt-in client bridge for server-commanded Route 17 audio.
-- MVP: tuned mode checks only radios in the LOCAL player's top-level inventory
-- (including held radios); NOT world speakers, car radios or remote backpack contents.
-- Global mode deliberately bypasses tuning and needs root opt-in on the server.
if isServer and isServer() then return end

local VERSION="sr17-v1"
local MODULE="SiegerRadio"
local SOUNDS={
    -- BEGIN RADIO CATALOG
    test_tone="SiegerRadio_TestTone",
    -- END RADIO CATALOG
}
local tickCount=0
local acked=false
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

local function deviceTuned(device,frequency)
    if not device then return false end
    local ok,result=pcall(function()
        return device:getIsTurnedOn()==true
            and device:getChannel()==frequency
            and device:getPower()>0
            and device:getDeviceVolume()>0
            and device:getIsTelevision()~=true
    end)
    return ok and result==true
end

local function hasTunedRadio(player,frequency)
    if not player or not player.getInventory then return false end
    local inventory=player:getInventory()
    if not inventory then return false end
    local entries=inventory:getItems()
    if not entries then return false end
    if entries:size()>512 then return false end -- bounded client-side scan
    for i=0,entries:size()-1 do
        local item=entries:get(i)
        if item and item.getDeviceData then
            local ok,device=pcall(function()return item:getDeviceData()end)
            if ok and deviceTuned(device,frequency) then return true end
        end
    end
    -- A held device in a nested container is not considered in this MVP.
    for _,item in ipairs({player:getPrimaryHandItem(),player:getSecondaryHandItem()}) do
        if item and item.getDeviceData then
            local ok,device=pcall(function()return item:getDeviceData()end)
            if ok and deviceTuned(device,frequency) then return true end
        end
    end
    return false
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
    if command~="CUE" or args.version~=VERSION then return end
    if type(args.requestId)~="string" or #args.requestId~=32
        or not args.requestId:match("^[0-9a-f]+$") then return end
    local clip=SOUNDS[args.clip]
    if not clip then return end -- never accept arbitrary sound names
    local freq=tonumber(args.frequency)
    if not freq or freq<88000 or freq>108000 or freq%100~=0 then return end
    if args.scope~="tuned" and args.scope~="global" then return end
    local p=playerLocal()
    if not p then return end
    if args.scope=="tuned" and not hasTunedRadio(p,freq) then return end
    if played[args.requestId] then return end
    local sm=getSoundManager and getSoundManager() or nil
    if not sm or not sm.PlaySound then
        log("ERROR sound manager unavailable")
        return
    end
    local ok,sound=pcall(function()return sm:PlaySound(clip,false,0.50)end)
    if not ok or not sound then
        log("ERROR audio clip not registered/started: "..tostring(args.clip))
        return
    end
    markOnce(args.requestId)
end

local function tick()
    tickCount=tickCount+1
    if tickCount%120==0 then sendHello() end
end

if Events then
    if Events.OnGameStart then Events.OnGameStart.Add(sendHello) end
    if Events.OnTick then Events.OnTick.Add(tick) end
    if Events.OnServerCommand then Events.OnServerCommand.Add(receive) end
end
