-- Lua 5.1 engine-shaped fixture: arbitrary Story world, metagrid geometry,
-- accurate per-room rectangles, chunk presence and zero idle world scans.
local runtime=arg[1] or "story/runtime/SiegerAdminBuildingAtlas.lua"
local now=1792400000000
local files,callback={},nil
local scans=0
local visitedChunks=0
local function seq(list)
    return {size=function()return #list end,
        get=function(_,i)return list[i+1] end}
end
local function rect(x,y,x2,y2)
    return {getX=function()return x end,getY=function()return y end,
        getX2=function()return x2 end,getY2=function()return y2 end}
end
local function room(z,name,list)
    return {getZ=function()return z end,getName=function()return name end,
        getRects=function()return seq(list)end}
end
local school=rect(100,200,120,220)
school.getIDString=function()return "school-01" end
school.getRooms=function()return seq({
    room(0,"classroom",{rect(101,201,110,211),rect(108,209,117,217)}),
    room(1,"upper_floor",{rect(100,200,112,212)})
})end
local far=rect(200,300,220,330)
far.getRooms=function()return seq({room(0,"far room",{rect(200,300,220,330)})})end
local near=rect(122,210,127,218)
near.getRooms=function()return seq({room(0,"garage",{rect(123,210,126,217)})})end
local all=seq({school,far,near})
getWorld=function()
    return {getMetaGrid=function()
        scans=scans+1
        return {getBuildings=function()return all end}
    end}
end
getCell=function()return {getChunk=function(_,cx,cy)
    visitedChunks=visitedChunks+1
    return cx==10 and cy==20 and {} or nil
end}end
getTimestampMs=function()return now end
SiegerStoryScenes={world="map_world"}
isClient=function()return false end
Events={OnTickEvenPaused={Add=function(fn)callback=fn end}}
getFileReader=function(name)
    local body=files[name]
    if not body then return nil end
    local start=1
    return {
        readLine=function()
            if start>#body then return nil end
            local newline=body:find("\n",start,true)
            local value=body:sub(start,newline and newline-1 or #body)
            start=newline and newline+1 or #body+1
            return value
        end,close=function()end
    }
end
getFileWriter=function(name,create,append)
    local body=append and(files[name]or"")or""
    return {write=function(_,text)body=body..text end,
            close=function()files[name]=body end}
end
dofile(runtime)
assert(callback,"Atlas listener missing")
for i=1,120 do now=now+50;callback() end
assert(scans==0 and visitedChunks==0,"Atlas MUST NOT access world while idle")
local function query(letter,world,x0,y0,x1,y1,expires,maxrows)
    local id=string.rep(letter,32)
    files["SiegerAdminAtlasRequest.txt"]=table.concat({
        "v1",id,world,tostring(x0),tostring(y0),tostring(x1),tostring(y1),
        "0","1",tostring(maxrows or 50000),tostring(expires or now+30000),"end"
    },"\t").."\n"
    now=now+1200;callback()
    return files["SiegerAdminAtlasResult.txt"]or"",files["SiegerAdminAtlas-"..id..".txt"]or""
end
local receipt,log=query("a","map_world",100,200,130,230)
assert(receipt:find("\tcomplete\t2\t3\t4\t1\t",1,true),receipt)
assert(log:find("\tb0\t100\t200\t120\t220\t",1,true),"School metadata missing")
assert(log:find("r\tb0\tb0_r0\t0\t101\t201\t110\t211\t",1,true))
assert(log:find("r\tb0\tb0_r0\t0\t108\t209\t117\t217\t",1,true))
assert(log:find("r\tb0\tb0_r1\t1\t100\t200\t112\t212\t",1,true))
assert(log:find("c\t10\t20\n",1,true),"Loaded-chunk presence not included")
assert(log:find("end\t7\t2\t3\t4\t1\n",1,true),log)
local scanned,chunkScans=scans,visitedChunks
for i=1,60 do now=now+50;callback()end
assert(scans==scanned and visitedChunks==chunkScans,"Idle must never repeat atlas")
local before=log
receipt,log=query("a","map_world",100,200,130,230)
assert(log==before and scans==scanned,"Identical ID must not create another atlas")
receipt,log=query("b","wrong_world",100,200,130,230)
assert(receipt:find("\terror\t",1,true),"Mismatched world must report error")
assert(scans==scanned,"Wrong-world scan MUST not read metadata")
receipt,log=query("c","map_world",100,200,130,230,now-2000)
assert(receipt:find("\terror\t",1,true),"Expired request must report error")
assert(scans==scanned)
receipt,log=query("d","map_world",100,200,130,230,nil,1)
assert(receipt:find("\terror\t",1,true),"Budget exhaustion must never report complete")
receipt,log=query("e","map_world",400,500,450,550)
assert(receipt:find("\tcomplete\t0\t0\t0\t0\t",1,true),"Empty city zone should succeed")
assert(scans>=scanned+2)
print("PASS: universal metagrid Atlas, 3-room/4-rect multi-floor export, chunk coverage, idle, errors, replay")
