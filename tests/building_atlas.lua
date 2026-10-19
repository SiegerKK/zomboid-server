-- Lua 5.1 engine-shaped fixture for B42 SERVER chunk lookup (8 tiles).
-- Verifies staggered full coverage, complete framing, stop/replay/restart,
-- unusual building/room shapes and no idle scans.
local runtime=arg[1] or "story/runtime/SiegerAdminBuildingAtlas.lua"
local now=1792400000000
local files,callback={},nil
local metagridCalls=0
local chunkCalls=0
local maxCallsPerTick=0
local function list(a)
    return {size=function()return #a end,get=function(_,i)return a[i+1]end}
end
local function rect(x,y,x2,y2)
    return {getX=function()return x end,getY=function()return y end,
        getX2=function()return x2 end,getY2=function()return y2 end}
end
local function room(z,name,parts)
    return {getZ=function()return z end,getName=function()return name end,
        getRects=function()return list(parts)end}
end
local school=rect(100,200,120,220)
school.getIDString=function()return "school-01" end
school.getRooms=function()return list({
    room(0,"classroom",{rect(101,201,110,211),rect(108,209,117,217)}),
    room(1,"upper_floor",{rect(100,200,112,212)})
})end
local far=rect(200,300,220,330)
far.getRooms=function()return list({room(0,"far room",{rect(200,300,220,330)})})end
local near=rect(122,210,127,218)
near.getRooms=function()return list({room(0,"garage",{rect(123,210,126,217)})})end
local all=list({school,far,near})
getWorld=function()
    return {getMetaGrid=function()
        metagridCalls=metagridCalls+1
        return {getBuildings=function()return all end}
    end}
end
getCell=function()
    return {
        getChunk=function()error("Do not use client-only IsoCell.getChunk")end,
        getChunkForGridSquare=function(_,x,y,z)
            assert(x%8==0 and y%8==0 and z==0,
                "Chunk requests must use the 8-tile B42 grid world-square origin")
            chunkCalls=chunkCalls+1
            return x==96 and y==200 and {} or nil
        end
    }
end
getTimestampMs=function()return now end
isClient=function()return false end
SiegerStoryScenes={world="map_world"}
Events={OnTickEvenPaused={Add=function(fn)callback=fn end}}
getFileReader=function(name)
    local body=files[name]
    if not body then return nil end
    local index=1
    return {readLine=function()
        if index>#body then return nil end
        local n=body:find("\n",index,true)
        local value=body:sub(index,n and n-1 or #body)
        index=n and n+1 or #body+1
        return value
    end,close=function()end}
end
getFileWriter=function(name,create,append)
    local body=append and(files[name]or"")or""
    return {write=function(_,s)body=body..s end,close=function()files[name]=body end}
end
local function boot()dofile(runtime);assert(callback)end
boot()
local function tick(delta)
    now=now+(delta or 50)
    local before=chunkCalls
    callback()
    maxCallsPerTick=math.max(maxCallsPerTick,chunkCalls-before)
end
for i=1,120 do tick()end
assert(chunkCalls==0 and metagridCalls==0,"Idle must not scan world")
local function status()return files["SiegerAdminAtlasResult.txt"]or""end
local function log(id)return files["SiegerAdminAtlas-"..id..".txt"]or""end
local function request(letter,world,x0,y0,x1,y1,limit,expires)
    local id=string.rep(letter,32)
    files["SiegerAdminAtlasRequest.txt"]=table.concat({
        "v1",id,world,tostring(x0),tostring(y0),tostring(x1),tostring(y1),
        "0","1",tostring(limit or 50000),tostring(expires or now+30000),"end"
    },"\t").."\n"
    tick(1200)
    return id
end
local function drain()
    for i=1,250 do
        if status():find("\tcomplete\t",1,true) or status():find("\terror\t",1,true) then return end
        tick()
    end
    error("Atlas job never completed")
end
local id=request("a","map_world",100,200,130,230)
drain()
assert(status():find("\tcomplete\t2\t3\t4\t1\t7\t",1,true),status())
local first=log(id)
assert(first:find("v2\t"..id.."\tmap_world\t100\t200\t130\t230\t0\t1\tserver_loaded_chunks\t3\t8\n",1,true))
assert(first:find("\tb0\t100\t200\t120\t220\t",1,true))
assert(first:find("r\tb0\tb0_r0\t0\t101\t201\t110\t211\t",1,true))
assert(first:find("r\tb0\tb0_r0\t0\t108\t209\t117\t217\t",1,true))
assert(first:find("r\tb0\tb0_r1\t1\t100\t200\t112\t212\t",1,true))
assert(first:find("c\t12\t25\n",1,true),"ServerMap chunk at 96/8,200/8 missing")
assert(first:find("end\t7\t2\t3\t4\t1\t",1,true))
for line in first:gmatch("[^\n]+") do
    if line:sub(1,2)=="r\t" then
        local _,tabs=line:gsub("\t","")
        assert(tabs==8,"Room wire row must have nine columns: "..line)
    end
end
if arg[2]then
    local out=assert(io.open(arg[2],"wb"));out:write(first);out:close()
end
local scanned,probed=metagridCalls,chunkCalls
for i=1,30 do tick()end
assert(metagridCalls==scanned and chunkCalls==probed,"Idle did extra work")
request("a","map_world",100,200,130,230)
drain()
assert(log(id)==first and metagridCalls==scanned,"Repeated ID rescanned or overwrote")
request("b","wrong_world",100,200,130,230);drain()
assert(status():find("\terror\t",1,true) and metagridCalls==scanned)
request("c","map_world",100,200,130,230,50000,now-2000);drain()
assert(status():find("\terror\t",1,true) and metagridCalls==scanned)
local tiny=request("d","map_world",100,200,130,230,1);drain()
assert(status():find("\terror\t",1,true) and not log(tiny):find("\nend\t",1,true))
local empty=request("e","map_world",400,500,450,550);drain()
assert(status():find("\tcomplete\t0\t0\t0\t0\t",1,true))
-- Very large empty rectangle: no row-based cap may shortcut a scan.
local before=chunkCalls
local large=request("f","map_world",100,200,500,500)
assert(status():find("\trunning\t",1,true),"large scan must be stepped")
assert(chunkCalls-before<=256,"One frame used more than its work slice")
for i=1,4 do tick()end
assert(status():find("\trunning\t",1,true))
files["SiegerAdminAtlasStop.txt"]=large.."\n"
tick()
assert(status():find("\terror\t",1,true) and status():find("operator_stopped",1,true),
    "Stop must abort Atlas only")
assert(maxCallsPerTick<=256,"Unbounded chunk iteration inside one game tick")
files["SiegerAdminAtlasStop.txt"]=nil
local interruption=request("1","map_world",100,200,500,500)
assert(status():find("\trunning\t",1,true))
local snap=log(interruption)
boot()
tick(1200)
assert(status():find("runtime_interrupted",1,true),"Old in-progress scan must be interrupted")
assert(log(interruption)==snap,"Restart altered old partial data")
-- Server without chunk API: complete Atlas geometry with honest unknown coverage.
local originalGetCell=getCell
getCell=function()return {getChunk=function()error("Forbidden getChunk")end}end
local unknown=request("2","map_world",100,200,130,230);drain()
assert(status():find("\tcomplete\t",1,true))
assert(log(unknown):find("\tunknown\t3\t8\n",1,true))
getCell=originalGetCell
print("PASS: Atlas exact B42 8-tile ServerMap lookup, staged scanning, completeness, pause, stop, restart and unknown coverage")
