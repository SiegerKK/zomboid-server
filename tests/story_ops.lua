-- Standalone Lua 5.1 test of read-only Story Ops snapshot protocol.
local path=arg[1] or "story/runtime/SiegerStoryOps.lua"
local files,events={},{}
local function reader(body)
    local pos=1
    return {readLine=function()
        if pos>#body then return nil end
        local nextNewline=body:find("\n",pos,true)
        if not nextNewline then
            local row=body:sub(pos);pos=#body+1;return row
        end
        local row=body:sub(pos,nextNewline-1);pos=nextNewline+1;return row
    end,close=function()end}
end
getFileReader=function(name)
    return files[name] and reader(files[name]) or nil
end
getFileWriter=function(name)
    local parts={}
    return {write=function(_,s)parts[#parts+1]=s end,
        close=function()files[name]=table.concat(parts)end}
end
local function list(entries)
    return {size=function()return #entries end,
            get=function(_,i)return entries[i+1] end}
end
local function player(user,x,y)
    return {getUsername=function()return user end,
            getX=function()return x end,getY=function()return y end,
            getZ=function()return 0 end,
            getVehicle=function()return nil end}
end
local admin=player("admin",100,100)
local friend=player("friend",104,100)
local users=list({admin,friend})
getOnlinePlayers=function()return users end
local function pos(x,y)
    return {getX=function()return x end,
        getY=function()return y end,getZ=function()return 0 end}
end
local zombies=list({pos(103,100),pos(108,100),pos(132,100)})
local vehicles={pos(105,100),pos(134,100)}
local cell={
    getZombieList=function()return zombies end,
    getVehicles=function()return {iterator=function()
        local i=0
        return {hasNext=function()return i<#vehicles end,
                next=function()i=i+1;return vehicles[i]end}
    end}end,
    getGridSquare=function(_,x,y,z)
        if x==110 and y==100 then return nil end
        return {x=x,y=y,z=z}
    end
}
getCell=function()return cell end
SiegerStoryScenes={world="story_test"}
isClient=function()return false end
Events={OnTick={Add=function(callback)events.tick=callback end}}
dofile(path)
assert(type(events.tick)=="function")
local function tick()
    for _=1,120 do events.tick() end
end
local function send(id,op,user,radius)
    files["SiegerStoryOpsRequest.txt"]="v1\t"..id.."\tstory_test\t"..op..
        "\t"..user.."\t"..radius.."\n"
    tick()
    return files["SiegerStoryOpsResult.txt"] or ""
end
local a=string.rep("a",32)
local r=send(a,"players","-",0)
assert(r:find("\tplayers\tcomplete\tserver_snapshot\t2\n",1,true))
assert(r:find("player\tadmin\t100.0\t100.0\t0.0\t-",1,true))
assert(r:find("player\tfriend\t104.0\t100.0\t0.0\t-",1,true))
local previous=r
tick()
assert(files["SiegerStoryOpsResult.txt"]==previous,"Repeated request must be ignored")
local b=string.rep("b",32)
r=send(b,"nearby","admin",10)
assert(r:find("\tnearby\tcomplete\tserver_snapshot\t1\n",1,true))
assert(r:find("nearby\tadmin\t10\t2\t3.0\t1\t1\t",1,true))
assert(r:find("\t316\t317\n",1,true),"Missing tiles must be reported explicitly")
local c=string.rep("c",32)
r=send(c,"nearby","offline",10)
assert(r:find("\tnearby\terror\treview_server_logs\t0\n",1,true))
local d=string.rep("d",32)
files["SiegerStoryOpsRequest.txt"]="v1\t"..d.."\tstory_test\tnearby\tadmin\t99\n"
tick()
assert(files["SiegerStoryOpsResult.txt"]==r,"Invalid radius must not generate response")
local e=string.rep("e",32)
SiegerStoryScenes.world="road_home"
r=send(e,"players","-",0)
assert(r:find("\tplayers\terror\treview_server_logs\t0\n",1,true))
print("PASS: read-only ops player census, nearby zombie/car/coverage, replay, invalid bounds, world lock")
