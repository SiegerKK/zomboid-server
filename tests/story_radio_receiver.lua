-- Standalone Lua 5.1 client mock for IsoRadio world furniture and vehicles.
local path=arg[1] or "mods/SiegerRadio/42/media/lua/client/SiegerRadioClient.lua"
local f=assert(io.open(path,"rb"));local script=f:read("*a");f:close()
local version=assert(script:match('local VERSION%s*=%s*"([^"]+)"'))
local events,played,stopped={},{},{}
Events={OnGameStart={Add=function(fn)events.started=fn end},
        OnServerCommand={Add=function(fn)events.server=fn end},
        OnTick={Add=function(fn)events.tick=fn end}}
isServer=function()return false end
sendClientCommand=function()end
local function list(a)return {size=function()return #a end,get=function(_,i)return a[i+1] end} end
local function device(isMains)
 local data={on=true,chan=101200,power=isMains and 0 or 1,volume=0.7,canPower=true}
 return {state=data,
 getIsTurnedOn=function()return data.on end,
 getChannel=function()return data.chan end,
 getPower=function()return data.power end,
 getDeviceVolume=function()return data.volume end,
 getIsTelevision=function()return false end,
 canBePoweredHere=function()return data.canPower end}
end
local mains=device(true)
local carRadio=device(false)
local furniture={class="IsoRadio",getDeviceData=function()return mains end}
instanceof=function(obj,kind)return obj and obj.class==kind end
local equipped={}
local inventory={getItems=function()return list(equipped)end}
local playerX=100.5
local player={getX=function()return playerX end,getY=function()return 100.5 end,
    getZ=function()return 0 end,getInventory=function()return inventory end,
    getPrimaryHandItem=function()return nil end,getSecondaryHandItem=function()return nil end}
getSpecificPlayer=function(i)assert(i==0);return player end
local powered=true
local carPart={getDeviceData=function()return carRadio end,
 hasDevicePower=function()return powered end}
local vehicle={getX=function()return 101.8 end,getY=function()return 100.5 end,
 getZ=function()return 0 end,getPartCount=function()return 1 end,
 getPartByIndex=function(_,i)assert(i==0);return carPart end}
local vehicles={}
local square={getObjects=function()return list({furniture})end}
getCell=function()
 return {getGridSquare=function(_,x,y,z)
   if x==101 and y==100 and z==0 then return square end
   return nil end,
 getVehicles=function()return {
 size=function()return #vehicles end,
 iterator=function()
  local index=0
  return {hasNext=function()return index<#vehicles end,
   next=function()index=index+1;return vehicles[index]end}
 end}end}
end
local emitterTicks=0
local gain,last3d=0,true
local emitter={setPos=function()end,
 set3D=function(_,handle,is3d)assert(handle==15);last3d=is3d end,
 tick=function()emitterTicks=emitterTicks+1 end,
 stopAll=function()end,
 playSound=function(_,name)played[#played+1]={name=name,kind="positional"};return 15 end,
 setVolume=function(_,handle,vol)assert(handle==15 and vol>=0 and vol<=1);gain=vol end,
 stopSound=function(_,handle)assert(handle==15);stopped[#stopped+1]="positional" end}
local world={
 getFreeEmitter=function(_,x,y,z)assert(x and y and z);return emitter end,
 takeOwnershipOfEmitter=function()end,
 returnOwnershipOfEmitter=function()end}
getWorld=function()return world end
getSoundManager=function()return {PlaySound=function(_,name)played[#played+1]={name=name,kind="global"};return {ok=true}end}end
local now=123456
getTimestampMs=function()return now end
local function tick(times)
 for _=1,(times or 30) do now=now+16;events.tick()end
end
local function cue(key,scope,freq)
 events.server("SiegerRadio","CUE",{
 version=version,requestId=string.rep(key,32),
 clip="test_tone",frequency=freq or 101200,scope=scope,durationMs=750})
end
dofile(path)
events.started()
events.server("SiegerRadio","HELLO_ACK",{version=version})
cue("a","tuned")
assert(#played==1 and played[1].kind=="positional",
    "Powered mains furniture radio should emit local 3D sound")
assert(emitterTicks==1,"Owned emitter must tick immediately to start queued FMOD sounds")
tick(10)
assert(emitterTicks==11,"Owned emitter must tick every frame between 30-tick receiver scans")
mains.state.chan=101400
tick()
assert(#stopped==1,"Retuning furniture radio should stop audio")
cue("b","tuned")
assert(#played==1,"Wrong frequency must be silent")
mains.state.chan=101200
mains.state.on=false
vehicles={vehicle}
cue("c","tuned")
assert(#played==2 and played[2].kind=="positional",
    "Powered and tuned car radio should emit local 3D sound")
powered=false
tick()
assert(#stopped==2,"Loss of vehicle power should stop audio")
carRadio.state.chan=101400
cue("d","tuned")
assert(#played==2,"Unpowered/retuned vehicle radio cannot play")
cue("e","global")
assert(#played==3 and played[3].kind=="global","Explicit global bypass should remain")
mains.state.on=true;mains.state.chan=100400;vehicles={}
local beforeStops=#stopped
cue("9","tuned",100400)
tick(30)
assert(#stopped==beforeStops,"Positional CUE must retain actual frequency, not station default")
mains.state.on=false
tick(30)
-- Track received late is deferred to next song, not restarted at timestamp zero.
events.server("SiegerRadio","STATION_TRACK",{
 version=version,requestId=string.rep("f",32),clip="test_tone",
 frequency=101200,scope="tuned",durationMs=8000,remainingMs=4000})
tick(30)
assert(#played==4,"Late song tuning should wait for the next playlist track")
-- New on-air behavior: a playing FMOD handle is primed *even with the
-- receiver switched off*, then muted/unmuted without a second playSound.
local playBefore=#played
local stopBefore=#stopped
events.server("SiegerRadio","STATION_TRACK",{
 version=version,requestId=string.rep("1",32),clip="test_tone",
 frequency=101200,scope="tuned",durationMs=8000,remainingMs=8000})
tick(30)
assert(#played==playBefore+1 and played[#played].kind=="positional",
    "Start a muted station stream at song boundary without tuned receiver")
assert(gain==0,"Radio turned off must start inaudible; never leak playback")
assert(emitterTicks>11,"Silent FMOD stream must continue ticking")
mains.state.on=true;mains.state.chan=101200
tick(30)
assert(gain>0 and last3d==true,"Tuning on in middle of song must unmute live 3D audio")
playerX=500.5
tick(30)
assert(gain==0,"Walking out of radio range must mute station")
assert(#played==playBefore+1 and #stopped==stopBefore,
    "Walking out must neither stop the current handle nor restart the song")
playerX=100.5
tick(30)
assert(gain>0 and #played==playBefore+1 and #stopped==stopBefore,
    "Returning to range must restore the SAME in-progress song")
mains.state.on=false
tick(30)
assert(gain==0 and #stopped==stopBefore,"Power-off should mute, not destroy stream")
mains.state.on=true
tick(30)
assert(gain>0 and #played==playBefore+1,"Power-on must resume current track")
mains.state.chan=101400
tick(30)
assert(gain==0,"Retuning off station must mute")
mains.state.chan=101200
tick(30)
assert(gain>0 and #played==playBefore+1,"Retuning back restores current track")
mains.state.volume=0
tick(30)
assert(gain==0,"Volume zero must mute")
mains.state.volume=0.7
tick(30)
assert(gain>0,"Restoring volume must unmute without restarting")
-- Switching from furniture to a powered car is a route change, not a
-- different song. Portable receivers should use nonpositional sound.
mains.state.on=false;carRadio.state.chan=101200;powered=true;vehicles={vehicle}
tick(30)
assert(gain>0 and last3d==true and #played==playBefore+1,
    "Powered car radio should receive the existing live FMOD stream")
powered=false
tick(30)
assert(gain==0,"Unpowered car radio must be silent")
vehicles={}
local handRadio={getDeviceData=function()return carRadio end}
equipped={handRadio};powered=true
tick(30)
assert(gain>0 and last3d==false and #played==playBefore+1,
    "Switching to portable radio must keep the track and use 2D routing")
equipped={}
tick(30)
assert(gain==0,"Removing the portable radio should mute, not stop the song")
events.server("SiegerRadio","STATION_TRACK",{
 version=version,requestId=string.rep("1",32),clip="test_tone",
 frequency=101200,scope="tuned",durationMs=8000,remainingMs=3000})
tick(30)
assert(#played==playBefore+1,"Duplicate snapshot cannot restart the current song")
-- A new station track invalidates the old handle exactly once.
events.server("SiegerRadio","STATION_TRACK",{
 version=version,requestId=string.rep("2",32),clip="test_tone",
 frequency=101200,scope="tuned",durationMs=8000,remainingMs=8000})
tick(30)
assert(#played==playBefore+2 and #stopped==stopBefore+1,
    "Next song must dispose previous stream and prime a fresh one")
events.server("SiegerRadio","STATION_STOP",{version=version})
assert(#stopped==stopBefore+2,"Station stop must release owned FMOD stream")
tick(30)
assert(#played==playBefore+2,"Station stop must prevent later playback")
print("PASS: cues, client-owned emitters, on-air mute/unmute, range, retune, power, car, portable, replay guard and stop")
