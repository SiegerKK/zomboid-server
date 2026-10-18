-- Lua 5.1 server fixture: TLOU diagnostics must scan the ENTIRE loaded
-- collection on demand, including positions beyond arbitrary sample limits.
local files,callback={},nil
local function reader(body)
    local start=1
    return {readLine=function()
        if start>#body then return nil end
        local stop=body:find("\n",start,true)
        if not stop then local s=body:sub(start);start=#body+1;return s end
        local s=body:sub(start,stop-1);start=stop+1;return s
    end,close=function()end}
end
getFileReader=function(path) return files[path] and reader(files[path]) or nil end
getFileWriter=function(path)
    local rows={}
    return {write=function(_,s)rows[#rows+1]=s end,
            close=function()files[path]=table.concat(rows)end}
end
local zombies={}
local INITIALIZED=1300
local queries=0
for i=1,INITIALIZED do
    local persistent=i==INITIALIZED and 0 or i
    local z={
        getPersistentOutfitID=function()return persistent end,
        dressInRandomOutfit=function()error("diagnostics must never dress an entity") end,
        getHealth=function()return 80 end,
        isMoving=function()return i%2==0 end,
        getTarget=function()return i%3==0 and true or nil end
    }
    zombies[#zombies+1]=z
end
local list={size=function()queries=queries+1;return #zombies end,
            get=function(_,i)return zombies[i+1]end}
getCell=function()return {getZombieList=function()return list end}end
local types={"TLOU_Runner","TLOU_Stalker","TLOU_Clicker","TLOU_Bloater"}
local tableTypes={}
for _,key in ipairs(types) do
    tableTypes[key]={chance=250,HP=100,onTick={function()end}}
end
ZomboidForge={ZTypes=tableTypes,
    GetZType=function(z)
        local id=z:getPersistentOutfitID()
        assert(id~=0)
        return types[(id-1)%4+1]
    end}
SandboxVars={TLOU_infected={
    VanillaSpawn=false,RunnerSpawnWeight=560,StalkerSpawnWeight=330,
    ClickerSpawnWeight=110,BloaterSpawn=false,HideIndoors=true,
    OnlyUnexplored=true,WanderAtNight=false}}
SiegerStoryScenes={world="story_test"}
isClient=function()return false end
Events={OnTick={Add=function(fn)callback=fn end}}
dofile(arg[1] or "story/runtime/SiegerStoryTLOUDiagnostics.lua")
assert(callback)
local function tick(n)
    for _=1,n do callback() end
end
tick(360)
assert(queries==0,"Idle diagnostics must never enumerate zombies")
local function request(rid,mode)
    files["SiegerStoryTLOURequest.txt"]="v2\t"..rid.."\tstory_test\t"..mode.."\n"
    tick(180)
    return files["SiegerStoryTLOUResult.txt"]
end
local a=string.rep("a",32)
local out=request(a,"registry")
assert(out:find("\tregistry\tcomplete\tserver_registry\t13\n",1,true))
assert(queries==0,"Registry request must not iterate zombies")
local b=string.rep("b",32)
out=request(b,"census")
assert(out:find("\tcensus\tcomplete\tcomplete_loaded_census\t20\n",1,true))
assert(out:find("census\t1300\t1300\t0\t0\t1\t-\tloaded_list_only",1,true))
assert(out:find("observed\tunknown\t1",1,true),"Uninitialized outfit counted honestly")
assert(out:find("observed\tTLOU_Runner\t325\t325\t80.00",1,true),
       "Must classify all 1300 zombies, not first 512")
assert(queries==1,"Exactly one traversal per full census")
tick(360)
assert(queries==1,"No background repeats")
local c=string.rep("c",32)
SiegerStoryScenes.world="road_home"
out=request(c,"census")
assert(out:find("\tcensus\terror\treview_server_logs\t0\n",1,true))
assert(queries==1,"World mismatch must not touch zombies")
print("PASS: complete 1300/1300 TLOU census, registry-only, no idle scans, no outfit mutations")
