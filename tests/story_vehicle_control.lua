-- Actual B42.21 drainable ABI: get/setCurrentUsesFloat, no getUsedDelta.
local source=assert(arg[1])
local REQ="SiegerStoryVehicleRequest.txt"
local RES="SiegerStoryVehicleResult.txt"
local GUARD="SiegerStoryVehicleGuard.txt"
local memory,car,parts,charge,tick,occupied,sync,added,removed
local function reset()
    memory={};charge=.60;occupied=false;sync=0;added=0;removed=0
    isClient=function()return false end
    SiegerStoryScenes={world="story_test"}
    Events={OnTick={Add=function(fn)tick=fn end}}
    getFileReader=function(name)
        if not memory[name] then return nil end
        local lines={};for line in memory[name]:gmatch("([^\n]+)")do lines[#lines+1]=line end
        local i=0
        return {readLine=function()i=i+1;return lines[i]end,close=function()end}
    end
    getFileWriter=function(name)
        assert(name==RES or name==GUARD)
        memory[name]=""
        return {write=function(_,s)memory[name]=memory[name]..s end,close=function()end}
    end
    local battery={getCurrentUsesFloat=function()return charge end,
        setCurrentUsesFloat=function(_,v)charge=v end}
    local contents={}
    local items={size=function()return #contents end,get=function(_,i)return contents[i+1]end}
    local container={getItems=function()return items end,
        AddItem=function(_,typ)
            assert(typ=="Base.WaterBottle" or typ=="Base.CigaretteSingle")
            local item={getFullType=function()return typ end}
            contents[#contents+1]=item;added=added+1;return item
        end,
        Remove=function(_,item)
            for i,v in ipairs(contents)do if v==item then table.remove(contents,i);removed=removed+1;return end end
            error("missing item")
        end}
    parts={}
    for _,id in ipairs({"Battery","GasTank","GloveBox","Engine"})do
        local key=id;local condition=98;local fuel=12
        parts[id]={getId=function()return key end,getCondition=function()return condition end,
            setCondition=function(_,v)condition=v end,
            getInventoryItem=function()return key=="Battery" and battery or nil end,
            getContainerContentAmount=function()return fuel end,
            getContainerCapacity=function()return 40 end,
            setContainerContentAmount=function(_,v)fuel=v end,
            getItemContainer=function()return key=="GloveBox" and container or nil end}
    end
    car={getId=function()return 253 end,getScriptName=function()return "Base.PickUpTruck" end,
        getX=function()return 10.5 end,getY=function()return 20.5 end,getZ=function()return 0 end,
        getPartById=function(_,key)return parts[key]end,
        transmitPartCondition=function()sync=sync+1 end,
        transmitPartModData=function()sync=sync+1 end,
        transmitPartUsedDelta=function()sync=sync+1 end}
    local collection={iterator=function()
        local done=false
        return {hasNext=function()return not done end,next=function()done=true;return car end}
    end}
    getCell=function()return {getVehicles=function()return collection end}end
    getOnlinePlayers=function()return {size=function()return occupied and 1 or 0 end,
        get=function()return {getVehicle=function()return car end}end}end
    sendAddItemToContainer=function()sync=sync+1 end
    sendRemoveItemFromContainer=function()sync=sync+1 end
    dofile(source)
end
local counter=0
local function request(op,part,expected,value,x)
    counter=counter+1
    local id=string.format("%032x",counter)
    memory[REQ]=table.concat({"v1",id,"story_test",op,"253","Base.PickUpTruck",
        tostring(x or 10),"20","0",part or "-",expected or "-",value or "0"},"\t").."\n"
    for _=1,120 do tick()end
    assert(memory[RES],"no ACK")
    return memory[RES]
end
reset()
assert(request("inspect"):find("fuel_12__battery_0.6",1,true))
assert(not memory[GUARD] and sync==0)
assert(request("battery","Battery","0.6","0.75"):find("\tcomplete\t",1,true))
assert(charge==.75 and sync==1)
for _=1,240 do tick()end
assert(sync==1,"duplicate request executed twice")
dofile(source) -- restart must read prior response and suppress the same ID
for _=1,120 do tick()end
assert(sync==1,"replay after runtime reload")
reset();occupied=true
assert(request("battery","Battery","0.6","0.75"):find("\terror\t",1,true))
assert(charge==.6 and not memory[GUARD] and sync==0)
reset()
assert(request("condition","Engine","97","60"):find("\terror\t",1,true))
assert(parts.Engine:getCondition()==98 and not memory[GUARD])
reset()
assert(request("condition","Engine","98","60",11):find("\terror\t",1,true))
assert(parts.Engine:getCondition()==98 and not memory[GUARD])
reset()
assert(request("fuel","GasTank","12","41"):find("\terror\t",1,true))
assert(parts.GasTank:getContainerContentAmount()==12 and not memory[GUARD])
reset()
car.transmitPartUsedDelta=nil
assert(request("battery","Battery","0.6","0.75"):find("\terror\t",1,true))
assert(charge==.6 and not memory[GUARD])
for _,typ in ipairs({"Base.WaterBottle","Base.CigaretteSingle"})do
    reset()
    assert(request("add","GloveBox",typ,"2"):find("\tcomplete\t",1,true))
    assert(added==2 and sync==2)
    assert(request("remove","GloveBox",typ,"1"):find("\tcomplete\t",1,true))
    assert(removed==1 and sync==3)
end
reset()
assert(request("add","GloveBox","Base.WaterBottleEmpty","1"):find("\terror\t",1,true))
assert(added==0 and not memory[GUARD])
print("PASS: B42 battery API, exact identity, occupied/sync/expected-value guards, item sync and replay")
