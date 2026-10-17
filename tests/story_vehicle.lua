-- Offline Lua 5.1 test for strict parked car spawn and replay resistance.
-- Requires pinned Build42.21 game JVM plus two client check before deploying.
local runtime=arg[1] or "story/runtime/SiegerStoryDirector.lua"
local files,events={},{};
Events={OnServerStarted={Add=function(f)events.started=f end},
        OnTick={Add=function(f)events.tick=f end},
        LoadGridsquare={Add=function()end},
        OnZombieDead={Add=function()end}}
isClient=function()return false end
local function list(xs)return {size=function()return #xs end,get=function(_,i)return xs[i+1]end}end
getFileReader=function(name)
 if not files[name] then return nil end
 local rows={};for row in files[name]:gmatch("[^\n]+") do rows[#rows+1]=row end
 local n=0;return {readLine=function()n=n+1;return rows[n]end,close=function()end}
end
getFileWriter=function(name,c,a)
 if not a then files[name]=""end
 return {write=function(_,v)files[name]=(files[name] or "")..v end,close=function()end}
end
instanceof=function(o,typ)return o and o.class==typ end
sendAddItemToContainer=function()end
instanceItem=function(kind)
 local md={}
 return {getModData=function()return md end,
  setCanBeWrite=function()end,canBeWrite=function()return true end,
  setNumberOfPages=function(self,n)self.n=n end,getNumberOfPages=function(self)return self.n or 1 end,
  addPage=function(self,i,v)self.page=v end,seePage=function(self)return self.page end,
  getPageToWrite=function()return 10 end}
end
ScriptManager={instance={getVehicle=function(_,script)
 if script=="Base.Van" then return {script=script} end
end}}
IsoDirections={N=1,E=2,S=3,W=4}
local vehicles={}
local spawnCount=0
local sqCache={}
local function square(x,y,z)
 local k=x..":"..y..":"..z
 if not sqCache[k] then
  local md={}
  sqCache[k]={getX=function()return x end,getY=function()return y end,getZ=function()return z end,
   getModData=function()return md end,transmitModdata=function()end,
   getRoom=function()return nil end,isOutside=function()return true end,
   isFree=function()return true end,getObjects=function()return list({})end,
   getWorldObjects=function()return list({})end}
 end
 return sqCache[k]
end
local function vehicleSet()
 return {iterator=function()
  local i=0;return {hasNext=function()return i<#vehicles end,
    next=function()i=i+1;return vehicles[i]end}
 end}
end
getCell=function()
 return {getGridSquare=function(_,x,y,z)return square(x,y,z)end,
         getVehicles=function()return vehicleSet()end}
end
getOnlinePlayers=function()return list({})end
addVehicleDebug=function(script,dir,skin,location)
 assert(script=="Base.Van" and dir==IsoDirections.S and skin==nil)
 assert(location:getX()==10620 and location:getY()==9209)
 spawnCount=spawnCount+1
 local md={}
 local car={class="BaseVehicle",getModData=function()return md end,
   transmitModdata=function()end,getScriptName=function()return script end,
   getId=function()return 47 end,getX=function()return 10620.5 end,
   getY=function()return 9209.5 end,getZ=function()return 0 end}
 vehicles[#vehicles+1]=car
 return car
end
SiegerStoryScenes={schema=1,world="story_test",scenes={},inspect={}}
dofile(runtime);events.started()
local function request(id,scene,x,y)
 local line=table.concat({"vehicle","route17_van_probe",tostring(x),tostring(y),"0",
   "-","-1","-","-","Base.Van","S","-1"},"\t")
 files["SiegerStoryLiveRequest.txt"]=
  table.concat({"v1",id,"story_test",scene,string.rep("f",64),"1"},"\t")
  .."\n"..line.."\n"
end
request(string.rep("a",32),"vehicle_probe_01",10620,9209)
for i=1,120 do events.tick() end
assert(spawnCount==1 and #vehicles==1)
local car=vehicles[1]
assert(car:getModData().SiegerStoryToken=="SiegerStory:vehicle_probe_01:route17_van_probe:vehicle")
assert(car:getModData().SiegerStoryKind=="vehicle")
assert(files["SiegerStoryQuestEvents.txt"]:find("\tspawn\tvehicle_probe_01\troute17_van_probe\t",1,true))
assert(files["SiegerStoryLiveResult.txt"]:find("\tcomplete\t1\t0\t0",1,true))
-- Replay of exact same packet must not create second vehicle.
dofile(runtime);events.started()
for i=1,120 do events.tick() end
assert(spawnCount==1)
assert(files["SiegerStoryLiveResult.txt"]:find("route17_van_probe\talready",1,true))
-- A different scene cannot spawn within eight cells of an existing car.
request(string.rep("b",32),"vehicle_probe_02",10622,9211)
for i=1,120 do events.tick() end
assert(spawnCount==1)
assert(files["SiegerStoryLiveResult.txt"]:find("\tfailed\t0\t0\t1",1,true))
print("PASS: bounded stock vehicle addVehicleDebug, ownership tag, replay and car-collision refusal")
