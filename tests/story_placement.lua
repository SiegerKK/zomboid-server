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
 if ident=="Base.HamRadio1" then
  return {
   getWorldObjectSprite=function()return "radio_stock_world_1"end,
   getDeviceData=function()
     return {getClone=function()
       local data={}
       function data:setIsPortable(v)self.portable=v end
       function data:setChannelRaw(v)self.chan=v end
       function data:setIsTurnedOn(v)self.powered=v end
       function data:setParent(v)self.parent=v end
       return data
     end}
   end}
 end
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
-- The historically wrong 0.65 must fail before creating any item.
local wrongHeight=table.concat({"loot","floating_bandage","1","2","0","ground","-1","-","-",
 "Base.Bandage=1","550","550","650","0","1","furniture_tables_01_15"},"\t")
local wrongAck=request("d","uncalibrated_height_scene",wrongHeight)
assert(wrongAck:find("\tfailed\t0\t0\t1",1,true),
       "Mismatched table height should fail closed")
assert(#grid(1).ground==2,"Invalid height spawned a floating item")
-- After a server reset Thomas's table must receive one real interactive
-- IsoRadio, never a dropped HamRadio1 item nor a converted old item.
local originalCell=getCell
local kitchenMD,kitchenWorld={},{}
local kitchenTable=furniture("IsoObject","furniture_tables_high_01_15",true)
kitchenTable.getSurfaceOffsetNoTable=function()return 32 end
local objects={floor,furniture("IsoObject","furniture_doorway_1",false),kitchenTable}
local kitchen={getX=function()return 10621 end,getY=function()return 9232 end,
 getZ=function()return 1 end,getModData=function()return kitchenMD end,
 transmitModdata=function()end,getObjects=function()return list(objects)end,
 getWorldObjects=function()return list(kitchenWorld)end,
 AddSpecialObject=function(_,radio)objects[#objects+1]=radio end}
getCell=function()return {getGridSquare=function(_,x,y,z)
 if x==10621 and y==9232 and z==1 then return kitchen end
 return originalCell():getGridSquare(x,y,z) end}end
IsoSpriteManager={instance={getSprite=function(_,name)
 assert(name=="radio_stock_world_1")
 return {getName=function()return name end}
end}}
local transmissions=0
IsoRadio={new=function(cell,square,sprite)
 assert(square==kitchen)
 local md={}
 return {class="IsoRadio",getModData=function()return md end,
  setDeviceData=function(self,data)self.deviceData=data end,
  setRenderYOffset=function(self,v)self.renderOffset=v end,
  transmitCompleteItemToClients=function() transmissions=transmissions+1 end,
  getSprite=function()return sprite end}
end}
ISMoveableSpriteProps={new=function(_)
 return {getTotalTableHeight=function(_,sq)assert(sq==kitchen);return 32 end}
end}
local furnitureWire=table.concat({
 "radio_furniture","thomas_kitchen_radio","10621","9232","1","furniture",
 "2","furniture_tables_high_01_15","IsoObject","Base.HamRadio1","101200","333"},"\t")
local outdatedFurniture=furnitureWire:gsub("\t333$","\t281")
local outdatedAck=request("g","smokeys_bar_03_upstairs",outdatedFurniture)
assert(outdatedAck:find("\tfailed\t0\t0\t1",1,true),"Old kitchen height must be rejected")
local badFurniture=furnitureWire:gsub("furniture_tables_high_01_15","unknown_table_radio")
local rejected=request("e","smokeys_bar_03_upstairs",badFurniture)
assert(rejected:find("\tfailed\t0\t0\t1",1,true))
assert(#objects==3 and #kitchenWorld==0 and transmissions==0)
local installed=request("f","smokeys_bar_03_upstairs",furnitureWire)
assert(installed:find("\tcomplete\t1\t0\t0",1,true))
assert(#objects==4 and objects[4].class=="IsoRadio")
assert(objects[4].deviceData.chan==101200 and objects[4].deviceData.portable==false)
assert(objects[4].renderOffset==32 and transmissions==1)
assert(#kitchenWorld==0,"Must not create a dropped HamRadio1 alongside the IsoRadio")
assert(files["SiegerStoryQuestEvents.txt"]:find("\tspawn\tsmokeys_bar_03_upstairs\tthomas_kitchen_radio\t",1,true))
local previous=files["SiegerStoryQuestEvents.txt"]
dofile(runtime);events.started()
for i=1,130 do events.tick()end
assert(#objects==4 and transmissions==1 and files["SiegerStoryQuestEvents.txt"]==previous,
       "Installed radio repeated after Lua reload")
print("PASS: table surface z, edge offset, item angle, same-token relocation and no replay")
