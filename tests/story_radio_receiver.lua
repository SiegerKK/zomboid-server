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
 local data={on=true,chan=101300,power=isMains and 0 or 1,volume=0.7,canPower=true}
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
local player={getX=function()return 100.5 end,getY=function()return 100.5 end,
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
 getVehicles=function()return list(vehicles)end}
end
local emitter={setPos=function()end,
 playSound=function(_,name)played[#played+1]={name=name,kind="positional"};return 15 end,
 setVolume=function(_,handle,vol)assert(handle==15 and vol>0)end,
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
 clip="test_tone",frequency=freq or 101300,scope=scope,durationMs=750})
end
dofile(path)
events.started()
events.server("SiegerRadio","HELLO_ACK",{version=version})
cue("a","tuned")
assert(#played==1 and played[1].kind=="positional",
    "Powered mains furniture radio should emit local 3D sound")
mains.state.chan=101400
tick()
assert(#stopped==1,"Retuning furniture radio should stop audio")
cue("b","tuned")
assert(#played==1,"Wrong frequency must be silent")
mains.state.chan=101300
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
-- Track received late is deferred to next song, not restarted at timestamp zero.
events.server("SiegerRadio","STATION_TRACK",{
 version=version,requestId=string.rep("f",32),clip="test_tone",
 frequency=101300,scope="tuned",durationMs=8000,remainingMs=4000})
tick(30)
assert(#played==3,"Late song tuning should wait for the next playlist track")
print("PASS: mains furniture, car power, FM retune, 3D emission, global cue, late-join safety")
