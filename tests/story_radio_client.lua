-- Client-side mock: frequency filter, audio allowlist, global/tuned semantics.
local runtime=arg[1] or "mods/SiegerRadio/42/media/lua/client/SiegerRadioClient.lua"
local events={};local calls,plays={},{}
Events={OnGameStart={Add=function(fn)events.start=fn end},
 OnTick={Add=function(fn)events.tick=fn end},
 OnServerCommand={Add=function(fn)events.server=fn end}}
isServer=function()return false end
local device={getIsTurnedOn=function()return true end,
 getChannel=function()return 101300 end,getPower=function()return 1 end,
 getDeviceVolume=function()return .8 end,getIsTelevision=function()return false end}
local portable={getDeviceData=function()return device end}
local entries={portable}
local held=portable
local inv={getItems=function()return {size=function()return #entries end,
 get=function(_,i)return entries[i+1]end}end}
local p={getInventory=function()return inv end,
 getPrimaryHandItem=function()return held end,
 getSecondaryHandItem=function()return nil end}
getSpecificPlayer=function(index)assert(index==0);return p end
sendClientCommand=function(...)
 calls[#calls+1]={...}
end
getSoundManager=function()return {PlaySound=function(_,name,loop,volume)
 plays[#plays+1]={name=name,loop=loop,volume=volume}
 return {ok=true}
end}end
local function msg(id,scope,frequency,clip)
 events.server("SiegerRadio","CUE",{requestId=string.rep(id,32),version="sr17-v1",
 clip=clip or "test_tone",frequency=frequency or 101300,scope=scope,durationMs=750})
end
dofile(runtime);events.start()
assert(#calls==1 and calls[1][2]=="SiegerRadio" and calls[1][3]=="HELLO")
events.server("SiegerRadio","HELLO_ACK",{version="sr17-v1"})
msg("a","tuned")
assert(#plays==1 and plays[1].name=="SiegerRadio_TestTone")
msg("a","tuned")
assert(#plays==1,"Replayed duplicate sound")
msg("b","tuned",101400)
assert(#plays==1,"Played sound on wrong frequency")
msg("c","tuned",101300,"dangerous_sound")
assert(#plays==1,"Played unregistered sound")
entries={}
held=nil
msg("d","tuned")
assert(#plays==1,"Played tuned sound without matching radio")
msg("e","global")
assert(#plays==2 and plays[2].name=="SiegerRadio_TestTone")
print("PASS: client handshake, radio frequency/power gate, no arbitrary sound, global audio opt-in")
