-- Lua 5.1 bounded harness: player inspect/grant/remove/heal with private root file protocol.
-- Mock behavior only. Requires pinned B42 MP tests before production.
local runtime=arg[1] or "story/runtime/SiegerStoryPlayerControl.lua"
local files,events={},{}
Events={OnTick={Add=function(fn)events.tick=fn end}}
isClient=function()return false end
SiegerStoryScenes={world="story_test",schema=1}
local function list(values)
    return {size=function()return #values end,
            get=function(_,i)return values[i+1] end}
end
getFileReader=function(name)
    if files[name]==nil then return nil end
    local vals={}
    for line in files[name]:gmatch("[^\n]+") do vals[#vals+1]=line end
    local cursor=0
    return {readLine=function()cursor=cursor+1;return vals[cursor]end,close=function()end}
end
getFileWriter=function(name,create,append)
    if not append then files[name]="" end
    return {write=function(_,s)files[name]=(files[name]or"")..s end,close=function()end}
end
local items={}
local inv={
    getItems=function()return list(items)end,
    AddItem=function(_,item)items[#items+1]=item;return item end,
    Remove=function(_,item)
        for i=#items,1,-1 do if items[i]==item then table.remove(items,i);return end end
        error("Missing item")
    end
}
local body1={health=79,RestoreToFullHealth=function(self)self.health=100 end,
    getHealth=function(self)return self.health end}
local body2={health=100,RestoreToFullHealth=function(self)self.health=100 end,
    getHealth=function(self)return self.health end}
CharacterStat={HUNGER="hunger",THIRST="thirst",FATIGUE="fatigue",STRESS="stress"}
local stats={get=function(_,key)return ({hunger=.1,thirst=.2,fatigue=.3,stress=.4})[key]end}
local body={getOverallBodyHealth=function()return 79 end,
    getBodyParts=function()return list({body1,body2})end}
local player={
    getUsername=function()return "admin"end,
    getX=function()return 10622.5 end,getY=function()return 9221.1 end,
    getZ=function()return 0 end,
    getStats=function()return stats end,getBodyDamage=function()return body end,
    getInventory=function()return inv end,
    getPrimaryHandItem=function()return nil end,
    getSecondaryHandItem=function()return nil end
}
getOnlinePlayers=function()return list({player})end
local adds,removes=0,0
sendAddItemToContainer=function()adds=adds+1 end
sendRemoveItemFromContainer=function()removes=removes+1 end
instanceItem=function(fullType)
    local md={}
    return {getFullType=function()return fullType end,getModData=function()return md end}
end
local function issue(id,op,arg,count)
    files["SiegerStoryPlayerRequest.txt"]=table.concat(
        {"v1",id,"story_test","admin",op,arg,tostring(count)},"\t").."\n"
    for i=1,130 do events.tick() end
    local result=files["SiegerStoryPlayerResult.txt"]
    assert(result and result:find("v1\t"..id.."\t",1,true),"Wrong/missing result")
    return result
end
dofile(runtime)
local inspected=issue(string.rep("a",32),"inspect","-",0)
assert(inspected:find("\tcomplete\tserver_ack",1,true))
assert(inspected:find("field\thealth\t79",1,true))
assert(inspected:find("field\thunger\t0.1",1,true))
assert(inspected:find("field\tinjured_body_parts\t1",1,true))
assert(inspected:find("field\tinventory_count\t0",1,true))
local granted=issue(string.rep("b",32),"grant","Base.Bandage",2)
assert(granted:find("\tcomplete\tserver_ack",1,true))
assert(#items==2 and adds==2)
assert(items[1]:getModData().SiegerStoryToken:find("admin_player_ops",1,true))
local granted_id=string.rep("b",32)
dofile(runtime)
for i=1,130 do events.tick() end
assert(#items==2 and adds==2,"Duplicated item grant after Lua reload")
local token=items[1]:getModData().SiegerStoryToken
local removed=issue(string.rep("c",32),"remove-tagged",token,1)
assert(removed:find("\tcomplete\tserver_ack",1,true))
assert(#items==1 and removes==1)
local healed=issue(string.rep("d",32),"heal","-",0)
assert(healed:find("\tcomplete\tserver_ack",1,true))
assert(body1.health==100 and body2.health==100)
-- If the server receives an unknown operation, it must not add/remove anything.
files["SiegerStoryPlayerRequest.txt"]="v1\t"..string.rep("e",32)..
    "\tstory_test\tadmin\trun_lua\tBase.Bandage\t1\n"
for i=1,130 do events.tick() end
assert(#items==1 and adds==2 and removes==1)
-- Simulate ambiguous mutation: last guard ID exists but last result was lost.
local failedId=string.rep("f",32)
files["SiegerStoryPlayerGuard.txt"]=failedId.."\tstory_test\tadmin\tgrant\n"
local denied=issue(failedId,"grant","Base.Bandage",1)
assert(denied:find("\terror\tserver_side_error_review_logs",1,true))
assert(#items==1)
print("PASS: scoped player snapshot/grant/remove-tagged/heal, replay guard and forbidden ops")
