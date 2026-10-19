-- Engine-shaped read-only fixture. Real-game AI/network acceptance is separate.
local runtime=arg[1]or'story/runtime/SiegerAdminZombieDebug.lua'
local files,callback={},nil
local now=1792400000000
local calls=0
local states={}
local exported={}
local players={}
local age=24.5;local simulate=false
local function list(t)return{size=function()return#t end,get=function(_,i)return t[i+1]end}end
getTimestampMs=function()return now end
isClient=function()return false end
SiegerStoryScenes={world='story_test'}
Events={OnTickEvenPaused={Add=function(f)callback=f end}}
getFileReader=function(name)
 local text=files[name];if not text then return nil end
 local index=1
 return{readLine=function()
  if index>#text then return nil end
  local pos=text:find('\n',index,true);local value=text:sub(index,pos and pos-1 or#text);index=pos and pos+1 or#text+1;return value
 end,close=function()end}
end
getFileWriter=function(name,create,append)
 local text=append and(files[name]or'')or''
 return{write=function(_,s)text=text..s end,close=function()files[name]=text end}
end
getOnlinePlayers=function()return list(players)end
local time={getYear=function()return 1993 end,getMonth=function()return 11 end,getDay=function()return 0 end,getTimeOfDay=function()return 7.5 end,getNight=function()return 0.25 end,getWorldAgeHours=function()return age end}
getGameTime=function()return time end
getCore=function()return{getVersionNumber=function()return'42.21.0'end}end
SandboxVars={TLOU_infected={HideIndoors=true,WanderAtNight=true,OnlyUnexplored=false}}
local hide=function()error('DO NOT invoke AI behavior')end
local tlou={HideIndoors=hide,MaxDistanceToCheck=50,HideIndoorsUpdates=36}
ZomboidForge={NonPersistentZData={},ZTypes={TLOU_Stalker={onTick={hide}}},GetZType=function()error('FORBIDDEN cache initialization')end}
getLoadedLuaCount=function()return 1 end
getLoadedLua=function()return'media/lua/shared/TLOU_infected_module.lua'end
require=function(name)assert(name=='TLOU_infected_module');return tlou end
instanceof=function(value,kind)return value and value.kind==kind end
local building={getDef=function()return{getX=function()return 100 end,getY=function()return 100 end,getW=function()return 10 end,getH=function()return 10 end}end}
local room={getRoomDef=function()return{getX=function()return 101 end,getY=function()return 101 end,getW=function()return 5 end,getH=function()return 5 end,getZ=function()return 0 end}end}
local function zombie(id,x)
 local z={kind='IsoZombie',id=id,x=x,y=100,z=0,state='IdleState',health=1.5,inside=false,moving=false,alive=true,timeSinceSeenFlesh=4320,timeSinceRespondToSound=2}
 z.getX=function(self)if self.bad then error('getter_failed')end;return self.x end
 z.getY=function(self)return self.y end;z.getZ=function(self)return self.z end
 z.getOnlineID=function(self)return self.id end
 z.getHealth=function(self)return self.health end
 z.isAlive=function(self)return self.alive end;z.isMoving=function(self)return self.moving end
 z.isCrawling=function()return false end;z.isOnFloor=function()return false end;z.isUseless=function()return false end
 z.getCurrentStateName=function(self)return self.state end;z.getPreviousStateName=function()return'IdleState'end
 z.getCurrentSquare=function(self)return{getRoom=function()return self.inside and room or nil end}end
 z.getBuilding=function(self)return self.inside and building or nil end
 z.getTarget=function(self)return self.target end
 z.getThumpTarget=function()return nil end
 z.getPathFindBehavior2=function(self)return{getTargetX=function()return self.x+5 end,getTargetY=function()return 105 end,getTargetZ=function()return 0 end,getPathLength=function()return 10 end,getIsCancelled=function()return false end,isMovingUsingPathFind=function()return self.moving end}end
 z.setHealth=function()error('FORBIDDEN setter')end
 ZomboidForge.NonPersistentZData[z]={ZType='TLOU_Stalker'}
 return z
end
local a,b=zombie(7,100),zombie(7,110)
local loaded={a,b}
getCell=function()calls=calls+1;return{getZombieList=function()return list(loaded)end}end
local function reload()dofile(runtime);assert(callback)end
reload()
for _=1,120 do now=now+10;callback()end
assert(calls==0,'idle collector accessed world')
local index=0
local function start(mode,seconds,interval,maxbytes,maxrows,maxz,defer)
 index=index+1;now=now+1100
 local id=string.format('%032x',index)
 files['SiegerAdminZombieDebugRequest.txt']=table.concat({'v1',id,'story_test',mode,tostring(seconds or 0),tostring(interval or 1000),tostring(maxbytes or 1048576),tostring(maxrows or 10000),tostring(maxz or 10000),string.format('%.0f',now+30000),'-','end'},'\t')..'\n'
 if not defer then callback()end;return id
end
local function status()return files['SiegerAdminZombieDebugStatus.txt']or''end
local function trace(id)return files['SiegerAdminZombieDebug-'..id..'.txt']or''end
local function step(ms)now=now+ms;if simulate then age=age+ms/1000000 end;callback()end
local function keep(name,id)exported[name]=trace(id)end
local first=start('snapshot')
assert(status():find('\tcomplete\t',1,true));assert(trace(first):find('"inside":false',1,true));assert(trace(first):find('"bound":true',1,true))
assert(trace(first):find('"timestamp_ms":1792400002300',1,true),'wall ms precision lost')
assert(trace(first):find(first..':1',1,true)and trace(first):find(first..':2',1,true),'online ID collision merged objects')
keep('snapshot',first)
local saved=calls;step(2000);assert(calls==saved,'snapshot replayed')
local id=start('record',3)
a.x=102;a.inside=true;a.state='PathFindState';a.moving=true
local c=zombie(7,120);loaded={a,c};step(1000)
loaded={c};c.x=121;step(1000)
step(1000)
assert(status():find('\tcomplete\t',1,true));assert(trace(id):find('left_loaded_list_not_proof_of_death',1,true))
assert(trace(id):find('"kind":"lost"',1,true));keep('record',id)
local stopped=start('record',10);files['SiegerAdminZombieDebugStop.txt']=stopped..'\n';step(100)
assert(status():find('\tstopped\t',1,true));keep('stopped',stopped)
local pending=start('record',10,1000,1048576,10000,10000,true);saved=calls
files['SiegerAdminZombieDebugStop.txt']=pending..'\n';step(1)
assert(status():find('operator_stop_before_sampling',1,true));assert(calls==saved);keep('pending_stopped',pending)
local interrupted=start('record',10);saved=calls;reload();step(100)
assert(status():find('\tinterrupted\t',1,true));assert(calls==saved,'restart resumed capture');keep('interrupted',interrupted)
loaded={a,b};local limited=start('snapshot',0,1000,1048576,10000,1)
assert(status():find('\tlimited\t',1,true));assert(trace(limited):find('"observed_slots":2',1,true));keep('limited',limited)
local many={};for i=1,100 do many[i]=zombie(i,100+i)end;loaded=many
local bytes=start('snapshot',0,1000,65536)
assert(status():find('\tlimited\t',1,true));keep('byte_limited',bytes)
local rowlimited=start('snapshot',0,1000,1048576,100,10000)
assert(status():find('\tlimited\t',1,true));keep('row_limited',rowlimited)
loaded={a,b};a.bad=true
local bad=start('snapshot');assert(status():find('\terror\t',1,true));keep('entity_error',bad);a.bad=false
-- Missing optional APIs stay explicit null/unavailable, not fabricated zero.
local previous=b.getHealth;b.getHealth=nil
local optional=start('snapshot');assert(status():find('\tcomplete\t',1,true));assert(trace(optional):find('"health":null',1,true));keep('optional',optional);b.getHealth=previous
local savedBuilding=b.getBuilding;b.getBuilding=nil
local unknown=start('snapshot');assert(trace(unknown):find('"inside":null',1,true));keep('unknown_building',unknown);b.getBuilding=savedBuilding
-- Same object remains identifiable across a temporary missing-list sample;
-- an observed read error does not manufacture a lost/unloaded event.
local gaps=start('record',4)
a.bad=true;step(1000);a.bad=false;step(1000);step(2000)
assert(status():find('\terror\t',1,true));keep('gap',gaps)
-- Paused clocks must not generate a fake stuck-path diagnosis.
loaded={a};a.state='PathFindState';a.moving=false;a.inside=false
local paused=start('record',12)
for _=1,12 do step(1000)end;keep('paused_path',paused)
simulate=true
local stalled=start('record',12)
for _=1,12 do step(1000)end;keep('stationary_path',stalled);simulate=false
local expired=start('record',10,1000,1048576,10000,10000,true);saved=calls
files['SiegerAdminZombieDebugRequest.txt']=files['SiegerAdminZombieDebugRequest.txt']:gsub('\t%d+\t%-\tend\n$','\t1\t-\tend\n')
step(1);assert(status():find('expired_request',1,true));assert(calls==saved);keep('expired',expired)
local original=trace(first)
files['SiegerAdminZombieDebugRequest.txt']=table.concat({'v1',first,'story_test','snapshot','0','1000','1048576','10000','10000',string.format('%.0f',now+30000),'-','end'},'\t')..'\n'
step(1100);assert(status():find('request_log_exists',1,true));assert(trace(first)==original,'existing trace overwritten')
-- Client must register nothing; another world must not access live world data.
local oldcb=callback;isClient=function()return true end;reload();assert(callback==oldcb);isClient=function()return false end
SiegerStoryScenes.world='road_home';saved=calls;start('snapshot');assert(calls==saved)
-- Test-only exposure: no test API is exported by the production runtime.
_debugTraces=exported
_firstScanData=exported.record
if arg[2]then
 for name,body in pairs(exported)do local f=assert(io.open(arg[2]..'/'..name..'.txt','wb'));f:write(body);f:close()end
end
print('PASS: zombie debug fixture: idle, identity collisions, building/state changes, timed completion, stop, restart, limits and getter failures')
