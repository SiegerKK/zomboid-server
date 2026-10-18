-- SiegerRadio server: bounded, root-issued radio texts and registered audio cues.
-- Only story_test. No client-originated transmit commands. No arbitrary URLs,
-- audio uploads, Lua eval, global sound spamming or periodic world scans.
if isClient and isClient() then return end

local REQUEST = "SiegerStoryRadioRequest.txt"
local RESPONSE = "SiegerStoryRadioResult.txt"
local GUARD = "SiegerStoryRadioGuard.txt"
local VERSION="sr17-v1-023e01823321"
local CLIENT_BUILD="radio-ops13"
local POLL_MS = 100
local COOLDOWN_MS = 3000
local lastPollMs = nil
local processed = nil
local ackLoaded = false
local ready = {}  -- exact current connected IsoPlayer object keys
local CLIPS = {
    -- BEGIN RADIO CATALOG
    north_track_01={sound="SiegerRadio_NorthTrack01",duration=176588},
    north_track_02={sound="SiegerRadio_NorthTrack02",duration=263001},
    north_track_03={sound="SiegerRadio_NorthTrack03",duration=257579},
    north_track_04={sound="SiegerRadio_NorthTrack04",duration=297471},
    north_track_05={sound="SiegerRadio_NorthTrack05",duration=293883},
    north_track_06={sound="SiegerRadio_NorthTrack06",duration=252865},
    north_track_07={sound="SiegerRadio_NorthTrack07",duration=242347},
    north_track_08={sound="SiegerRadio_NorthTrack08",duration=210001},
    north_track_09={sound="SiegerRadio_NorthTrack09",duration=281472},
    north_track_10={sound="SiegerRadio_NorthTrack10",duration=329584},
    north_track_11={sound="SiegerRadio_NorthTrack11",duration=215620},
    north_track_12={sound="SiegerRadio_NorthTrack12",duration=302811},
    north_track_13={sound="SiegerRadio_NorthTrack13",duration=175264},
    north_track_14={sound="SiegerRadio_NorthTrack14",duration=237401},
    north_track_15={sound="SiegerRadio_NorthTrack15",duration=145181},
    north_track_16={sound="SiegerRadio_NorthTrack16",duration=311310},
    north_track_17={sound="SiegerRadio_NorthTrack17",duration=230737},
    north_track_18={sound="SiegerRadio_NorthTrack18",duration=243043},
    north_track_19={sound="SiegerRadio_NorthTrack19",duration=198298},
    north_track_20={sound="SiegerRadio_NorthTrack20",duration=245806},
    north_track_21={sound="SiegerRadio_NorthTrack21",duration=324360},
    north_track_22={sound="SiegerRadio_NorthTrack22",duration=167194},
    north_track_23={sound="SiegerRadio_NorthTrack23",duration=200027},
    north_track_24={sound="SiegerRadio_NorthTrack24",duration=252053},
    north_track_25={sound="SiegerRadio_NorthTrack25",duration=218151},
    north_track_26={sound="SiegerRadio_NorthTrack26",duration=224444},
    north_track_27={sound="SiegerRadio_NorthTrack27",duration=195466},
    north_track_28={sound="SiegerRadio_NorthTrack28",duration=203928},
    north_track_29={sound="SiegerRadio_NorthTrack29",duration=214576},
    north_track_30={sound="SiegerRadio_NorthTrack30",duration=198925},
    north_track_31={sound="SiegerRadio_NorthTrack31",duration=219730},
    north_track_32={sound="SiegerRadio_NorthTrack32",duration=208678},
    north_track_33={sound="SiegerRadio_NorthTrack33",duration=253933},
    north_track_34={sound="SiegerRadio_NorthTrack34",duration=158453},
    north_track_35={sound="SiegerRadio_NorthTrack35",duration=173881},
    north_track_36={sound="SiegerRadio_NorthTrack36",duration=273810},
    north_track_37={sound="SiegerRadio_NorthTrack37",duration=187199},
    north_track_38={sound="SiegerRadio_NorthTrack38",duration=252796},
    north_track_39={sound="SiegerRadio_NorthTrack39",duration=219196},
    north_track_40={sound="SiegerRadio_NorthTrack40",duration=252192},
    north_track_41={sound="SiegerRadio_NorthTrack41",duration=232014},
    test_tone={sound="SiegerRadio_TestTone",duration=750},
    -- END RADIO CATALOG
}
local CHANNEL_NAME = "NORTHBOUND RELAY"
local CHANNEL_FREQUENCY = 101200
local MAX_BYTES = 2500
local lastSentMs = nil

local function log(msg)
    print("SIEGER_RADIO "..tostring(msg))
end

local function fields(line)
    local out, start = {}, 1
    while true do
        local index=string.find(line,"\t",start,true)
        if not index then out[#out+1]=line:sub(start);return out end
        out[#out+1]=line:sub(start,index-1)
        start=index+1
    end
end

local function identifier(value)
    return type(value)=="string" and #value==32
        and value:match("^[0-9a-f]+$")~=nil
end

local function integer(raw, minimum, maximum)
    if not raw or not raw:match("^%d+$") then error("Invalid integer") end
    local val=tonumber(raw)
    if not val or val<minimum or val>maximum or val~=math.floor(val) then
        error("Integer out of range")
    end
    return val
end

-- Lua 5.1 byte strings and the Build 42 Kahlua UTF-16 runtime both
-- supported, including Cyrillic and non-BMP Unicode characters.
local wideStrings=pcall(string.char,256)
local function unhex(data, limit)
    if type(data)~="string" or #data==0 or #data%2~=0 or #data>limit*2
        or not data:match("^[0-9a-f]+$") then
        error("Invalid UTF-8 hex text")
    end
    local bytes={}
    for i=1,#data,2 do bytes[#bytes+1]=tonumber(data:sub(i,i+1),16) end
    local result,idx={},1
    while idx<=#bytes do
        local first=bytes[idx]
        local length,cp,min=1,first,0
        if first>=194 and first<=223 then length=2;cp=first-192;min=128
        elseif first>=224 and first<=239 then length=3;cp=first-224;min=2048
        elseif first>=240 and first<=244 then length=4;cp=first-240;min=65536
        elseif first>=128 then error("Invalid UTF-8 lead byte") end
        for j=1,length-1 do
            local nextByte=bytes[idx+j]
            if not nextByte or nextByte<128 or nextByte>191 then
                error("Invalid UTF-8 continuation byte")
            end
            cp=cp*64+nextByte-128
        end
        if cp<min or cp>1114111 or (cp>=55296 and cp<=57343) then
            error("Invalid Unicode scalar")
        end
        if wideStrings then
            if cp>65535 then
                cp=cp-65536
                result[#result+1]=string.char(55296+math.floor(cp/1024),56320+cp%1024)
            else result[#result+1]=string.char(cp) end
        else
            for j=0,length-1 do result[#result+1]=string.char(bytes[idx+j]) end
        end
        idx=idx+length
    end
    return table.concat(result)
end

local function writeResult(req,status,clients,reason)
    local writer=getFileWriter(RESPONSE,true,false)
    if not writer then error("Cannot open radio response") end
    local ok,err=pcall(function()
        writer:write(table.concat({"v1",req.id,"story_test",req.kind,status,
            tostring(req.frequency),tostring(clients),reason},"\t").."\n")
    end)
    writer:close()
    if not ok then error(err) end
end

local function loadLastResult()
    if ackLoaded then return end
    local reader=getFileReader(RESPONSE,false)
    if reader then
        local line=reader:readLine()
        reader:close()
        if line then
            local cells=fields(line)
            if cells[1]=="v1" and identifier(cells[2]) then processed=cells[2] end
        end
    end
    ackLoaded=true
end

local function readRequest()
    local reader=getFileReader(REQUEST,false)
    if not reader then return nil end
    local raw=reader:readLine()
    local extra=reader:readLine()
    reader:close()
    if not raw or #raw>MAX_BYTES or extra then return nil end
    local f=fields(raw)
    if #f~=11 or f[1]~="v1" or not identifier(f[2])
        or f[3]~="story_test" or (f[4]~="text" and f[4]~="audio") then
        return nil
    end
    if f[2]==processed then return nil end -- terminal invalid packets are not reparsed/logged every poll
    local packet={id=f[2],kind=f[4]}
    packet.frequency=integer(f[5],88000,108000)
    if packet.frequency%100~=0 then error("Radio channel must use 100 kHz steps") end
    packet.x=integer(f[6],0,40000)
    packet.y=integer(f[7],0,40000)
    packet.signal=integer(f[8],100,500000)
    packet.scope=f[9]
    if packet.kind=="text" then
        if packet.scope~="radio" or f[11]~="0" then error("Invalid text scope") end
        packet.message=unhex(f[10],480)
        if packet.message:find("[\r\n\t]") then error("Invalid text controls") end
    else
        if packet.scope~="tuned" and packet.scope~="global" then
            error("Invalid audio scope")
        end
        local clip=CLIPS[f[10]]
        if not clip or clip.duration>60000 or f[10]:match("^north_track_")
            or integer(f[11],100,60000)~=clip.duration then
            error("Unregistered or incorrect audio duration")
        end
        packet.clip=f[10]
        packet.duration=clip.duration
    end
    return packet
end

local function priorAttempt(id)
    local reader=getFileReader(GUARD,false)
    if not reader then return false end
    local last=reader:readLine()
    reader:close()
    return last==id
end

local function markAttempt(req)
    -- Written BEFORE dispatch; uncertain/crashed sends will never be retried.
    local writer=getFileWriter(GUARD,true,false)
    if not writer then error("Persistent radio attempt guard unavailable") end
    writer:write(req.id.."\n")
    writer:close()
end

local function radioEngine()
    if not getZomboidRadio then error("getZomboidRadio global unavailable") end
    local radio=getZomboidRadio()
    if not radio or not radio.SendTransmission then
        error("Radio engine transmission API unavailable")
    end
    return radio
end

local function registerChannel()
    local radio=radioEngine()
    if radio.getChannelName and radio.addChannelName then
        local name=radio:getChannelName(CHANNEL_FREQUENCY)
        if not name or tostring(name)=="" then
            radio:addChannelName(CHANNEL_NAME,CHANNEL_FREQUENCY,"Amateur",false)
        elseif tostring(name)~=CHANNEL_NAME then
            log("WARN frequency 101.2 already owned by "..tostring(name))
        end
    end
end

local function audioClientCount()
    if not sendServerCommand then error("Audio client command API unavailable") end
    local players=getOnlinePlayers and getOnlinePlayers()
    if not players then error("Connected player list unavailable") end
    if players:size()>32 then error("Audio client count exceeds safety cap") end
    if players:size()==0 then error("No clients online for audio dispatch") end
    for i=0,players:size()-1 do
        local player=players:get(i)
        if not player or ready[player]~=VERSION then
            error("One or more clients have not acknowledged SiegerRadio client pack")
        end
    end
    return players:size()
end

local function dispatch(req, nowMs)
    if not SiegerStoryScenes or SiegerStoryScenes.world~="story_test" then
        error("Story radio allowed only in the story_test world")
    end
    if lastSentMs and nowMs-lastSentMs < COOLDOWN_MS then
        error("Radio cooldown: at least 3000 milliseconds between dispatches")
    end
    if priorAttempt(req.id) then
        error("Previous transmission attempt uncertain; no replay")
    end
    if req.kind=="text" then
        local radio=radioEngine() -- check before irreversible guard
        markAttempt(req)
        radio:SendTransmission(req.x,req.y,req.frequency,req.message,
            "SiegerRadio","",0.93,0.86,0.65,req.signal,false)
        lastSentMs=nowMs
        return 0,"radio_api_called"
    end
    local count=audioClientCount()
    markAttempt(req)
    -- No file bytes cross the wire. All receivers must have this sound
    -- in the client pack. Dispatch ACK != proof that playback was heard.
    sendServerCommand("SiegerRadio","CUE",{
        requestId=req.id,clip=req.clip,frequency=req.frequency,
        scope=req.scope,version=VERSION,durationMs=req.duration})
    lastSentMs=nowMs
    return count,"client_command_sent"
end

local function poll(nowMs)
    loadLastResult()
    local ok,req=pcall(readRequest)
    if not ok then
        log("ERROR request rejected: "..tostring(req))
        -- A well-framed but invalid request returns a terminal error instead
        -- of leaving the root control CLI waiting forever.
        local reader=getFileReader(REQUEST,false)
        if reader then
            local line=reader:readLine()
            reader:close()
            if line and #line<=MAX_BYTES then
                local a=fields(line)
                if #a==11 and a[1]=="v1" and identifier(a[2])
                    and a[3]=="story_test" and (a[4]=="text" or a[4]=="audio")
                    and a[2]~=processed then
                    processed=a[2]
                    local failed={id=a[2],kind=a[4],frequency=tonumber(a[5]) or 0}
                    local written,err=pcall(writeResult,failed,"error",0,"invalid_request")
                    if not written then log("ERROR invalid request ACK: "..tostring(err)) end
                end
            end
        end
        return
    end
    if not req or req.id==processed then return end
    -- Keep an early request pending; never mark or reject it before its slot.
    if lastSentMs and nowMs-lastSentMs < COOLDOWN_MS then return end
    processed=req.id
    local success,clients,reason=pcall(dispatch,req,nowMs)
    if not success then
        log("ERROR "..req.kind.." id="..req.id..": "..tostring(clients))
        clients,reason=0,"server_rejected_review_logs"
    end
    local okWrite,err=pcall(writeResult,req,success and "complete" or "error",clients,reason)
    if not okWrite then log("ERROR saving ACK: "..tostring(err)) end
end

local function onClientCommand(module,command,player,args)
    if module~="SiegerRadio" or command~="HELLO" then return end
    if player and args and type(args)=="table"
        and args.version==VERSION and args.build==CLIENT_BUILD then
        ready[player]=VERSION
        if sendServerCommand then
            sendServerCommand(player,"SiegerRadio","HELLO_ACK",{version=VERSION,build=CLIENT_BUILD})
        end
    end
end

local function tick()
    -- B42.21 getTimestampMs is System.currentTimeMillis(), not game time/FPS.
    local nowMs=getTimestampMs()
    if lastPollMs and nowMs>=lastPollMs and nowMs-lastPollMs<POLL_MS then return end
    lastPollMs=nowMs
    local ok,err=pcall(poll,nowMs)
    if not ok then log("ERROR radio poll: "..tostring(err)) end
end

if Events then
    if Events.OnTick then Events.OnTick.Add(tick) end
    if Events.OnClientCommand then Events.OnClientCommand.Add(onClientCommand) end
    if Events.OnServerStarted then
        Events.OnServerStarted.Add(function()
            local ok,err=pcall(registerChannel)
            if not ok then log("WARN station name not registered: "..tostring(err)) end
        end)
    end
end
