-- Behavioral test for one authored corpse + same-square revolver.
-- Lua 5.1 mock only: final proof requires pinned B42 JVM and clients.
local runtime=arg[1] or "story/runtime/SiegerStoryDirector.lua"
local files,events,squares={},{},{}
local createCount=0
isClient=function() return false end
Events={
 OnServerStarted={Add=function(fn) events.started=fn end},
 OnTick={Add=function(fn) events.tick=fn end},
 LoadGridsquare={Add=function(fn) events.load=fn end},
 OnZombieDead={Add=function(fn) events.dead=fn end}
}
local function list(v)
 return {size=function() return #v end,get=function(_,i) return v[i+1] end}
end
local function lines(s)
 local result={}
 for line in (s or ""):gmatch("[^\n]+") do result[#result+1]=line end
 return result
end
getFileReader=function(name)
 if not files[name] then return nil end
 local values=lines(files[name]);local cursor=0
 return {readLine=function() cursor=cursor+1;return values[cursor] end,close=function()end}
end
getFileWriter=function(name,unused,append)
 if not append then files[name]="" end
 return {write=function(_,v) files[name]=(files[name] or "")..v end,close=function()end}
end
instanceof=function(obj,cls) return obj and obj.class==cls end
sendAddItemToContainer=function()end
instanceItem=function(kind)
 local md={}
 local item={kind=kind,class="InventoryItem"}
 function item:getModData() return md end
 function item:getPageToWrite() return 10 end
 function item:setCanBeWrite()end
 function item:canBeWrite()return true end
 function item:setNumberOfPages(n)self.pages=n end
 function item:getNumberOfPages()return self.pages end
 function item:addPage(i,p)self.note=p end
 function item:seePage()return self.note end
 function item:getFullType()return self.kind end
 return item
end
local floor={class="IsoObject",getSprite=function()
 return {getName=function() return "floors_interior_tilesandwood_01_21" end}
end}
local function square(x,y,z)
 local k=x..":"..y..":"..z
 if not squares[k] then
  local md,corpses,ground={},{},{}
  local sq={
   getX=function()return x end,getY=function()return y end,getZ=function()return z end,
   getRoom=function()return {getName=function()return "bathroom" end}end,
   getObjects=function()return list({floor})end,
   getDeadBodys=function()return list(corpses)end,
   getWorldObjects=function()return list(ground)end,
   getModData=function()return md end,transmitModdata=function()end,
   AddWorldInventoryItem=function(_,item,ox,oy,oz)
    assert(ox==0.72 and oy==0.60 and oz==0)
    ground[#ground+1]={getItem=function()return item end}
    return item
   end,
   bodies=corpses,ground=ground
  }
  squares[k]=sq
 end
 return squares[k]
end
getCell=function()
 return {getGridSquare=function(_,x,y,z)
  if z==0 and ((x==10602 and y==9403) or (x==10602 and y==9404)) then
   return square(x,y,z)
  end
 end}
end
createRandomDeadBody=function(sq,blood)
 assert(blood==1)
 createCount=createCount+1
 local md={}
 local body={class="IsoDeadBody",
   getModData=function()return md end,transmitModdata=function()end,
   getSquare=function()return sq end
 }
 sq.bodies[#sq.bodies+1]=body
 return body
end
SiegerStoryScenes={schema=1,world="story_test",scenes={},inspect={}}
dofile(runtime);events.started()
local function packet(requestId,scene,actionId,x,y,floorSprite)
 local line=table.concat({"corpse",actionId,tostring(x),tostring(y),"0",
                          "-","-1","-","-","bathroom",floorSprite,"1","Base.Revolver"},"\t")
 files["SiegerStoryLiveRequest.txt"]=
  table.concat({"v1",requestId,"story_test",scene,string.rep("f",64),"1"},"\t")
  .."\n"..line.."\n"
end
local floorSprite="floors_interior_tilesandwood_01_21"
local scene="smokeys_shop_04_bathroom_corpse"
local action="bathroom_body_and_revolver"
packet(string.rep("a",32),scene,action,10602,9403,floorSprite)
for _=1,120 do events.tick() end
local sq=square(10602,9403,0)
assert(createCount==1 and #sq.bodies==1 and #sq.ground==1)
local body=sq.bodies[1]
local gun=sq.ground[1]:getItem()
assert(body:getModData().SiegerStoryKind=="corpse")
assert(body:getModData().SiegerStoryQuest==scene)
assert(gun:getModData().SiegerStoryKind=="item")
assert(gun:getFullType()=="Base.Revolver")
assert(body:getModData().SiegerStoryToken=="SiegerStory:"..scene..":"..action..":corpse")
assert(gun:getModData().SiegerStoryToken=="SiegerStory:"..scene..":"..action..":revolver")
assert(files["SiegerStoryLiveResult.txt"]:find("\tcomplete\t1\t0\t0",1,true))
local ledger=files["SiegerStoryQuestEvents.txt"]
assert(ledger:find("\tspawn\t"..scene.."\t"..action.."\t",1,true))
assert(ledger:find("\tcorpse\t10602\t9403\t0",1,true))
assert(ledger:find("\titem\t10602\t9403\t0",1,true))
-- Re-loading the same request after a fresh Lua runtime must not create new objects.
dofile(runtime);events.started()
for _=1,120 do events.tick() end
assert(createCount==1 and #sq.bodies==1 and #sq.ground==1)
assert(files["SiegerStoryLiveResult.txt"]:find(action.."\talready",1,true))
-- Mismatched floor selector fails before touching the world.
packet(string.rep("b",32),"wrong_floor_scene","wrong_floor_action",10602,9404,
       "floors_interior_tilesandwood_01_99")
for _=1,120 do events.tick() end
local sq2=square(10602,9404,0)
assert(#sq2.bodies==0 and #sq2.ground==0 and createCount==1)
assert(files["SiegerStoryLiveResult.txt"]:find("\tfailed\t0\t0\t1",1,true))
-- Simulate audit ledger I/O failure after actual corpse creation.
local writer=getFileWriter
getFileWriter=function(name,create,append)
 if name=="SiegerStoryQuestEvents.txt" then return nil end
 return writer(name,create,append)
end
packet(string.rep("c",32),"audit_failure_scene","audit_failure_body",10602,9404,floorSprite)
for _=1,120 do events.tick() end
assert(createCount==2 and #sq2.bodies==1 and #sq2.ground==0)
assert(files["SiegerStoryLiveResult.txt"]:find("\tfailed\t0\t0\t1",1,true))
dofile(runtime);events.started()
for _=1,120 do events.tick() end
assert(createCount==2 and #sq2.bodies==1 and #sq2.ground==0,
       "Ambiguous corpse retry duplicated body or gun")
getFileWriter=writer
print("PASS: one corpse+revolver with unique tags, replay idempotence, floor gate, audit-failure lock")
