-- Lua 5.1 behavioral harness for the read-only area scan (no real game data).
local runtime = arg[1] or "story/runtime/SiegerStoryAreaScan.lua"
-- PZ Kahlua exposes pairs but not the Lua 5.1 global next.
next=nil
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
    getName=function() return _unicodeBandage or "Бинт" end,
    getUnequippedWeight=function()return 0.1 end
}
local note={
    getFullType=function() return "Base.Note" end,
    getName=function() return _unicodeNote or 'Дневник "Медик"' end
}
local food={getFullType=function()return "Base.CannedBeans"end,
    getName=function()return "Beans"end,
    getCalories=function()return 360 end}
local fluid={getAmount=function()return 0.5 end,
    getCapacity=function()return 1.0 end,
    isMixture=function()return false end,
    getPrimaryFluid=function()return {getFluidTypeString=function()
        return "Water"end}end}
local bottle={getFullType=function()return "Base.WaterBottle"end,
    getName=function()return "Water bottle"end,
    getFluidContainer=function()return fluid end}
local items=list({bandage,note,food,bottle})
local container={
    getType=function() return "medicine" end,
    getItems=function() return items end,
    getCapacity=function()return 50 end,
    getCapacityWeight=function()return 2.5 end,
    getFreeCapacity=function(_,chr)assert(chr==nil);return 47.5 end
}
local furniture={
    getClass=function() return {getSimpleName=function() return "IsoObject" end} end,
    getSprite=function() return {getName=function() return "furniture_medical_01_1" end} end,
    getContainerCount=function() return 1 end,
    getContainerByIndex=function(_,i) if i==0 then return container end end
}
instanceof=function(obj,cls) return (obj==furniture and cls=="IsoObject")
    or (obj==food and cls=="Food") end
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
local vehicles={}
local function vehicleSet()
    return {iterator=function()
        local i=0
        return {hasNext=function()return i<#vehicles end,
                next=function()i=i+1;return vehicles[i]end}
    end}
end
getCell=function()
    return {getGridSquare=function(self,x,y,z)
        mapCalls=mapCalls+1
        if x==1000 and y==2000 and z==0 then return sq end
        return nil
    end,getVehicles=function()return vehicleSet()end}
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
assert(data:find('"food_calories":360',1,true),'Food energy not observed')
assert(data:find('"fluid_amount_l":0.5',1,true),'B42 fluid contents not observed')
assert(data:find('"fluid_capacity_l":1',1,true))
assert(data:find('"fluid_type":"Water"',1,true))
assert(data:find('"fluid_mixed":false',1,true))
assert(data:find('"sprite":"furniture_medical_01_1"',1,true))
assert(data:find('"object_index":0',1,true))
assert(data:find('"container_index":0',1,true))
assert(data:find('"capacity":50',1,true))
assert(data:find('"capacity_weight":2.5',1,true))
assert(data:find('"free_capacity":47.5',1,true))
assert(data:find('"unequipped_weight":0.1',1,true))
assert(data:find('"center_x":1000',1,true))
assert(data:find('"min_z":-2',1,true))
assert(not data:find("C:\\",1,true))
local count=0
for line in data:gmatch("[^\n]+") do count=count+1 end
assert(count==9,"Unexpected count of meta/object/container/4 items/ground/summary: "..count)
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
end,getVehicles=function()return vehicleSet()end} end
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
-- Vehicle inventory, window damage state and floor blood metadata in v2 only.
local gloveItems=list({note})
local glovebox={getType=function()return "GloveBox"end,getItems=function()return gloveItems end}
local part1={getId=function()return "Battery"end,getCondition=function()return 35 end,
    getInventoryItem=function()return bandage end,getItemContainer=function()return nil end}
local part2={getId=function()return "GloveBox"end,getCondition=function()return 75 end,
    getInventoryItem=function()return nil end,getItemContainer=function()return glovebox end}
local car={getX=function()return 1001.75 end,getY=function()return 2000.5 end,
    getZ=function()return 0 end,getId=function()return 42 end,
    getScriptName=function()return "Base.Van"end,getPartCount=function()return 2 end,
    getPartByIndex=function(_,i)return i==0 and part1 or part2 end}
local farCar={getX=function()return 19999 end,getY=function()return 19999 end,
    getZ=function()return 0 end,getId=function()return 900 end,
    getScriptName=function()return "Base.Sedan"end,getPartCount=function()return 0 end}
vehicles={car,farCar}
local window={getSprite=function()return {getName=function()return "fixtures_windows_01_10" end}end,
    getContainerCount=function()return 0 end,
    isSmashed=function()return true end,
    isGlassRemoved=function()return false end,IsOpen=function()return false end,
    getBarricadeOnSameSquare=function()return {} end,
    getBarricadeOnOppositeSquare=function()return nil end,
    getNorth=function()return true end,
    getModData=function()return {SiegerAdminConstructionTag="refuge:shelter:window"}end}
local savedInstanceof=instanceof
instanceof=function(obj,cls)
    if obj==window then return cls=="IsoWindow"end
    return savedInstanceof(obj,cls)
end
sq.getObjects=function()return list({furniture,window})end
sq.haveBloodFloor=function()return true end
sq.haveBloodWall=function()return false end
files[req]="v2\t"..string.rep("8",32).."\tkyrylo\t51\t5\n"
for n=1,7000 do updates() end
local snapshot=files[response]
assert(snapshot:find('"kind":"vehicle"',1,true),'Missing vehicle row')
assert(snapshot:find('"vehicle_id":42',1,true))
assert(snapshot:find('"script":"Base.Van"',1,true))
assert(snapshot:find('"kind":"vehicle_part"',1,true))
assert(snapshot:find('"part_id":"GloveBox"',1,true))
assert(snapshot:find('"kind":"vehicle_container"',1,true))
assert(snapshot:find('"kind":"vehicle_item"',1,true))
assert(snapshot:find('"full_type":"Base.Note"',1,true))
assert(snapshot:find('"vehicles":1',1,true),'Out-of-window vehicle leaked')
assert(snapshot:find('"vehicle_parts":2',1,true))
assert(snapshot:find('"vehicle_containers":1',1,true))
assert(snapshot:find('"vehicle_items":1',1,true))
assert(snapshot:find('"vehicle_snapshot":"complete"',1,true))
assert(snapshot:find('"construction_tag":"refuge:shelter:window"',1,true))
assert(snapshot:find('"face":"N"',1,true))
assert(snapshot:find('"window_smashed":true',1,true))
assert(snapshot:find('"window_barricaded_same":true',1,true))
assert(snapshot:find('"blood_floor":true',1,true))
assert(snapshot:find('"status":"complete"',1,true))
history("PASS: bounded loaded vehicles and glovebox, window state and blood-floor survey")
history("PASS: v1 25x25x5 and v2 51/101 x5 bounded surveys; explicit loaded/nil coverage")

-- v3 arbitrary radius, explicit floors, allowlisted record categories.
local v3id=string.rep("3",32)
files[req]=table.concat({"v3",v3id,"kyrylo","1000","2000","3","0","1",
    "squares,objects,containers,items,ground,vehicles,windows,blood"},"\t").."\n"
for n=1,450 do updates() end
local v3=files[response]
assert(v3:find('"requested_squares":98',1,true))
assert(v3:find('"side":7',1,true))
assert(v3:find('"levels":2',1,true))
assert(v3:find('"center_x":1000',1,true))
assert(v3:find('"min_z":0',1,true))
assert(v3:find('"max_z":1',1,true))
assert(v3:find('"vehicle_snapshot":"complete"',1,true))
assert(v3:find('"window_smashed":true',1,true))
assert(v3:find('"blood_floor":true',1,true))
-- Selective run skips cars and window state; no need to rewrite mod code.
local lightid=string.rep("4",32)
files[req]=table.concat({"v3",lightid,"kyrylo","-","-","2","0","0",
    "squares,objects"},"\t").."\n"
for n=1,320 do updates() end
local light=files[response]
assert(light:find('"requested_squares":25',1,true))
assert(light:find('"vehicle_snapshot":"not_requested"',1,true))
assert(not light:find('"kind":"vehicle"',1,true))
assert(not light:find('"window_smashed"',1,true))
local farId=string.rep("5",32)
files[req]=table.concat({"v3",farId,"kyrylo","11000","2000","2","0","0",
    "squares"},"\t").."\n"
for n=1,150 do updates() end
assert(files[response]:find("center_far_from_online_player",1,true))
assert(files[response]:find('"status":"error"',1,true))
history("PASS: v3 dynamic center/radius/floors/selective categories and far-centre refusal")

-- Both property-table APIs are read-only. A sprite name alone is not bed proof.
local bed={getSprite=function()return {getName=function()return "bed_head"end}end,
    getProperties=function()return {Val=function(_,k)
        if k=="BedType" then return "averageBed"end end}end,
    getModData=function()return {SiegerAdminConstructionTag="refuge:beds:head"}end,
    getContainerCount=function()return 0 end}
local bedInstanceof=instanceof
instanceof=function(o,c)return (o==bed and c=="IsoObject") or bedInstanceof(o,c)end
sq.getObjects=function()return list({bed})end
for i=1,2 do
    if i==2 then bed.getProperties=function()return {get=function(_,k)
        if k=="BedType" then return "averageBed"end end}end end
    files[req]=table.concat({"v3",string.rep(i==1 and "6" or "7",32),"kyrylo",
        "1000","2000","2","0","0","squares,objects"},"\t").."\n"
    for n=1,320 do updates()end
    assert(files[response]:find('"bed_type":"averageBed"',1,true))
    assert(files[response]:find('"construction_tag":"refuge:beds:head"',1,true))
    assert(files[response]:find('"errors":0',1,true))
end
history("PASS: native bed property attestation without sprite mutation")
