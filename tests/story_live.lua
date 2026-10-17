-- Lua 5.1 behavioral harness for live note/loot queue in Story Director.
-- Stub methods model base 42 runtime; not equivalent to two-client game test.
local runtime=arg[1] or "story/runtime/SiegerStoryDirector.lua"
-- Match pinned Kahlua: periodic work must not require the Lua next() global.
next=nil
local events={}
Events={
    LoadGridsquare={Add=function(f) events.load=f end},
    OnServerStarted={Add=function(f) events.started=f end},
    OnTick={Add=function(f) events.tick=f end}
}
isClient=function() return false end
local files={}
local function linesOf(str)
    local t={}
    for line in string.gmatch(str,"([^\n]+)") do t[#t+1]=line end
    return t
end
getFileReader=function(filename,unused)
    if not files[filename] then return nil end
    local data=linesOf(files[filename]);local i=0
    return {readLine=function() i=i+1;return data[i] end,close=function()end}
end
getFileWriter=function(filename,make,append)
    if not append or files[filename]==nil then files[filename]="" end
    return {write=function(_,str)files[filename]=files[filename]..str end,
            close=function()end}
end
local made={},{}
local gameItems={}
local function list(t)
    return {size=function() return #t end,get=function(_,i)return t[i+1] end}
end
sendAddItemToContainer=function() end
instanceof=function(obj,cls) return obj.class==cls end
instanceItem=function(kind)
    local md,pages={},{}
    local item={kind=kind,md=md,pages=pages,pageToWrite=kind=="Base.Notebook" and 10 or 1}
    function item:getModData() return self.md end
    function item:getFullType() return self.kind end
    function item:setCustomName(v) self.customName=v end
    function item:setName(s) self.name=s end
    function item:canBeWrite() return self.writable end
    function item:setCanBeWrite(v)self.writable=v end
    function item:setNumberOfPages(v)self.count=v end
    function item:getNumberOfPages()return self.count end
    function item:setPageToWrite(v) error("Do not depend on nonserialized PageToWrite override") end
    function item:getPageToWrite() return self.pageToWrite or 1 end
    function item:addPage(i,v)self.pages[i]=v end
    function item:seePage(i)return self.pages[i] end
    return item
end
local container={
    getItems=function()return list(gameItems)end,
    AddItem=function(_,obj)table.insert(gameItems,obj);return obj end,
    getType=function()return "filingcabinet"end
}
local object={class="IsoObject",getContainer=function()return container end,
    getSprite=function()return {getName=function() return "furniture_medical_01_0"end}end}
local metadata={}
local ground={}
local loaded2=false
local function square(x,y,z)
    local md=metadata[tostring(x)..":"..tostring(y)..":"..tostring(z)]
    if not md then md={};metadata[tostring(x)..":"..tostring(y)..":"..tostring(z)]=md end
    return {
        getX=function()return x end,getY=function()return y end,getZ=function()return z end,
        getModData=function()return md end,transmitModdata=function()end,
        getObjects=function()return list({object})end,
        getWorldObjects=function()return list(ground)end,
        getRoom=function()return nil end,
        AddWorldInventoryItem=function(_,item)table.insert(ground,{getItem=function()return item end});return item end
    }
end
getCell=function()return {getGridSquare=function(_,x,y,z)
    if x==1 and y==2 and z==0 then return square(x,y,z)end
    if x==1 and y==3 and z==0 and loaded2 then return square(x,y,z)end
    return nil
end} end
SiegerStoryScenes={schema=1,world="story_test",scenes={},inspect={}}
local function hx(value)
    local t={}
    for i=1,#value do t[#t+1]=string.format("%02x",value:byte(i))end
    return table.concat(t)
end
local function request(id,scene,rows)
    files["SiegerStoryLiveRequest.txt"]=table.concat(
       {"v1",id,"story_test",scene,string.rep("f",64),tostring(#rows)},"\t")
       .."\n"..table.concat(rows,"\n").."\n"
end
local note=table.concat({"note","diary_one","1","2","0","ground","-1","-","-",
    (_liveHex0 or hx('Доктор "Миллер"')),"2",(_liveHex1 or hx("Страница первая"))..":"..(_liveHex2 or hx("Страница вторая"))},"\t")
local loot=table.concat({"loot","loot_one","1","2","0","container","0",
    "furniture_medical_01_0","IsoObject","Base.Bandage=2;Base.Disinfectant=1"},"\t")
local another=table.concat({"note","deferred_one","1","3","0","ground","-1","-","-",
    (_liveHex3 or hx("Письмо")),"1",(_liveHex4 or hx("Пусть дождь закончится"))},"\t")
dofile(runtime)
assert(events.tick and events.started)
events.started()
request(string.rep("a",32),"clinic_live_001",{note,loot,another})
for i=1,120 do events.tick() end
local response=files["SiegerStoryLiveResult.txt"]
assert(response and response:find("end\t"..string.rep("a",32).."\tpending\t2\t1\t0",1,true))
assert(response:find("action\tdiary_one\tapplied\t",1,true))
assert(response:find("action\tloot_one\tapplied\t",1,true))
assert(#gameItems==3 and #ground==1)
assert(files["SiegerStoryQuestEvents.txt"]:find("\tspawn\tclinic_live_001\tdiary_one\t",1,true))
if _liveTitle then assert(ground[1]:getItem().name==_liveTitle,"UTF-8 title corrupted") end
assert(ground[1]:getItem().pages[2]==(_livePage or "Страница вторая"))
assert(ground[1]:getItem().kind=="Base.Notebook" and ground[1]:getItem().customName==true)
assert(ground[1]:getItem():getPageToWrite()==10,"Journal UI cannot navigate authored pages")
for i=1,120 do events.tick() end
assert(#gameItems==3 and #ground==1,"Pending job must not duplicate applied items")
loaded2=true
for i=1,120 do events.tick() end
response=files["SiegerStoryLiveResult.txt"]
assert(response:find("end\t"..string.rep("a",32).."\tcomplete\t3\t0\t0",1,true))
assert(#gameItems==3 and #ground==2)

-- Same request after a full Lua restart: persisted square flags prevent duplicates.
dofile(runtime);events.started()
for i=1,120 do events.tick()end
response=files["SiegerStoryLiveResult.txt"]
assert(response:find("action\tdiary_one\talready",1,true))
assert(response:find("action\tloot_one\talready",1,true))
assert(response:find("\tcomplete\t3\t0\t0",1,true))
assert(#gameItems==3 and #ground==2)

-- Invalid selector must report a terminal failure, NEVER success.
local wrong=table.concat({"loot","bad_object","1","2","0","container","0",
    "totally_wrong_sprite","IsoObject","Base.Bandage=1"},"\t")
request(string.rep("b",32),"other_clinic_001",{wrong})
for i=1,120 do events.tick() end
response=files["SiegerStoryLiveResult.txt"]
assert(response:find("\tfailed\t0\t0\t1",1,true))
assert(response:find("action\tbad_object\terror\t",1,true))
assert(#gameItems==3)
local logs=0
for _,v in ipairs({})do logs=logs+1 end
print("PASS: live queue note/loot/deferred square, per-action receipts, restart idempotence, selector rejection")
