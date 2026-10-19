-- Engine-shaped Lua 5.1 fixture: batch preflight, one-shot mixed apply,
-- occupied vehicle acceptance, item sync, replay and active world identity.
local file=assert(arg[1])
local REQUEST="SiegerStoryBatchRequest.txt"
local RESULT="SiegerStoryBatchResult.txt"
local GUARD="SiegerStoryBatchGuard.txt"
local files,clock,changes,failed
local function list(arr)
    return {size=function()return #arr end,
            get=function(_,i)return arr[i+1] end}
end
local function item(kind)
    return {getFullType=function()return kind end,
            getItem=function()return nil end}
end
local function setup()
    files={};clock=0;changes={sync=0,condition=60,fuel=10,battery=.5,
                       healed=false,groundAdds=0,groundRemoves=0}
    failed=false
    local cargo={item("Base.Bandage"),item("Base.Bandage")}
    local inv={item("Base.Plank"),item("Base.Plank"),item("Base.Plank")}
    local counterItems={item("Base.Bandage"),item("Base.Bandage")}
    local function container(array)
        return {getItems=function()return list(array)end,
            AddItem=function(_,value)
                array[#array+1]=value
                return value
            end,
            Remove=function(_,value)
                for i,x in ipairs(array) do
                    if x==value then table.remove(array,i);return end
                end
                error("missing inventory item")
            end}
    end
    local truckBed=container(cargo)
    local playerInv=container(inv)
    local counter=container(counterItems)
    counter.getType=function()return "counter" end
    local battery={
        getCurrentUsesFloat=function()return changes.battery end,
        setCurrentUsesFloat=function(_,v)changes.battery=v end
    }
    local parts={}
    for _,name in ipairs({"Engine","GasTank","Battery","TruckBed"}) do
        local partName=name
        parts[name]={
            getId=function()return partName end,
            getCondition=function()return changes.condition end,
            setCondition=function(_,v)changes.condition=v end,
            getContainerContentAmount=function()return changes.fuel end,
            setContainerContentAmount=function(_,v)changes.fuel=v end,
            getContainerCapacity=function()return 40 end,
            getInventoryItem=function()return battery end,
            getItemContainer=function()return truckBed end
        }
    end
    local car={
        getId=function()return 253 end,
        getScriptName=function()return "Base.PickUpTruck" end,
        getX=function()return 10.5 end,getY=function()return 20.5 end,
        getZ=function()return 0 end,
        getPartById=function(_,name)return parts[name]end,
        transmitPartCondition=function()changes.sync=changes.sync+1 end,
        transmitPartModData=function()changes.sync=changes.sync+1 end,
        transmitPartUsedDelta=function()changes.sync=changes.sync+1 end
    }
    local bodypart={RestoreToFullHealth=function()changes.healed=true end}
    CharacterStat={HUNGER="hunger"}
    local stats={get=function()return changes.hunger end,set=function(_,enum,v)assert(enum=="hunger");changes.hunger=v;return true end}
    local player={
        getUsername=function()return "operator" end,
        getVehicle=function()return car end,
        getInventory=function()return playerInv end,
        getStats=function()return stats end,
        getBodyDamage=function()return {getBodyParts=function()return list({bodypart})end}end
    }
    local ground={}
    local sq={
        getObjects=function()
            return list({{getContainerByIndex=function(_,index)
                return index==0 and counter or nil
            end}})
        end,
        getWorldObjects=function()return list(ground)end,
        AddWorldInventoryItem=function(_,value)
            changes.groundAdds=changes.groundAdds+1
            local wrapped={getItem=function()return value end}
            ground[#ground+1]=wrapped
            return wrapped
        end,
        transmitRemoveItemFromSquare=function(_,wrapped)
            for i,v in ipairs(ground) do
                if v==wrapped then
                    table.remove(ground,i)
                    changes.groundRemoves=changes.groundRemoves+1
                    return
                end
            end
            error("Ground target disappeared")
        end
    }
    ground[1]={getItem=function()return item("Base.Plank") end}
    getCell=function()
        return {
            getVehicles=function()
                return {iterator=function()
                    local first=true
                    return {
                        hasNext=function()return first end,
                        next=function()first=false;return car end
                    }
                end}
            end,
            getGridSquare=function(_,x,y,z)
                if x==12 and y==20 and z==0 then return sq end
                return nil
            end
        }
    end
    getOnlinePlayers=function()return list({player})end
    instanceItem=function(kind)
        if kind=="Nope.NotReal" then return nil end
        return item(kind)
    end
    sendAddItemToContainer=function()changes.sync=changes.sync+1 end
    sendRemoveItemFromContainer=function()changes.sync=changes.sync+1 end
    isClient=function()return false end
    SiegerStoryScenes={world="road_home"}
    Events={OnTick={Add=function(fn)clock=fn end}}
    getFileReader=function(name)
        local data=files[name]
        if not data then return nil end
        local rows={}
        for row in (data.."\n"):gmatch("([^\n]+)\n") do rows[#rows+1]=row end
        local idx=0
        return {readLine=function()idx=idx+1;return rows[idx]end,close=function()end}
    end
    getFileWriter=function(name)
        files[name]=""
        return {write=function(_,str)files[name]=files[name]..str end,close=function()end}
    end
    dofile(file)
end
local function action(kind,id,script,x,y,z,part,operation,typeId,v,expected,extra)
    return table.concat({kind,id,script,x,y,z,part,operation,typeId,v,expected,extra},"\t")
end
local function tick()
    for _=1,120 do clock() end
end
local function submit(hex,actions)
    local id=string.rep(hex,32)
    local header=table.concat({"v1",id,"road_home",string.rep("a",64),tostring(#actions)},"\t")
    files[REQUEST]=header.."\n"..table.concat(actions,"\n").."\n"
    tick()
    return files[RESULT] or ""
end
local function v(part,op,key,to,expected)
    return action("vehicle","253","Base.PickUpTruck","10","20","0",
        part,op,key,to,expected,"-")
end
local function p(op,key,to)
    return action("player","operator","-","-","-","-",
        "-",op,key,to,"-","-")
end
local function c(op,kind,count)
    return action("container","0","counter","12","20","0",
        "0q",op,kind,count,"-","-")
end
local function g(op,kind,count,extra)
    return action("ground","-","-","12","20","0",
        "-",op,kind,count,"-",extra)
end
setup()
local bad={v("Engine","condition","-","90","60"),
           p("add","Nope.NotReal","2")}
local reply=submit("1",bad)
assert(reply:find("\terror\t0\t2\tpreflight_failed",1,true))
assert(changes.condition==60 and changes.sync==0 and not files[GUARD],
    "Batch MUST preflight all edits before touching the car")
setup()
local good={
    v("Engine","condition","-","100","60"),
    v("GasTank","fuel","-","30","10"),
    v("Battery","battery","-","0.95","0.5"),
    v("TruckBed","add","Example.CustomItem","7","-"),
    v("TruckBed","remove","Base.Bandage","1","-"),
    p("heal","-","0"),
    p("stat","hunger","0.1"),
    p("add","Example.CustomItem","3"),
    p("remove","Base.Plank","2"),
    c("add","Base.Plank","4"),
    c("remove","Base.Bandage","1"),
    g("add","Base.Plank","2","0.5,0.5,0"),
    g("remove","Base.Plank","1","-")
}
reply=submit("2",good)
assert(reply:find("\tcomplete\t13\t13\tserver_applied",1,true),reply)
assert(changes.condition==100 and changes.fuel==30
    and changes.battery==.95 and changes.healed
    and math.abs(changes.hunger-.1)<.00001, "Multi-target state not applied")
assert(changes.sync==21 and changes.groundAdds==2 and changes.groundRemoves==1,
    "Did not sync inventory, cargo and world objects")
local count=changes.sync
tick()
assert(changes.sync==count,"Repeated request must not be applied twice")
dofile(file)
tick()
assert(changes.sync==count,"Reloaded runtime must not replay the same request")
print("PASS: production-world batch preflight, car state, heal, multi-item spawn and replay guard")
