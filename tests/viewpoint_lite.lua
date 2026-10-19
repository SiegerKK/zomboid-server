-- Lua 5.1 behavioral harness with the observed Viewpoint harvest API.
-- A successful harvest returns a table consumed by Java, not nil.
local file=assert(arg[1],"expected client script")
local boot,start,tick,exit
local option={value=false}
function option:getValue() return self.value end
Events={
  OnGameBoot={Add=function(f)boot=f end},
  OnGameStart={Add=function(f)start=f end},
  OnTick={Add=function(f)tick=f end},
  OnGameExit={Add=function(f)exit=f end}
}
isServer=function()return false end
local now=1000
getTimestampMs=function()return now end
PZAPI={ModOptions={
  create=function(_,id,label)
    assert(id=="SiegerViewpointLite")
    return {addTickBox=function(_,key,title,default,tooltip)
      assert(key=="cacheHarvest" and default==false and tooltip)
      return option
    end}
  end,
  load=function()end
}}
local calls,runs=0,0
local resultMode="success"
ViewpointInteract={
  actions={},
  harvest=function(player,object)
    calls=calls+1
    ViewpointInteract.actions={player=player,object=object,step=calls}
    if resultMode=="nil" then return nil end
    if resultMode=="why" then return {why="no context menu"} end
    return {title="Interaction",labels={"Take"},enabled={true},seen=1,step=calls}
  end,
  run=function()runs=runs+1;return "ok" end
}
dofile(file)
assert(boot and start and tick and exit)
boot();start()
local a,b={},{}
-- Disabled by default: untouched return values and two original executions.
local first=ViewpointInteract.harvest(a,b)
local second=ViewpointInteract.harvest(a,b)
assert(calls==2 and type(first)=="table" and type(second)=="table"
       and first~=second and first.labels[1]=="Take",
       "Default OFF must preserve the real harvest result")
option.value=true
now=1010
local actual=ViewpointInteract.harvest(a,b)
local actions=ViewpointInteract.actions
assert(calls==3 and actual.step==3)
now=1030
local hit=ViewpointInteract.harvest(a,b)
assert(calls==3 and hit==actual and ViewpointInteract.actions==actions,
       "Same player/target must reuse BOTH original result and actions")
-- Both identities are part of the cache key.
local differentTarget=ViewpointInteract.harvest(a,{})
assert(calls==4 and differentTarget~=actual,"Different object must invalidate")
local differentPlayer=ViewpointInteract.harvest({},b)
assert(calls==5 and differentPlayer~=differentTarget,"Different player must invalidate")
-- Running an action is a mutation: no cached result can survive.
assert(ViewpointInteract.run()=="ok" and runs==1)
local afterAction=ViewpointInteract.harvest(a,b)
assert(calls==6 and afterAction~=actual,"Executed action must invalidate result")
-- External code can replace the action table without replacing the target.
ViewpointInteract.actions={}
now=1040
assert(ViewpointInteract.harvest(a,b)~=afterAction and calls==7,
       "Replacing actions must invalidate")
-- Expiration and a clock reversal always invalidate.
now=1110;tick()
assert(ViewpointInteract.harvest(a,b).step==8 and calls==8)
now=100;tick()
assert(ViewpointInteract.harvest(a,b).step==9 and calls==9)
-- Known interaction mods bypass our cache; opt-out restores direct calls.
ViewpointFixes={}
assert(ViewpointInteract.harvest(a,b).step==10 and calls==10)
ViewpointFixes=nil
option.value=false
assert(ViewpointInteract.harvest(a,b).step==11 and calls==11)
option.value=true
assert(ViewpointInteract.harvest(a,b).step==12 and calls==12)
-- Non-success results are not cached: menu availability can change mid-frame.
SiegerViewpointLite.clear()
resultMode="nil";now=150
assert(ViewpointInteract.harvest(a,b)==nil)
assert(ViewpointInteract.harvest(a,b)==nil and calls==14,
       "Nil result must not be cached")
resultMode="why";now=160
local reason=ViewpointInteract.harvest(a,b)
assert(reason.why=="no context menu")
assert(ViewpointInteract.harvest(a,b)~=reason and calls==16,
       "Why-only menu result must not be cached")
resultMode="success";now=170
local resumed=ViewpointInteract.harvest(a,b)
assert(type(resumed)=="table" and resumed.seen==1 and calls==17,
       "Recovering normal menus must get a fresh success result")
exit()
local stats=SiegerViewpointLite.stats()
assert(stats.hits==1,"One real table-result cache hit in test")
assert(stats.misses>0 and stats.attempts==18,
       "Deterministic statistics count user calls, not allocation guesses")
print("PASS Viewpoint Lite: table result preserved; nil/error results bypass cache; bounded invalidation")
