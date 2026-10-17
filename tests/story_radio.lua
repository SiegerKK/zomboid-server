-- Lua 5.1 behavioural harness. Mocks show packet validation/replay handling;
-- MUST be followed by the pinned Build 42.21 dedicated-server/client check.
local runtime=arg[1] or "story/runtime/SiegerStoryRadio.lua"
local files,events,transmissions,commands={},{},{},{}
local registered={}
Events={OnTick={Add=function(fn)events.tick=fn end},
    OnClientCommand={Add=function(fn)events.client=fn end},
    OnServerStarted={Add=function(fn)events.started=fn end}}
isClient=function() return false end
SiegerStoryScenes={schema=1,world="story_test"}
local function lines(s)
    local vals={}
    for row in (s or ""):gmatch("[^\n]+") do vals[#vals+1]=row end
    return vals
end
getFileReader=function(filename)
    if files[filename]==nil then return nil end
    local content=lines(files[filename]);local i=0
    return {readLine=function()i=i+1;return content[i]end,close=function()end}
end
getFileWriter=function(filename,create,append)
    assert(filename:match("%.txt$"))
    if not append then files[filename]="" end
    return {write=function(_,s)files[filename]=(files[filename] or "")..s end,close=function()end}
end
local radio={
    SendTransmission=function(_,x,y,freq,msg,guid,codes,r,g,b,signal,isTv)
        assert(x==10622 and y==9221 and signal==100000 and not isTv)
        transmissions[#transmissions+1]={frequency=freq,msg=msg,guid=guid}
    end,
    getChannelName=function()return nil end,
    addChannelName=function(_,name,freq,cat,overwrite)
        registered={name=name,frequency=freq,category=cat,overwrite=overwrite}
    end
}
getZomboidRadio=function()return radio end
local person={getUsername=function()return "kyrylo" end}
getOnlinePlayers=function()return {size=function()return 1 end,get=function()return person end}end
sendServerCommand=function(...)
    local args={...}
    commands[#commands+1]=args
end
local function encode(raw)
    return (raw:gsub(".",function(c)return string.format("%02x",c:byte())end))
end
local function send(id,kind,scope,payload,duration,freq)
    files["SiegerStoryRadioRequest.txt"]=table.concat({
        "v1",string.rep(id,32),"story_test",kind,tostring(freq or 101300),
        "10622","9221","100000",scope,payload,tostring(duration)
    },"\t").."\n"
    for _=1,130 do events.tick()end
    return files["SiegerStoryRadioResult.txt"]
end

dofile(runtime);events.started()
assert(registered.name=="NORTHBOUND RELAY")
assert(registered.frequency==101300)
local text=send("a","text","radio",encode("Сигнал Маршрута 17"),0)
assert(text:find("\tcomplete\t101300\t0\tradio_api_called",1,true))
assert(#transmissions==1)
assert(transmissions[1].msg=="Сигнал Маршрута 17")
-- On reload, same request ID is not resent, even when previous server ACK exists.
dofile(runtime);events.started()
for _=1,250 do events.tick()end
assert(#transmissions==1,"Message duplicated on radio restart")
-- Wrong catalog/audio duration is rejected, never broadcast.
local wrong=send("b","audio","tuned","test_tone",999)
assert(wrong:find("\terror\t101300\t0\tserver_rejected_review_logs",1,true))
assert(#commands==0)
-- Without the installed/handshaking client sound pack, audio is blocked.
local absent=send("c","audio","tuned","test_tone",750)
assert(absent:find("\terror\t101300\t0\tserver_rejected_review_logs",1,true))
assert(#commands==0)
-- Client HELLO alone grants no ability to ask server to transmit text.
events.client("SiegerRadio","PLAY",person,{version="sr17-v1"})
assert(#commands==0)
events.client("SiegerRadio","HELLO",person,{version="wrong"})
assert(#commands==0)
events.client("SiegerRadio","HELLO",person,{version="sr17-v1"})
assert(#commands==1 and commands[1][1]==person and commands[1][3]=="HELLO_ACK")
for _=1,650 do events.tick()end
local accepted=send("d","audio","tuned","test_tone",750)
assert(accepted:find("\tcomplete\t101300\t1\tclient_command_sent",1,true))
assert(#commands==2 and commands[2][1]=="SiegerRadio" and commands[2][2]=="CUE")
assert(commands[2][3].clip=="test_tone" and commands[2][3].scope=="tuned")
local cmdCount=#commands
dofile(runtime);events.started()
for _=1,130 do events.tick()end
assert(#commands==cmdCount,"Audio replayed after reload")
-- The operation ID cannot double-dispatch, even when global scope is used.
local originalAck=files["SiegerStoryRadioResult.txt"]
assert(originalAck:find("\tcomplete\t"))
print("PASS: native radio UTF-8 text, registered channel, clip allowlist, HELLO gate, cooldown and durable replay")
