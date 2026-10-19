-- Build 42-shaped game Lua fixture: genuine native object types, stage
-- dependencies, guarded two-pass preflight, existing object replacement and
-- replay defense. No real game/save state is modified by this test.
local runtime=arg[1] or "story/runtime/SiegerAdminConstruction.lua"
local files={},tick,objects,created,nativeSends,world
local clock=1792400000000
local function seq(array)
    return {size=function()return #array end,get=function(_,i)return array[i+1]end}
end
local function newObject(kind,sp,north)
    local obj={kind=kind,sp=sp,north=north,md={},health=100}
    function obj:getModData()return self.md end
    function obj:getSprite()return {getName=function()return self.sp end}end
    function obj:getNorth()return self.north end
    function obj:transmitCompleteItemToClients()
        nativeSends=nativeSends+1
    end
    function obj:setMaxHealth(n)self.maxHealth=n end
    function obj:setHealth(n)self.health=n end
    function obj:setHoppable(v)self.hoppable=v end
    function obj:setIsFloor(v)self.floor=v end
    function obj:setIsDoor(v)self.door=v end
    function obj:setIsLocked(v)self.locked=v end
    function obj:getContainerCount()return 0 end
    function obj:isActivated()return false end
    return obj
end
local function getSquare(x,y,z)
    local key=table.concat({x,y,z},":")
    if not objects[key]then
        local sq={all={},x=x,y=y,z=z}
        function sq:getObjects()return seq(self.all)end
        function sq:getFloor()return nil end
        function sq:getRoom()return nil end
        function sq:getMovingObjects()return seq({})end
        function sq:isVehicleIntersecting()return false end
        function sq:AddSpecialObject(o)
            self.all[#self.all+1]=o
            created=created+1
        end
        sq.AddTileObject=sq.AddSpecialObject
        function sq:transmitRemoveItemFromSquare(obj)
            for i,value in ipairs(self.all) do
                if value==obj then
                    table.remove(self.all,i);nativeSends=nativeSends+1;return i-1
                end
            end
            error("attempted to remove unknown object")
        end
        function sq:RecalcAllWithNeighbours()end
        objects[key]=sq
    end
    return objects[key]
end
local function start()
    files={};objects={};created=0;nativeSends=0;clock=1792400000000
    SiegerStoryScenes={world="map_world"}
    getTimestampMs=function()return clock end
    getCell=function()return {getGridSquare=function(_,x,y,z)
        if x>=0 and x<=1000 and y>=0 and y<=1000 and z>=0 and z<=3 then
            return getSquare(x,y,z)
        end
        return nil
    end}end
    isClient=function()return false end
    IsoFlagType={collideN="collideN",collideW="collideW"}
    instanceof=function(obj,kind)return obj.kind==kind end
    getSprite=function(name)
        if name=="MissingSprite" then return nil end
        return {getName=function()return name end}
    end
    instanceItem=function(kind)
        if kind=="Missing.Item"then return nil end
        return {kind=kind,md={},getModData=function(self)return self.md end,
                setCondition=function(self,c)self.condition=c end}
    end
    IsoThumpable={new=function(_,sq,sprite,orientation)
        return newObject("IsoThumpable",sprite,orientation)
    end}
    IsoDoor={new=function(_,sq,sprite,orientation)
        return newObject("IsoDoor",sprite,orientation)
    end}
    IsoWindow={new=function(_,sq,sprite,orientation)
        return newObject("IsoWindow",sprite:getName(),orientation)
    end}
    IsoObject={new=function(_,sq,sprite)
        return newObject("IsoObject",sprite,false)
    end}
    IsoGenerator={new=function(item,_,sq)
        local object=newObject("IsoGenerator","appliances_misc_01_0",false)
        object.item=item
        sq:AddSpecialObject(object)
        return object
    end}
    Events={OnTickEvenPaused={Add=function(callback)tick=callback end}}
    getFileReader=function(name)
        local value=files[name]
        if not value then return nil end
        local rows={}
        for str in value:gmatch("[^\n]+") do rows[#rows+1]=str end
        local i=0
        return {readLine=function()i=i+1;return rows[i]end,close=function()end}
    end
    getFileWriter=function(name,create,append)
        local text=append and files[name] or ""
        return {write=function(_,v)text=text..v end,
                close=function()files[name]=text end}
    end
    dofile(runtime)
end
local function pump(n)
    for i=1,(n or 130) do clock=clock+50;tick() end
end
local function request(requestLetter,settlement,stage,actions,deps,permit,worldName)
    local id=string.rep(requestLetter,32)
    local header=table.concat({"v1",id,worldName or "map_world",settlement,stage,
        string.rep("a",64),tostring(#actions),deps or "-",
        permit and "1" or "0",tostring(clock+30000),"end"},"\t")
    files.SiegerAdminConstructionRequest.txt=header.."\n"..table.concat(actions,"\n").."\n"
    pump()
    return files.SiegerAdminConstructionResult.txt or ""
end
local function a(id,verb,kind,x,y,z,face,sprite,open,health,expect,index)
    return table.concat({"a",id,verb,kind,tostring(x),tostring(y),
        tostring(z),face,sprite,open,health,expect,index},"\t")
end
local wall=a("fence","place","wall",10,20,0,"N","carpentry_02_80","-","350","-","-")
local door=a("door","place","door",11,20,0,"N","fixtures_doors_01_3","-","350","-","-")
local window=a("window","place","window",12,20,0,"W","fixtures_windows_01_25","-","-","-","-")
local generator=a("power","place","generator",13,20,0,"-","Base.Generator","-","88","-","-")
start()
pump(160)
assert(created==0,"Server processed idle requests")
local fail=request("1","refuge","shelter",{wall,
    a("bad","place","wall",900000,20,0,"N","carpentry_02_81","-","200","-","-")})
assert(fail:find("\terror\t0\t2\tpreflight_failed",1,true),
    "Whole stage must reject before first mutation")
assert(created==0 and nativeSends==0 and not files.SiegerAdminConstructionGuard.txt,
    "No world mutation or durable attempt on preflight failure")
local skip=request("2","refuge","infrastructure",{generator},"shelter")
assert(skip:find("\terror\t0\t1\tpreflight_failed",1,true),"Missing stage dependency should fail")
assert(created==0)
local done=request("3","refuge","shelter",{wall,door,window,generator})
assert(done:find("\tcomplete\t4\t4\tserver_applied",1,true),done)
assert(created==4 and nativeSends==4,"Native objects and replication missing")
assert(objects["10:20:0"].all[1].kind=="IsoThumpable")
assert(objects["11:20:0"].all[1].kind=="IsoDoor")
assert(objects["12:20:0"].all[1].kind=="IsoWindow")
local g=objects["13:20:0"].all[1]
assert(g.kind=="IsoGenerator" and g.item.condition==88 and g.item.md.fuel==0)
assert(g:getModData().SiegerAdminConstructionTag=="refuge:shelter:power")
assert(files.SiegerAdminConstructionStages.txt:find("refuge\tshelter",1,true))
local existing=request("4","refuge","shelter",{wall})
assert(existing:find("\terror\t0\t1\tpreflight_failed",1,true),
    "Completed stage must not be applied twice")
local before=created
pump(240)
assert(created==before,"Idle frames unexpectedly replay stage")
local other=request("5","refuge","another",{wall},"infrastructure")
assert(other:find("\terror\t0\t1\tpreflight_failed",1,true),
    "Stage with missing prerequisite must refuse")
-- Unreviewed native door removal may NEVER happen without explicit approval.
local removeDoor=a("old","remove_exact","IsoDoor",11,20,0,"N",
                   "fixtures_doors_01_3","-","-","-","0")
local no=request("6","refuge","infrastructure",{removeDoor},"shelter",false)
assert(no:find("\terror\t0\t1\tpreflight_failed",1,true))
assert(#objects["11:20:0"].all==1)
-- Replacement can be planned as remove_exact -> native placement in one stage.
local replaceDoor=a("replacement","place","door",11,20,0,"N",
                    "fixtures_doors_01_5","-","200","-","-")
local yes=request("7","refuge","infrastructure",{removeDoor,replaceDoor},
                  "shelter",true)
assert(yes:find("\tcomplete\t2\t2\tserver_applied",1,true),yes)
assert(#objects["11:20:0"].all==1 and
       objects["11:20:0"].all[1].sp=="fixtures_doors_01_5")
local demolish=a("demolish","remove_tag","IsoThumpable",10,20,0,"N",
    "carpentry_02_80","-","-","refuge:shelter:fence","-")
local gone=request("8","refuge","expansion",{demolish},"infrastructure")
assert(gone:find("\tcomplete\t1\t1\tserver_applied",1,true))
assert(#objects["10:20:0"].all==0,"Tagged construction not removed")
-- Restart after a completed stage does not perform a ghost replay.
local last=created
dofile(runtime);pump(180)
assert(created==last,"Reloaded runtime replayed a completed stage")
-- This is the ONLY checked world; offworld request must not even inspect square.
SiegerStoryScenes.world="map_world"
local off=request("9","refuge","offworld",{generator},"-",false,"foreign_world")
assert(off:find("\terror\t0\t1\tpreflight_failed",1,true))
assert(created==last)
print("PASS: typed staged building, true door/window/wall/generator, preflight, dependencies, exact removal, tags, network and replay")
