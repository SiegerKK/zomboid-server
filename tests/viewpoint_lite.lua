-- Plain Lua 5.1 harness, with no proprietary Viewpoint classes.
local file=assert(arg[1], "expected client script")
local boot,start,tick,exit
local actions={}, option={value=false}
function option:getValue() return self.value end
Events={
  OnGameBoot={Add=function(f)boot=f end},
  OnGameStart={Add=function(f)start=f end},
  OnTick={Add=function(f)tick=f end},
  OnGameExit={Add=function(f)exit=f end}
}
isServer=function() return false end
local now=1000
getTimestampMs=function() return now end
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
ViewpointInteract={
  actions=actions,
  harvest=function(player,object)
    calls=calls+1
    ViewpointInteract.actions={player=player,object=object,step=calls}
  end,
  run=function() runs=runs+1;return "ok" end
}
dofile(file)
assert(boot and start and tick and exit)
boot();start()
local a,b={},{}
local originalRun=ViewpointInteract.run
-- Disabled until the human explicitly opts in.
ViewpointInteract.harvest(a,b)
ViewpointInteract.harvest(a,b)
assert(calls==2,"Default OFF must behave exactly like Viewpoint")
option.value=true
now=1010
ViewpointInteract.harvest(a,b)
local expected=ViewpointInteract.actions
assert(calls==3)
now=1030
ViewpointInteract.harvest(a,b)
assert(calls==3 and ViewpointInteract.actions==expected,
       "Same player/target and unchanged published menu should skip rebuild")
-- Even inside the same 50ms, changing targets must always recompute.
ViewpointInteract.harvest(a,{})
assert(calls==4,"Different object must invalidate")
-- An action is a mutation; invalidate immediately.
assert(ViewpointInteract.run()=="ok" and runs==1)
ViewpointInteract.harvest(a,b)
assert(calls==5,"Executed action must invalidate cached option closure")
-- External menu modification invalidates the optimization.
ViewpointInteract.actions={}
now=1040
ViewpointInteract.harvest(a,b)
assert(calls==6,"Third-party replacement of action list must invalidate cache")
-- Time expiry, reversal, and disabled flag restore original behavior.
now=1110;tick()
ViewpointInteract.harvest(a,b)
assert(calls==7,"Expired cache must recompute")
now=100;tick()
ViewpointInteract.harvest(a,b)
assert(calls==8,"Clock rewind must recompute")
ViewpointFixes={}
ViewpointInteract.harvest(a,b)
assert(calls==9,"Existing interaction addon disables coalescing")
ViewpointFixes=nil
option.value=false
ViewpointInteract.harvest(a,b)
assert(calls==10,"Disabling option restores immediate original behavior")
option.value=true
ViewpointInteract.harvest(a,b)
assert(calls==11)
exit()
assert(SiegerViewpointLite.stats().hits==1,"One optimization hit, no invented metrics")
print("PASS Viewpoint Lite: opt-in, bounded cache, target/action/clock invalidation and conflict fallback")
