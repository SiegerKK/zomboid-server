-- Build 42-shaped game Lua fixture: genuine native object types, stage
-- dependencies, guarded two-pass preflight, existing object replacement and
-- replay defense. No real game/save state is modified by this test.
local runtime=arg[1] or "story/runtime/SiegerAdminConstruction.lua"
local files,tick,objects,created,nativeSends,world = {},nil,nil,0,0,nil
local clock=1792400000000
local function seq(array)
    return {size=function()return #array end,get=function(_,i)return array[i+1]end}
end
local function newObject(kind,sp,north)
    local obj={kind=kind,sp=sp,north=north,md={},health=100}
    function obj:getModData()return self.md end
    function obj:getSprite()return {getName=function()return self.sp end}end
    function obj:getNorth()return self.north end
    function obj:getProperties()return getSprite(self.sp):getProperties()end
    function obj:transmitCompleteItemToClients()
        if _failSend then error("mock_network_failure")end
        nativeSends=nativeSends+1
    end
    function obj:setMaxHealth(n)self.maxHealth=n end
    function obj:setHealth(n)self.health=n end
    function obj:setHoppable(v)self.hoppable=v end
    function obj:setIsFloor(v)self.floor=v end
    function obj:setIsDoor(v)self.door=v end
    function obj:setIsLocked(v)self.locked=v end
    function obj:getContainerCount()return self.container and 1 or 0 end
    function obj:getContainer()return self.container end
    function obj:setIsContainer(flag)
        if flag then
            local c={capacity=50}
            function c:getType()return "crate" end
            function c:setCapacity(v)self.capacity=v end
            function c:getCapacity()return self.capacity end
            self.container=c
        end
    end
    function obj:setBlockAllTheSquare(flag)self.blockAll=flag end
    function obj:isActivated()return false end
    function obj:isBarricadeAllowed()return self.kind=="IsoWindow" end
    function obj:getBarricadeOnSameSquare()return self.barricade end
    return obj
end
local function getSquare(x,y,z)
    local key=table.concat({x,y,z},":")
    if not objects[key]then
        local sq={all={},x=x,y=y,z=z}
        function sq:getObjects()return seq(self.all)end
        function sq:getFloor()return self.floor and {} or nil end
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
        return {getName=function()return name end,
            getProperties=function()return {
                has=function()return false end,
                Val=function(_,key)
                    if key=="BedType" and (name=="bed_head" or name=="bed_foot") then
                        return "averageBed"end
                end,
                Set=function()error("Never modify shared sprite properties")end
            }end}
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
        local o=newObject("IsoWindow",sprite:getName(),orientation)
        o.square=sq
        return o
    end}
    IsoObject={new=function(_,sq,sprite)
        assert(type(sprite)=="table" and sprite.getName,
            "Decorative native IsoObject must receive an IsoSprite")
        return newObject("IsoObject",sprite:getName(),false)
    end}
    IsoBarricade={AddBarricadeToObject=function(window,opposite)
        assert(opposite==false,"same-square side required")
        assert(window.kind=="IsoWindow" and not window.barricade)
        local o=newObject("IsoBarricade","carpentry_02_100",false)
        o.planks=0
        function o:addPlank(chr,item)
            assert(chr==nil and item==nil and self.planks<4)
            self.planks=self.planks+1
        end
        function o:getNumPlanks()return self.planks end
        window.barricade=o
        window.square:AddSpecialObject(o)
        return o
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
    files["SiegerAdminConstructionRequest.txt"]=header.."\n"..table.concat(actions,"\n").."\n"
    pump()
    return files["SiegerAdminConstructionResult.txt"] or ""
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
assert(created==0 and nativeSends==0 and not files["SiegerAdminConstructionGuard.txt"],
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
assert(files["SiegerAdminConstructionStages.txt"]:find("refuge\tshelter",1,true))
local windowBarricade=a("first_planks","barricade","IsoWindow",12,20,0,
    "W","fixtures_windows_01_25","-","2","-","0")
local deniedBarricade=request("a","refuge","fortify_windows",{windowBarricade},
                             "shelter",false)
assert(deniedBarricade:find("\terror\t0\t1\tpreflight_failed",1,true))
assert(#objects["12:20:0"].all==1,"Denied barricade mutated game")
local nativeBarricade=request("b","refuge","fortify_windows",{windowBarricade},
                             "shelter",true)
assert(nativeBarricade:find("\tcomplete\t1\t1\tserver_applied",1,true),
    nativeBarricade)
assert(#objects["12:20:0"].all==2)
assert(objects["12:20:0"].all[2].kind=="IsoBarricade" and
       objects["12:20:0"].all[2].planks==2)
assert(objects["12:20:0"].all[2].md.SiegerAdminConstructionTag==
       "refuge:fortify_windows:first_planks")
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
       objects["11:20:0"].all[1].sp=="fixtures_doors_01_5"
       and objects["11:20:0"].all[1].health==200,
       "Native door health must use the planned value")
local demolish=a("demolish","remove_tag","IsoThumpable",10,20,0,"N",
    "carpentry_02_80","-","-","refuge:shelter:fence","-")
local gone=request("8","refuge","expansion",{demolish},"infrastructure")
assert(gone:find("\tcomplete\t1\t1\tserver_applied",1,true))
assert(#objects["10:20:0"].all==0,"Tagged construction not removed")
local crate=a("dry_store","place","storage",15,20,0,"-",
    "carpentry_02_15","-","400","60","-")
local doneCrate=request("c","refuge","storeroom",{crate},"expansion")
assert(doneCrate:find("\tcomplete\t1\t1\tserver_applied",1,true),doneCrate)
local obj=objects["15:20:0"].all[1]
assert(obj and obj.kind=="IsoThumpable" and obj:getContainerCount()==1)
assert(obj:getContainer():getType()=="crate" and
       obj:getContainer():getCapacity()==60 and obj.blockAll==true,
       "Storage must be a real interactable native ItemContainer")
assert(obj.md.SiegerAdminConstructionTag=="refuge:storeroom:dry_store")
local badStorage=a("bad","place","storage",16,20,0,"-",
    "carpentry_02_15","-","400","999","-")
local rejected=request("d","refuge","bad_storeroom",{badStorage},"storeroom")
assert(rejected:find("\terror\t0\t1\tpreflight_failed",1,true))
assert(not objects["16:20:0"] or #objects["16:20:0"].all==0,
       "Invalid crate capacity must reject before any modification")
-- Restart after a completed stage does not perform a ghost replay.
local last=created
dofile(runtime);pump(180)
assert(created==last,"Reloaded runtime replayed a completed stage")
-- This is the ONLY checked world; offworld request must not even inspect square.
SiegerStoryScenes.world="map_world"
local off=request("9","refuge","offworld",{generator},"-",false,"foreign_world")
assert(off:find("\terror\t0\t1\tpreflight_failed",1,true))
assert(created==last)
-- Two native tiles of one bed: no synthetic BedType assignment or tile deletion.
start()
getSquare(50,50,0).floor=true;getSquare(50,51,0).floor=true
local head=a("bed_head","place","bed",50,50,0,"-","bed_head","-","-","averageBed","-")
local foot=a("bed_foot","place","bed",50,51,0,"-","bed_foot","-","-","averageBed","-")
local fake=a("fake","place","bed",50,51,0,"-","ordinary_decor","-","-","averageBed","-")
local failBed=request("a","refuge","beds",{head,fake})
assert(failBed:find("\terror\t0\t2\tpreflight_failed",1,true),failBed)
assert(created==0 and not files["SiegerAdminConstructionGuard.txt"],
       "Invalid foot tile must prevent all bed placement")
local okBed=request("b","refuge","beds",{head,foot})
assert(okBed:find("\tcomplete\t2\t2\tserver_applied",1,true),okBed)
assert(objects["50:50:0"].all[1].kind=="IsoObject")
assert(objects["50:51:0"].all[1]:getProperties():Val("BedType")=="averageBed")
assert(nativeSends==2,"Every native bed tile must be replicated")
start()
local noFloor=request("c","refuge","beds",{head})
assert(noFloor:find("\terror\t0\t1\tpreflight_failed",1,true),noFloor)
assert(created==0,"Bed over unobserved floor must reject")
start();getSquare(50,50,0).floor=true;_failSend=true
local partial=request("d","refuge","beds",{head})
_failSend=nil
assert(partial:find("\terror\t0\t1\tpartial_possible",1,true),partial)
assert(created==1 and not files["SiegerAdminConstructionStages.txt"],
       "Failed first replication must not be called unmodified or completed")
start()
getSquare(60,60,0).all[1]={kind="IsoObject",getProperties=function()
    return {has=function(_,flag)return flag=="collideN" end}
end}
local edge=a("wall","place","wall",60,60,0,"N","carpentry_02_81","-","500","-","-")
local blocked=request("e","refuge","native_edge",{edge})
assert(blocked:find("\terror\t0\t1\tpreflight_failed",1,true),blocked)
assert(created==0,"B42 has(collideN) must block placement through a vanilla wall")
start()
getSquare(60,60,0).all[1]={kind="IsoObject",getProperties=function()return {}end}
local unknown=request("f","refuge","unknown_edge",{edge})
assert(unknown:find("\terror\t0\t1\tpreflight_failed",1,true),unknown)
assert(created==0,"Missing native collision-property API must fail closed")
print("PASS: native beds, crates, barricades, B42 collision flags and first-action partial ACK")
