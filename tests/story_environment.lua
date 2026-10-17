-- Offline Lua 5.1 behavioral harness for exact window edits and blood.
-- Real pinned B42.21 dedicated server / 2-client sync is a separate gate.
local runtime=arg[1] or "story/runtime/SiegerStoryDirector.lua"
local files,events={},{};
Events={OnServerStarted={Add=function(fn)events.started=fn end},
        OnTick={Add=function(fn)events.tick=fn end},
        OnZombieDead={Add=function()end},
        LoadGridsquare={Add=function()end}}
isClient=function()return false end
local function list(a) return {size=function()return #a end,
                              get=function(_,i)return a[i+1] end} end
getFileReader=function(name)
 if not files[name] then return nil end
 local lines={};for v in files[name]:gmatch("[^\n]+") do lines[#lines+1]=v end
 local i=0;return {readLine=function()i=i+1;return lines[i]end,close=function()end}
end
getFileWriter=function(name,create,append)
 if not append then files[name]="" end
 return {write=function(_,v)files[name]=(files[name] or "")..v end,close=function()end}
end
instanceof=function(v,name)return v and v.class==name end
sendAddItemToContainer=function()end
instanceItem=function(id)
 local md={},nil
 local item={getModData=function()return md end,getPageToWrite=function()return 10 end,
  setCanBeWrite=function()end,canBeWrite=function()return true end,
  setNumberOfPages=function()end,getNumberOfPages=function()return 1 end,
  addPage=function()end,seePage=function()return "Story API check" end}
 return item
end
local floor={class="IsoObject",getSprite=function()return {getName=function()return "floor_carpet_motif_8" end}end}
local function makeWindow()
 local md={}
 local w={class="IsoWindow",smashed=false,barricade=nil,
   getModData=function()return md end,transmitModdata=function()end,
   getSprite=function()return {getName=function()return "walls_commercial_01_80" end}end,
   isSmashed=function(self)return self.smashed end,
   isGlassRemoved=function()return false end,
   getBarricadeOnSameSquare=function(self)return self.barricade end,
   getBarricadeOnOppositeSquare=function()return nil end,
   isBarricadeAllowed=function()return true end,
   smashWindow=function(self,bRemote,doAlarm)
     assert(bRemote==false and doAlarm==false)
     self.smashed=true
   end}
 return w
end
local w1,w2=makeWindow(),makeWindow()
local function makeSq(x,y,window)
 local md={},nil
 local splats=0
 local objs={floor,window}
 local sq={getX=function()return x end,getY=function()return y end,getZ=function()return 0 end,
  getRoom=function()return nil end,getModData=function()return md end,
  transmitModdata=function()end,getObjects=function()return list(objs) end,
  getWorldObjects=function()return list({})end,
  splatBlood=function(self,dist,alpha)
    assert(dist==0 and alpha==0.60);splats=splats+1
  end,
  getSplats=function()return splats end}
 return sq
end
local sq1=makeSq(1,2,w1)
local sq2=makeSq(3,4,w2)
getCell=function()
 return {getGridSquare=function(_,x,y,z)
  if z==0 and x==1 and y==2 then return sq1 end
  if z==0 and x==3 and y==4 then return sq2 end
 end}
end
IsoBarricade={AddBarricadeToObject=function(obj,onOpposite)
 assert(onOpposite==false and obj==w2)
 local md={}
 local bar={class="IsoBarricade",planks=0,getModData=function()return md end,
  canAddPlank=function(self)return self.planks<4 end,
  addPlank=function(self)a=self;self.planks=self.planks+1 end,
  transmitCompleteItemToClients=function(self)assert(self.planks==2)end}
 obj.barricade=bar
 return bar
end}
SiegerStoryScenes={schema=1,world="story_test",scenes={},inspect={}}
dofile(runtime);events.started()
local function packet(id)
 local lines={
 table.concat({"blood","old_floor","1","2","0","-","-1","-","-","floor_carpet_motif_8","2"},"\t"),
 table.concat({"window","smashed_glass","1","2","0","window","1",
               "walls_commercial_01_80","IsoWindow","smash"},"\t"),
 table.concat({"barricade","boarded_window","3","4","0","window","1",
               "walls_commercial_01_80","IsoWindow","2"},"\t")}
 files["SiegerStoryLiveRequest.txt"]=
  table.concat({"v1",id,"story_test","env_test_001",string.rep("f",64),"3"},"\t")
  .."\n"..table.concat(lines,"\n").."\n"
end
packet(string.rep("a",32))
for i=1,120 do events.tick() end
assert(sq1:getSplats()==2,"Blood was not applied exactly twice")
assert(w1.smashed==true,"Window was not smashed")
assert(w2.barricade and w2.barricade.planks==2,"Barricade missing/planks incorrect")
assert(w1:getModData().SiegerStoryKind=="window")
assert(w2.barricade:getModData().SiegerStoryKind=="barricade")
assert(files["SiegerStoryQuestEvents.txt"]:find("\tedit\tenv_test_001\told_floor\t",1,true))
assert(files["SiegerStoryQuestEvents.txt"]:find("\tedit\tenv_test_001\tsmashed_glass\t",1,true))
assert(files["SiegerStoryQuestEvents.txt"]:find("\tspawn\tenv_test_001\tboarded_window\t",1,true))
assert(files["SiegerStoryLiveResult.txt"]:find("\tcomplete\t3\t0\t0",1,true))
local saved=files["SiegerStoryQuestEvents.txt"]
dofile(runtime);events.started()
for i=1,120 do events.tick() end
assert(sq1:getSplats()==2 and w2.barricade.planks==2)
assert(files["SiegerStoryQuestEvents.txt"]==saved,"Actions replayed and duplicated")
assert(files["SiegerStoryLiveResult.txt"]:find("boarded_window\talready",1,true))
print("PASS: guarded blood, smashed window and tagged barricade with no replay")
