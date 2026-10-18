-- Standalone Lua 5.1 client mock for IsoRadio world furniture and vehicles.
local path=arg[1] or "mods/SiegerRadio/42/media/lua/client/SiegerRadioClient.lua"
local f=assert(io.open(path,"rb"));local script=f:read("*a");f:close()
local version=assert(script:match('local VERSION%s*=%s*"([^"]+)"'))
local events,played,stopped={},{},{}
Events={OnGameStart={Add=function(fn)events.started=fn end},
        OnServerCommand={Add=function(fn)events.server=fn end},
        OnTick={Add=function(fn)events.tick=fn end},
        OnFillWorldObjectContextMenu={Add=function(fn)events.menu=fn end}}
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
local playerZ=0
local upstairsOnly=false
local occupiedCar=nil
local carX=101.8
local player={getVehicle=function()return occupiedCar end,getX=function()return playerX end,getY=function()return 100.5 end,
    getZ=function()return playerZ end,getInventory=function()return inventory end,
    getPrimaryHandItem=function()return nil end,getSecondaryHandItem=function()return nil end}
getSpecificPlayer=function(i)assert(i==0);return player end
local powered=true
local carPart={getDeviceData=function()return carRadio end,
 hasDevicePower=function()return powered end}
local vehicle={getX=function()return carX end,getY=function()return 100.5 end,
 getZ=function()return 0 end,getPartCount=function()return 1 end,
 getPartByIndex=function(_,i)assert(i==0);return carPart end}
local vehicles={}
local square={getObjects=function()return list({furniture})end}
getCell=function()
 return {getGridSquare=function(_,x,y,z)
   if upstairsOnly then
     if x==106 and y==100 and z==2 then return square end
     return nil
   end
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
siegradioBridgePlay=function(id,offset,is3d,x,y,z,gain,vehicle)
 assert(type(id)=="string" and type(offset)=="number" and offset>=0)
 assert(type(is3d)=="boolean" and type(x)=="number" and gain>0)
 assert(type(vehicle)=="boolean" and (not vehicle or is3d))
 starts[#starts+1]={id=id,offset=offset,is3d=is3d,x=x,gain=gain,vehicle=vehicle}
 return true
end
siegradioBridgeUpdate=function(id,is3d,x,y,z,gain,vehicle)
 assert(type(vehicle)=="boolean" and (not vehicle or is3d))
 updates[#updates+1]={id=id,is3d=is3d,x=x,gain=gain,vehicle=vehicle}
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
assert(math.abs(starts[1].gain-.65*.7)<.00001,
       "Station music gain follows the device slider, not the old 65% clamp")
local liveStarts=#starts
mains.state.volume=.1
tick(30)
assert(math.abs(updates[#updates].gain-.065)<.00001 and #starts==liveStarts,
       "Turned-down receiver uses 10% music gain on SAME FMOD stream")
mains.state.volume=1
tick(30)
assert(math.abs(updates[#updates].gain-.65)<.00001 and #starts==liveStarts,
       "100% slider reaches max music gain without stream reopen")
mains.state.volume=.7
tick(30)
-- Turning the player's body/camera in place must NEVER transform a nearby
-- fixed radio into 2D or move it to the listener. The actual rear
-- attenuation is owned by FMOD/Viewpoint and needs a live hearing test.
local originalFacing=player.getForwardDirection
player.getForwardDirection=function()return {x=1,y=0}end
tick(30)
local front=updates[#updates]
player.getForwardDirection=function()return {x=-1,y=0}end
tick(30)
local behind=updates[#updates]
assert(#starts==1 and front and behind
    and front.is3d and behind.is3d
    and front.x==behind.x and front.gain==behind.gain,
    "A 180-degree turn must retain world-space 3D source and unchanged radio gain")
player.getForwardDirection=originalFacing
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
-- Local width diagnostics must never create or seek another stream.
local choices={}
ISContextMenu={getNew=function()return {
    addOption=function(_,label,degrees,callback)
        choices[#choices+1]={degrees=degrees,callback=callback}
    end}end}
local context={addOption=function()return {} end,addSubMenu=function()end}
local angles={}
assert(events.menu==nil,"Temporary radio A/B menus removed")
-- Power, volume and retuning should all release and later re-seek.
mains.state.on=false
tick(60)
assert(nativeStops==2,"Power off must stop stream")
mains.state.on=true
tick(60)
assert(#starts==3 and starts[3].offset>starts[2].offset,"Power on resumes live time")
mains.state.chan=101400
tick(60)
assert(nativeStops==3,"Retune away must stop stream")
mains.state.chan=101200
tick(60)
assert(#starts==4 and starts[4].offset>starts[3].offset,"Retune back seeks again")
mains.state.volume=0
tick(60)
assert(nativeStops==4,"Muted radio must release channel")
mains.state.volume=0.7
tick(60)
assert(#starts==5,"Restore volume opens one stream")
-- Car uses positional audio; switching to carried radio changes 3D -> 2D
mains.state.on=false;carRadio.state.chan=101200;powered=true;vehicles={vehicle}
tick(60)
assert(#starts==5 and #updates>updatesBefore and updates[#updates].x==101.8
    and updates[#updates].vehicle==true,
    "World-to-car source must retain one stream and select car FMOD range")
local lastX=starts[#starts].x
tick(60)
assert(#updates>updatesBefore and starts[#starts].x==lastX,"Car source should update")
-- Drive past many chunks with a stale player render coordinate and an
-- empty vehicle census: occupied car remains the SAME source every tick.
occupiedCar=vehicle;vehicles={}
local cabinTransitions={}
siegradioBridgeSetCabin=function(inside)cabinTransitions[#cabinTransitions+1]=inside;return true end
local drivingUpdates=#updates
local drivingStarts=#starts
local drivingStops=nativeStops
for i=1,90 do carX=carX+3;tick(1) end
assert(#updates>=drivingUpdates+90 and updates[#updates].x==carX,
    "Moving source must update each tick, not freeze for 30 frames")
assert(#starts==drivingStarts and nativeStops==drivingStops,
    "Chunk boundaries/driving must not release, reopen or reseek the stream")
assert(#cabinTransitions==1 and cabinTransitions[1]==true,
    "Occupied car enables cabin width once without per-frame retries")
carX=101.8;occupiedCar=nil;vehicles={vehicle}
tick(1)
assert(#cabinTransitions==2 and cabinTransitions[2]==false,"Exit restores external point width")
powered=false
tick(60)
assert(nativeStops>=5,"Car power off must release stream")
vehicles={}
local handRadio={getDeviceData=function()return carRadio end}
equipped={handRadio}
tick(60)
assert(starts[#starts].is3d==false,"Portable must use 2D mode")
equipped={}
tick(60)
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
local duringMusic=#starts
local preCueStops=nativeStops
cue("7","tuned")
assert(nativeStops==preCueStops+1 and #starts==duringMusic,
    "Short CUE must preempt music immediately without overlapping streams")
-- Stream resumption is searched on a 60-tick inactive cadence after
-- the 750 ms CUE expires; tick phase may change after live gain tests.
tick(120)
assert(#starts==duringMusic+1,
    "Station must return at current on-air position after short CUE")
events.server("SiegerRadio","STATION_STOP",{version=version})
local endingStops=nativeStops
tick(60)
assert(nativeStops==endingStops and #starts==duringMusic+1,
    "Station stop releases exactly one stream and cannot restart audio")

-- 30-tile vehicle reach should not extend indoor furniture to 30 tiles.
mains.state.on=false;carRadio.state.chan=101200;carRadio.state.volume=1;powered=true
vehicles={vehicle};occupiedCar=nil;playerZ=0;playerX=carX-29.5
local cueCount=#played
cue("6","tuned")
assert(#played==cueCount+1 and played[#played].name=="SiegerRadio_TestTone_Vehicle",
    "Vehicle at 29.5 tiles must have 30-tile short CUE")
playerX=carX-30.5
cue("5","tuned")
assert(#played==cueCount+1,"Vehicle beyond 30 tiles must be silent")
vehicles={};mains.state.on=true;mains.state.chan=101200
upstairsOnly=true;playerX=100.5;playerZ=1
cue("4","tuned")
assert(#played==cueCount+2 and played[#played].name=="SiegerRadio_TestTone",
    "Furniture on third scanned floor cannot be omitted at former 1200 cap")
-- Short CUE and music use the same receiver census. A low-volume car
-- is NOT a 30-tile speaker anymore, even when the GameSound CUE's own
-- native distanceMax happens to be 30.
upstairsOnly=false;playerZ=0;carX=101.8;playerX=carX-15
mains.state.on=false;carRadio.state.chan=101200;carRadio.state.volume=.1
vehicles={vehicle};occupiedCar=nil;powered=true
local beforeQuietCar=#played
cue("8","tuned")
assert(#played==beforeQuietCar,
       "At 10% a vehicle at 15 cells must be outside the 8.4-cell receiver census")
carRadio.state.volume=1
cue("0","tuned")
assert(#played==beforeQuietCar+1 and played[#played].name=="SiegerRadio_TestTone_Vehicle",
       "At 100% car radio must still reach 15 cells")
-- Furniture is also volume-limited, independently of the 30-cell vehicle scan.
vehicles={};playerX=111.5;mains.state.on=true;mains.state.chan=101200
mains.state.volume=.1
local beforeQuietFurniture=#played
cue("3","tuned")
assert(#played==beforeQuietFurniture,
       "Quiet furniture must not be heard at 10 tiles (radius 3.9)")
mains.state.volume=1
-- A fresh 32-digit request ID: the earlier smoke test already used "b"*32.
events.server("SiegerRadio","CUE",{
 version=version,requestId=string.rep("a",31).."0",
 clip="test_tone",frequency=101200,scope="tuned",durationMs=750})
assert(#played==beforeQuietFurniture+1 and played[#played].name=="SiegerRadio_TestTone",
       "Full-volume furniture must be audible at 10 cells")
print("PASS: device-volume range 3.9/12 furniture and 8.4/30 car, normalized gain, streaming/motion")
