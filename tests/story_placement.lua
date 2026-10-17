-- Mock dedicated-server behavior for explicit per-tile item pose and token relocation.
local runtime=arg[1] or "story/runtime/SiegerStoryDirector.lua"
local files,events,grids={},{},{}
isClient=function()return false end
Events={
 OnServerStarted={Add=function(fn)events.started=fn end},
 OnTick={Add=function(fn)events.tick=fn end},
 LoadGridsquare={Add=function(fn)events.load=fn end},
 OnZombieDead={Add=function(fn)events.dead=fn end}}
local function list(v)return {size=function()return #v end,get=function(_,i)return v[i+1]end}end
getFileReader=function(name)
 if not files[name]then return nil end
 local t={};for l in files[name]:gmatch("[^\n]+") do t[#t+1]=l end
 local i=0;return {readLine=function()i=i+1;return t[i]end,close=function()end}
end
getFileWriter=function(name,create,append)
 if not append then files[name]="" end
 return {write=function(_,txt)files[name]=(files[name]or"")..txt end,close=function()end}
end
local function furniture(class,sprite,isTable)
 return {class=class,getSprite=function()return {getName=function()return sprite end}end,
   isTableSurface=function()return isTable end,getSurfaceOffset=function()return 27 end,
   getSurfaceOffsetNoTable=function()return 27 end}
end
local floor=furniture("IsoObject","floor_carpet_motif_8",false)
local tableObj=furniture("IsoObject","furniture_tables_01_15",true)
local function grid(x)
 if not grids[x]then
  local md,ground={},{}
  local obj={getX=function()return x end,getY=function()return 2 end,getZ=function()return 0 end,
   getModData=function()return md end,transmitModdata=function()end,
   getObjects=function()return list({floor,tableObj})end,
   getWorldObjects=function()return list(ground)end,
   AddWorldInventoryItem=function(_,item,ox,oy,oz)
    local o={getItem=function()return item end,x=ox,y=oy,z=oz}
    ground[#ground+1]=o
    return item
   end,
   transmitRemoveItemFromSquare=function(_,world)
    for i=#ground,1,-1 do
     if ground[i]==world then table.remove(ground,i);return 1 end
    end
    error("World object missing")
   end,ground=ground}
  grids[x]=obj
 end
 return grids[x]
end
getCell=function()return {getGridSquare=function(_,x,y,z)
 if y==2 and z==0 and (x==1 or x==2)then return grid(x)end
end}end
instanceof=function(obj,class)return obj and obj.class==class end
sendAddItemToContainer=function()end
instanceItem=function(ident)
 local md,pages={},{}
 return {getFullType=function()return ident end,getModData=function()return md end,
   setWorldZRotation=function(self,angle)self.angle=angle end,
   getPageToWrite=function()return 10 end,
   setCanBeWrite=function()end,canBeWrite=function()return true end,
   setNumberOfPages=function()end,getNumberOfPages=function()return 1 end,
   addPage=function(_,i,page)pages[i]=page end,
   seePage=function(_,i)return pages[i]end,setName=function()end,setCustomName=function()end}
end
SiegerStoryScenes={schema=1,world="story_test",scenes={},inspect={}}
dofile(runtime);events.started()
local function request(ch,scene,line)
 files["SiegerStoryLiveRequest.txt"]=table.concat({
 "v1",string.rep(ch,32),"story_test",scene,string.rep("f",64),"1"},"\t").."\n"..line.."\n"
 for i=1,120 do events.tick()end
 return files["SiegerStoryLiveResult.txt"]
end
local line=table.concat({"loot","table_bandage","1","2","0","ground","-1","-","-",
 "Base.Bandage=1","150","740","281","217","1","furniture_tables_01_15"},"\t")
local ack=request("a","new_table_scene",line)
assert(ack:find("\tcomplete\t1\t0\t0",1,true))
assert(#grid(1).ground==1)
local wo=grid(1).ground[1];local item=wo:getItem()
assert(wo.x==0.15 and wo.y==0.74 and math.abs(wo.z-27/96)<0.0001 and item.angle==217)
local token=item:getModData().SiegerStoryToken
assert(token=="SiegerStory:new_table_scene:table_bandage:1:1")
-- Explicit reloc moves existing tagged object, never creating a replacement.
local second=table.concat({"relocate","arrange_01","1","2","0","-","-1","-","-",
 token,"2","2","0","820","190","281","33","1","furniture_tables_01_15"},"\t")
local ack2=request("b","ops_arrange_token_one",second)
assert(ack2:find("\tcomplete\t1\t0\t0",1,true))
assert(#grid(1).ground==0 and #grid(2).ground==1)
assert(grid(2).ground[1]:getItem()==item)
assert(item.angle==33)
assert(files["SiegerStoryQuestEvents.txt"]:find("\tmove\tnew_table_scene\ttable_bandage\t",1,true))
local ledger=files["SiegerStoryQuestEvents.txt"]
dofile(runtime);events.started()
for i=1,130 do events.tick()end
assert(#grid(1).ground==0 and #grid(2).ground==1)
assert(files["SiegerStoryQuestEvents.txt"]==ledger)
-- A deliberately grouped pair of items must not occupy the exact same pixels.
-- Its token-derived layout is stable, never random on every reload.
local pair=table.concat({"loot","last_meal_pair","1","2","0","ground","-1","-","-",
 "Base.Bandage=2","490","500","281","100","1","furniture_tables_01_15"},"\t")
local ack3=request("c","curated_pair_scene",pair)
assert(ack3:find("\tcomplete\t1\t0\t0",1,true))
assert(#grid(1).ground==2)
local first,second=grid(1).ground[1],grid(1).ground[2]
assert(first.x~=second.x or first.y~=second.y,
       "Curated props overlapped at identical coordinates")
assert(math.abs(first.z-27/96)<0.0001 and math.abs(second.z-27/96)<0.0001)
assert(first:getItem().angle and second:getItem().angle)
print("PASS: table surface z, edge offset, item angle, same-token relocation and no replay")
