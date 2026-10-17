-- Behavior probe for narrowly scoped zombie clearance: only Smokey's.
local runtime=arg[1] or "story/runtime/SiegerStoryBarControl.lua"
local events,files={},{}
local removed={}
local deleted=0
Events={OnTick={Add=function(fn)events.tick=fn end}}
isClient=function()return false end
SiegerStoryScenes={schema=1,world="story_test"}
local function list(arr)
 return {size=function()return #arr end,get=function(_,i)return arr[i+1] end}
end
local players={}
getOnlinePlayers=function()return list(players)end
getFileReader=function(name)
 if not files[name] then return nil end
 local rows={}
 for row in files[name]:gmatch("[^\n]+")do rows[#rows+1]=row end
 local cursor=0
 return {readLine=function()cursor=cursor+1;return rows[cursor]end,close=function()end}
end
getFileWriter=function(name,create,append)
 if not append then files[name]="" end
 return {write=function(_,str)files[name]=(files[name]or"")..str end,close=function()end}
end
local function zombie(x,y,z)
 return {class="IsoZombie",getX=function()return x end,
 getY=function()return y end,getZ=function()return z end}
end
local a=zombie(10619.5,9220.2,0)
local b=zombie(10622.5,9230.1,1)
local outside=zombie(10634,9230,0)
local zombies={a,b,outside}
local cell={
 getGridSquare=function(_,x,y,z) return {loaded=true}end,
 getZombieList=function()return list(zombies)end}
getCell=function()return cell end
instanceof=function(z,class)return z and z.class==class end
VirtualZombieManager={instance={removeZombieFromWorld=function(_,z)
 deleted=deleted+1;removed[#removed+1]=z
 for i=#zombies,1,-1 do if zombies[i]==z then table.remove(zombies,i) end end
 return true
end}}
local function send(ch,mode,count)
 files["SiegerStoryBarRequest.txt"]=
 "v1\t"..string.rep(ch,32).."\tstory_test\t"..mode.."\t"..tostring(count).."\n"
 for i=1,130 do events.tick() end
 return files["SiegerStoryBarResult.txt"]
end
dofile(runtime)
local counted=send("a","inspect",0)
assert(counted:find("\tinspect\tcomplete\t2\t0\tserver_ack",1,true))
assert(deleted==0)
-- No overbroad clear if reality has changed since inspect.
local refused=send("b","clear",1)
assert(refused:find("\tclear\terror",1,true))
assert(deleted==0)
-- Player in footprint prevents any deletion.
players={zombie(10620,9222,0)}
local near=send("c","clear",2)
assert(near:find("\tclear\terror",1,true))
assert(deleted==0)
players={}
local cleared=send("d","clear",2)
assert(cleared:find("\tclear\tcomplete\t2\t2\tserver_ack",1,true))
assert(deleted==2 and #zombies==1 and zombies[1]==outside)
-- Re-load Lua with same request. ACK is durable and suppresses replay.
dofile(runtime)
for i=1,130 do events.tick() end
assert(deleted==2)
assert(files["SiegerStoryBarResult.txt"]:find("\tcomplete\t2\t2\t",1,true))
print("PASS: bounded one-shot Smokey's zombie inspection, expected-count clearance and no replay")
