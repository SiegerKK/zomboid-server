-- Behavioral harness: one-at-a-time vanilla zombies, persistent tags,
-- death event ledger, and server-side idempotency. Not a multiplayer proof.
local runtime=arg[1] or "story/runtime/SiegerStoryDirector.lua"
local events,files,created={},{},{}
local squares={}
Events={
 OnServerStarted={Add=function(fn)events.started=fn end},
 OnTick={Add=function(fn)events.tick=fn end},
 OnZombieDead={Add=function(fn)events.dead=fn end},
 LoadGridsquare={Add=function(fn)events.load=fn end}
}
isClient=function() return false end
local function list(values)
 return {size=function()return #values end,get=function(_,i)return values[i+1] end}
end
getFileReader=function(name)
 if not files[name] then return nil end
 local lines={}
 for value in files[name]:gmatch("[^\n]+") do table.insert(lines,value) end
 local i=0
 return {readLine=function() i=i+1;return lines[i] end,close=function()end}
end
getFileWriter=function(name,create,append)
 if not append then files[name]="" end
 return {write=function(_,value) files[name]=(files[name] or "")..value end,
         close=function()end}
end
instanceof=function(v,cls) return v.class==cls end
sendAddItemToContainer=function()end
instanceItem=function(id)
 local md,content={},{}
 return {getModData=function()return md end,
         setCanBeWrite=function()end,canBeWrite=function()return true end,
         setNumberOfPages=function()end,getNumberOfPages=function()return 1 end,
         addPage=function(_,i,page) content[i]=page end,seePage=function(_,i)return content[i] end,
         getPageToWrite=function()return id=="Base.Notebook" and 10 or 1 end,
         setName=function()end,setCustomName=function()end}
end
local containerItems={}
local container={getItems=function()return list(containerItems)end,
                 AddItem=function(_,item)table.insert(containerItems,item);return item end}
local furniture={class="IsoObject",getSprite=function()return {getName=function()return "valid_cabinet" end} end,
 getContainer=function()return container end}
local function square(x,y,z)
 local key=x..","..y..","..z
 if not squares[key] then
   local md={}
   squares[key]={
    getX=function()return x end,getY=function()return y end,getZ=function()return z end,
    getModData=function()return md end,transmitModdata=function()end,
    getObjects=function()return list({furniture})end,getWorldObjects=function()return list({})end,
    AddWorldInventoryItem=function(_,obj)return obj end
   }
 end
 return squares[key]
end
getCell=function()return {getGridSquare=function(_,x,y,z)
 if x==1 and y==2 and z==0 then return square(x,y,z)end
end} end
addZombiesInOutfit=function(x,y,z,count,outfit,female)
 assert(x==1 and y==2 and z==0 and count==1 and outfit==nil and female==nil)
 local md={}
 local zombie={class="IsoZombie",getModData=function()return md end,
     getX=function()return x+0.5 end,getY=function()return y+0.5 end,
     getZ=function()return z end,getOnlineID=function()return 97 end}
 created[#created+1]=zombie
 return list({zombie})
end
SiegerStoryScenes={schema=1,world="story_test",scenes={},inspect={}}
dofile(runtime);events.started()
local ident=string.rep("a",32)
local line=table.concat({"infected","morgue_guard_a","1","2","0","-","-1","-","-","vanilla","1"},"\t")
files["SiegerStoryLiveRequest.txt"]=
 table.concat({"v1",ident,"story_test","clinic_quest_001",string.rep("f",64),"1"},"\t")
 .."\n"..line.."\n"
for _=1,120 do events.tick() end
assert(#created==1)
local md=created[1]:getModData()
assert(md.SiegerStoryQuest=="clinic_quest_001")
assert(md.SiegerStoryAction=="morgue_guard_a")
assert(md.SiegerStoryKind=="infected")
assert(md.SiegerStoryToken=="SiegerStory:clinic_quest_001:morgue_guard_a:1")
assert((files["SiegerStoryQuestEvents.txt"] or ""):find("\tspawn\tclinic_quest_001\tmorgue_guard_a\t",1,true))
assert(files["SiegerStoryLiveResult.txt"]:find("\tcomplete\t1\t0\t0",1,true))
-- Replay after server code restart must not spawn a second zombie.
dofile(runtime);events.started()
for _=1,120 do events.tick() end
assert(#created==1)
assert(files["SiegerStoryLiveResult.txt"]:find("morgue_guard_a\talready",1,true))
events.dead(created[1])
assert(files["SiegerStoryQuestEvents.txt"]:find("\tdead\tclinic_quest_001\tmorgue_guard_a\t",1,true))
local once=files["SiegerStoryQuestEvents.txt"]
events.dead(created[1])
assert(files["SiegerStoryQuestEvents.txt"]==once,"Death must not be recorded twice")
-- A prohibited infected subtype may never spawn another zombie.
files["SiegerStoryLiveRequest.txt"]=
 table.concat({"v1",string.rep("b",32),"story_test","clinic_quest_002",string.rep("f",64),"1"},"\t")
 .."\n"..line:gsub("vanilla","TLOU_Clicker").."\n"
for _=1,120 do events.tick() end
assert(#created==1)
print("PASS: vanilla live spawn, quest tags, journal, death marker, replay and subtype refusal")
