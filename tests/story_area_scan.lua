-- Lua 5.1 behavioral harness for the read-only area scan (no real game data).
local runtime = arg[1] or "story/runtime/SiegerStoryAreaScan.lua"
local req = "SiegerStoryScanRequest.txt"
local response = "SiegerStoryScanResult.txt"
local requestId = string.rep("a",32)
local files = {[req]="v1\t"..requestId.."\tkyrylo\t25\t5\n"}
local updates = nil
local logs = {}
Events={OnTick={Add=function(fn) updates=fn end}}
isClient=function() return false end
getFileReader=function(filename,flag)
    local contents=files[filename]
    if contents==nil then return nil end
    local lines={}
    for line in string.gmatch(contents,"([^\n]+)") do
        lines[#lines+1]=line
    end
    local i=0
    return {
        readLine=function() i=i+1;return lines[i] end,
        close=function() end
    }
end
getFileWriter=function(filename,create,append)
    assert(filename:match('%.txt$'),'Pinned B42 rejects .jsonl output')
    if not append then files[filename]="" end
    -- Model streaming IO without quadratic copies in the 101-cell harness.
    local chunks={}
    if append and files[filename] then chunks[1]=files[filename] end
    local writer={
        write=function(self,str) chunks[#chunks+1]=str end,
        close=function() files[filename]=table.concat(chunks) end
    }
    return writer
end
local history=print
print=function(...)
    logs[#logs+1]=table.concat({...}," ")
end
local function list(items)
    return {size=function() return #items end,get=function(self,i) return items[i+1] end}
end
local bandage={
    getFullType=function() return "Base.Bandage" end,
    getName=function() return _unicodeBandage or "Бинт" end
}
local note={
    getFullType=function() return "Base.Note" end,
    getName=function() return _unicodeNote or 'Дневник "Медик"' end
}
local items=list({bandage,note})
local container={
    getType=function() return "medicine" end,
    getItems=function() return items end
}
local furniture={
    getClass=function() return {getSimpleName=function() return "IsoObject" end} end,
    getSprite=function() return {getName=function() return "furniture_medical_01_1" end} end,
    getContainerCount=function() return 1 end,
    getContainerByIndex=function(_,i) if i==0 then return container end end
}
instanceof=function(obj,cls) return obj==furniture and cls=="IsoObject" end
local groundItem={
    getFullType=function() return "Base.Disinfectant" end,
    getName=function() return "Disinfectant" end
}
local ground={getItem=function() return groundItem end}
local sq={
    getObjects=function() return list({furniture}) end,
    getRoom=function() return {getName=function() return "edclinic" end} end,
    getWorldObjects=function() return list({ground}) end,
    getStaticMovingObjects=function() return list({}) end
}
local mapCalls=0
getCell=function()
    return {getGridSquare=function(self,x,y,z)
        mapCalls=mapCalls+1
        if x==1000 and y==2000 and z==0 then return sq end
        return nil
    end}
end
local player={
    getUsername=function() return "kyrylo" end,
    getX=function() return 1000.5 end,
    getY=function() return 2000.7 end,
    getZ=function() return 0 end
}
getOnlinePlayers=function() return list({player}) end
dofile(runtime)
assert(type(updates)=="function")
for n=1,320 do updates() end
local data=files[response]
_firstScanData=data -- optional export by the exact-game VM harness
assert(data and #data>200,"No response file produced")
assert(data:find('"kind":"meta"',1,true))
assert(data:find('"kind":"summary"',1,true))
assert(data:find('"requested_squares":3125',1,true))
assert(data:find('"loaded_squares":1',1,true))
assert(data:find('"unloaded_squares":3124',1,true))
assert(data:find('"full_type":"Base.Bandage"',1,true))
assert(data:find('"name":"'..(_unicodeBandage or 'Бинт')..'"',1,true),'Unicode inventory name changed')
assert(data:find('"full_type":"Base.Note"',1,true))
assert(data:find('"full_type":"Base.Disinfectant"',1,true))
assert(data:find('"sprite":"furniture_medical_01_1"',1,true))
assert(data:find('"object_index":0',1,true))
assert(data:find('"container_index":0',1,true))
assert(data:find('"center_x":1000',1,true))
assert(data:find('"min_z":-2',1,true))
assert(not data:find("C:\\",1,true))
local count=0
for line in data:gmatch("[^\n]+") do count=count+1 end
assert(count==7,"Unexpected count of meta/object/container/2 items/ground/summary: "..count)
-- Polling the same request must never schedule a second scan.
local previous=#files[response]
for n=1,150 do updates() end
assert(#files[response]==previous and mapCalls==3125)
-- A new VM/runtime must not replay and overwrite the completed request.
dofile(runtime)
for n=1,130 do updates() end
assert(#files[response]==previous and mapCalls==3125,'Completed request replayed after reload')
-- If an explicitly requested username isn't online, report rather than scan.
files[req]="v1\t"..string.rep("b",32).."\tother_player\t25\t5\n"
for n=1,130 do updates() end
assert(files[response]:find('"reason":"player_not_online"',1,true))
assert(files[response]:find('"status":"error"',1,true))
-- Dense inventories cannot monopolise a tick; all items eventually appear.
local reads=0
local heavyItem={getFullType=function() return 'Base.Bandage' end,
    getName=function() reads=reads+1;return 'Bandage' end}
local dense={}
for i=1,1000 do dense[i]=heavyItem end
items=list(dense)
files[req]='v1\t'..string.rep('c',32)..'\tkyrylo\t25\t5\n'
for n=1,500 do
    reads=0;updates();assert(reads<=200,'Unbounded inventory work in one tick')
end
assert(files[response]:find('"container_items":1000',1,true))
assert(files[response]:find('"status":"complete"',1,true))
-- Long item names must not be silently clipped in an allegedly full report.
items=list({{getFullType=function() return 'Base.Note' end,
    getName=function() return string.rep('x',513) end}})
files[req]='v1\t'..string.rep('d',32)..'\tkyrylo\t25\t5\n'
for n=1,500 do updates() end
assert(files[response]:find('"truncated":true',1,true))
assert(files[response]:find('"status":"partial"',1,true))
-- Kahlua may hide Object.getClass(); use a verified instanceof fallback.
items=list({bandage})
local classCalls=0
furniture.getClass=function() classCalls=classCalls+1;error('getSimpleName hidden') end
instanceof=function(obj,cls) return obj==furniture and cls=='IsoObject' end
files[req]='v1\t'..string.rep('e',32)..'\tkyrylo\t25\t5\n'
for n=1,500 do updates() end
assert(files[response]:find('"class":"IsoObject"',1,true))
assert(files[response]:find('"errors":0',1,true))
assert(classCalls==0,'Hidden Java reflection API must never be called')
-- Getter failures must be visible, rather than silently treated as full data.
container.getType=function() error('synthetic getter failure') end
files[req]='v1\t'..string.rep('f',32)..'\tkyrylo\t25\t5\n'
for n=1,500 do updates() end
assert(files[response]:find('"status":"partial"',1,true))
assert(files[response]:find('"errors":1',1,true))
-- One tagged zombie appearing in multiple visited squares must be emitted once.
local oldCell=getCell
local zmd={SiegerStoryToken="SiegerStory:scan_test:guard_one:1",SiegerStoryQuest="scan_test",
    SiegerStoryAction="guard_one",SiegerStoryKind="infected"}
local walking={getModData=function()return zmd end,getX=function()return 1000 end,
    getY=function()return 2000 end,getZ=function()return 0 end,getOnlineID=function()return 17 end}
local oldInstanceof=instanceof
instanceof=function(obj,cls) return (obj==walking and cls=="IsoZombie") or oldInstanceof(obj,cls) end
sq.getMovingObjects=function() return list({walking}) end
getCell=function() return {getGridSquare=function(_,x,y,z)
    if z==0 and y==2000 and (x==1000 or x==1001) then return sq end
end} end
container.getType=function() return "medicine" end
files[req]='v1\t'..string.rep('9',32)..'\tkyrylo\t25\t5\n'
for n=1,500 do updates() end
local _,found=files[response]:gsub('"kind":"quest_zombie"','')
assert(found==1 and files[response]:find('"quest_zombies":1',1,true),'Moving quest zombie duplicated')
sq.getMovingObjects=nil;getCell=oldCell;instanceof=oldInstanceof
-- v2 bounded area survey: explicit square rows and both new sizes.
container.getType=function() return "medicine" end
for _,side in ipairs({51,101}) do
    items=list({bandage})
    local id=side==51 and string.rep("1",32) or string.rep("2",32)
    files[req]="v2\t"..id.."\tkyrylo\t"..side.."\t5\n"
    for n=1,side*side do updates() end
    local survey=files[response]
    local expected=side*side*5
    assert(survey:find('"requested_squares":'..expected,1,true),'wrong v2 volume')
    assert(survey:find('"scanned_squares":'..expected,1,true),'unfinished v2 area')
    assert(survey:find('"kind":"square"',1,true),'missing coverage rows')
    assert(survey:find('"loaded":false',1,true),'missing nil-cell indicator')
    assert(survey:find('"loaded":true',1,true),'missing loaded-cell indicator')
    assert(survey:find('"status":"complete"',1,true),'incomplete v2 survey')
    assert(survey:find('"truncated":false',1,true),'unexpected report truncation')
end
history("PASS: v1 25x25x5 and v2 51/101 x5 bounded surveys; explicit loaded/nil coverage")
