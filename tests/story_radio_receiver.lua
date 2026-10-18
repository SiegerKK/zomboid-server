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
-- The Java bridge is a separate component: mock only its public Lua
-- entry points here. A separate headless JVM test exercises reflection JNI.
local starts,updates,nativeStops={},{},0
siegradioBridgeReady=function()return true end
siegradioBridgePlay=function(id,offset,is3d,x,y,z,gain)
 assert(type(id)=="string" and type(offset)=="number" and offset>=0)
 assert(type(is3d)=="boolean" and type(x)=="number" and gain>0)
 starts[#starts+1]={id=id,offset=offset,is3d=is3d,x=x,gain=gain}
 return true
end
siegradioBridgeUpdate=function(id,is3d,x,y,z,gain)
 updates[#updates+1]={id=id,is3d=is3d,x=x,gain=gain}
 return true
end
siegradioBridgeStop=function()nativeStops=nativeStops+1 end
-- A new player joins halfway through an already playing 60-second song.
-- There must be NO audio without an actual tuned powered local receiver.
local startSoundCount=#played
mains.state.on=false;mains.state.chan=101200
carRadio.state.chan=101400;vehicles={};equipped={}
events.server("SiegerRadio","STATION_TRACK",{
 version=version,requestId=string.rep("1",32),clip="north_track_01",
 frequency=101200,scope="tuned",durationMs=60000,remainingMs=30000})
tick(180) -- ~3 seconds of walking with no active radio
assert(#starts==0 and #played==startSoundCount,
    "Inactive player must not start/mute/decode any station stream")
mains.state.on=true
tick(60)
assert(#starts==1 and starts[1].offset>=30000 and starts[1].is3d,
    "Late tuner must seek to live midpoint, not restart from zero")
local firstOffset=starts[1].offset
-- Walk away for >3 seconds, releasing the channel and PCM buffers.
playerX=500.5
tick(240)
assert(nativeStops==1,"Leaving radio range must release stream immediately")
local updatesBefore=#updates
tick(120)
assert(#starts==1 and #updates==updatesBefore,
    "No range means no continuous invisible FMOD updates/decoding")
playerX=100.5
tick(60)
assert(#starts==2 and starts[2].offset>firstOffset+4000,
    "Return must seek to current on-air time with new stream")
-- Power, volume and retuning should all release and later re-seek.
mains.state.on=false
tick(30)
assert(nativeStops==2,"Power off must stop stream")
mains.state.on=true
tick(60)
assert(#starts==3 and starts[3].offset>starts[2].offset,"Power on resumes live time")
mains.state.chan=101400
tick(30)
assert(nativeStops==3,"Retune away must stop stream")
mains.state.chan=101200
tick(60)
assert(#starts==4 and starts[4].offset>starts[3].offset,"Retune back seeks again")
mains.state.volume=0
tick(30)
assert(nativeStops==4,"Muted radio must release channel")
mains.state.volume=0.7
tick(60)
assert(#starts==5,"Restore volume opens one stream")
-- Car uses positional audio; switching to carried radio changes 3D -> 2D
mains.state.on=false;carRadio.state.chan=101200;powered=true;vehicles={vehicle}
tick(30)
assert(#starts==5+1 and starts[#starts].is3d,"Car should use positional FMOD stream")
local lastX=starts[#starts].x
tick(30)
assert(#updates>updatesBefore and starts[#starts].x==lastX,"Car source should update")
powered=false
tick(30)
assert(nativeStops>=6,"Car power off must release stream")
vehicles={}
local handRadio={getDeviceData=function()return carRadio end}
equipped={handRadio}
tick(60)
assert(starts[#starts].is3d==false,"Portable must use 2D mode")
equipped={}
tick(30)
local previousStarts=#starts
events.server("SiegerRadio","STATION_TRACK",{
 version=version,requestId=string.rep("1",32),clip="north_track_01",
 frequency=101200,scope="tuned",durationMs=60000,remainingMs=20000})
tick(60)
assert(#starts==previousStarts,"Duplicate server HELLO cannot create playback")
events.server("SiegerRadio","STATION_TRACK",{
 version=version,requestId=string.rep("2",32),clip="north_track_02",
 frequency=101200,scope="tuned",durationMs=60000,remainingMs=60000})
tick(60)
assert(#starts==previousStarts,"New track without tuned radio stays asleep")
mains.state.on=true;mains.state.chan=101200
tick(60)
assert(#starts==previousStarts+1 and starts[#starts].id=="north_track_02",
    "Newly powered radio tunes into new server track")
events.server("SiegerRadio","STATION_STOP",{version=version})
local endingStops=nativeStops
tick(60)
assert(nativeStops==endingStops and #starts==previousStarts+1,
    "Station stop releases exactly one stream and cannot restart audio")
print("PASS: cues, Java stream demand, late join/return seek, release, power, tune, car, portable, de-dup and stop")
