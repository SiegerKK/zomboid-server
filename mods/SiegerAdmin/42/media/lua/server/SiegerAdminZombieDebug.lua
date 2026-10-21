-- On-demand server observations only. No setters, Forge cache initialization,
-- forced chunks, AI hooks, client commands, inventory or player-name collection.
if isClient and isClient() then return end
local REQUEST='SiegerAdminZombieDebugRequest.txt'
local STATUS='SiegerAdminZombieDebugStatus.txt'
local STOP='SiegerAdminZombieDebugStop.txt'
local GUARD='SiegerAdminZombieDebugGuard.txt'
local VERSION='zdebug-v1'
local NULL={}
local job=nil
local processed=nil
local initialized=false
local lastPoll=nil
local function arr(t)return setmetatable(t or{},{__array=true})end
local function finite(n)return type(n)=='number'and n==n and n>-1e15 and n<1e15 end
local function ascii(s,max)
 if type(s)~='string'then return nil end
 return s:sub(1,max or 96):gsub('[^ -~]','?')
end
local function json(v)
 if v==NULL or v==nil then return'null'end
 local kind=type(v)
 if kind=='boolean'then return v and'true'or'false'end
 if kind=='number'then assert(finite(v),'nonfinite_json');return string.format('%.17g',v)end
 if kind=='string'then
  return '"'..v:gsub('[%z\1-\31\\"]',function(c)
   if c=='"'then return'\\"'elseif c=='\\'then return'\\\\'end
   return string.format('\\u%04x',string.byte(c))end)..'"'
 end
 assert(kind=='table','invalid_json_type')
 local parts={}
 if getmetatable(v)and getmetatable(v).__array then
  for i=1,#v do parts[#parts+1]=json(v[i])end
  return'['..table.concat(parts,',')..']'
 end
 local keys={};for k in pairs(v)do assert(type(k)=='string');keys[#keys+1]=k end
 table.sort(keys)
 for _,k in ipairs(keys)do parts[#parts+1]=json(k)..':'..json(v[k])end
 return'{'..table.concat(parts,',')..'}'
end
local function readLine(name)
 local reader=getFileReader(name,false);if not reader then return nil end
 local line=reader:readLine();local extra=reader:readLine();reader:close()
 assert(not extra and(not line or#line<=1024),'invalid_control_file')
 return line
end
local function writeLine(name,line,append)
 local writer=getFileWriter(name,true,append or false);assert(writer,'writer_unavailable')
 local ok,err=pcall(function()writer:write(line..'\n')end);writer:close();if not ok then error(err)end
end
local function validID(id)return type(id)=='string'and#id==32 and id:match('^[0-9a-f]+$')~=nil end
local function validWorld(s)return type(s)=='string'and#s<=40 and s:match('^[A-Za-z0-9][A-Za-z0-9_%-]*$')~=nil end
local function split(line)
 local fields={};for f in(line..'\t'):gmatch('(.-)\t')do fields[#fields+1]=f end;return fields
end
local function integer(s,minimum,maximum)
 if type(s)~='string'or not s:match('^%d+$')then return nil end
 local n=tonumber(s);if n and n>=minimum and n<=maximum and n==math.floor(n)then return n end
end
local function logfile(id)return'SiegerAdminZombieDebug-'..id..'.txt'end
local function status(state,reason)
 writeLine(STATUS,table.concat({'v1',job.id,job.world,state,reason,tostring(job.samples),tostring(job.rows),tostring(job.bytes),logfile(job.id),string.format('%.0f',getTimestampMs())},'\t'))
end
local function emit(value,terminal)
 local line=json(value)..'\n'
 if not terminal then
  if job.rows>=job.maxRows-1 then error('limit_records')end
  if job.bytes+#line>job.maxBytes-4096 then error('limit_bytes')end
 end
 assert(job.writer,'log_writer_missing');job.writer:write(line)
 job.rows=job.rows+1;job.bytes=job.bytes+#line
end
local function openLog()
 job.writer=getFileWriter(logfile(job.id),true,true);assert(job.writer,'log_writer_unavailable')
end
local function closeLog()
 if job and job.writer then job.writer:close();job.writer=nil end
end
local function finish(state,reason,now)
 closeLog();openLog()
 emit({kind='end',id=job.id,status=state,reason=reason,samples=job.samples,
  rows_before_end=job.rows,bytes_before_end=job.bytes,elapsed_ms=state=='interrupted'and NULL or math.max(0,now-job.started),
  timestamp_ms=now,missed_intervals=job.missed,entity_errors=job.errors,
  scope='server_loaded_zombies_only'},true)
 closeLog();status(state,reason);job=nil
end
local function loadedModule(name)
 -- Fixed-name read of an ALREADY loaded return. Never initialize Forge/TLOU.
 if package and package.loaded and type(package.loaded[name])=='table'then return package.loaded[name]end
 if getLoadedLuaCount and getLoadedLua and require then
  local count=getLoadedLuaCount()
  if type(count)=='number'and count>=0 and count<=100000 then
   for i=0,count-1 do
    local path=getLoadedLua(i)
    if type(path)=='string'and(path==name..'.lua'or path:gsub('\\','/'):match('/'..name..'%.lua$'))then
     local ok,value=pcall(require,name);if ok and type(value)=='table'then return value end;return nil
    end
   end
  end
 end
 return nil
end
local function optional(object,method,missing,key)
 local ok,value,found=pcall(function()
  if object and object[method]then return object[method](object),true end
  return nil,false
 end)
 if not ok or not found then if missing then missing[#missing+1]=key or method end;return nil,false end
 return value,true
end
local function num(object,method,missing,key)
 local value=optional(object,method,missing,key)
 if finite(value)then return value end
 if value~=nil and missing then missing[#missing+1]=key or method end
 return NULL
end
local function bool(object,method,missing,key)
 local value=optional(object,method,missing,key)
 if type(value)=='boolean'then return value end
 return NULL
end
local function bounds(def,room)
 if not def then return NULL end
 local x,y,w,h=optional(def,'getX'),optional(def,'getY'),optional(def,'getW'),optional(def,'getH')
 if not(finite(x)and finite(y)and finite(w)and finite(h))then return NULL end
 local z=room and optional(def,'getZ')or nil
 local key=table.concat({x,y,w,h,finite(z)and z or'-'},':')
 return{key=key,x=x,y=y,w=w,h=h,z=finite(z)and z or NULL}
end
local function context()
 local t=getGameTime();assert(t,'game_time_missing')
 local players=getOnlinePlayers();assert(players and players.size,'players_api_missing')
 local s=SandboxVars and SandboxVars.TLOU_infected or{}
 local tlou=job.tlou
 return{timestamp_ms=getTimestampMs(),game={year=num(t,'getYear'),month_zero=num(t,'getMonth'),
  day_zero=num(t,'getDay'),hour=num(t,'getTimeOfDay'),night_strength=num(t,'getNight'),
  world_age_hours=num(t,'getWorldAgeHours')},players=players:size(),
  rules={HideIndoors=s.HideIndoors==nil and NULL or s.HideIndoors,
   WanderAtNight=s.WanderAtNight==nil and NULL or s.WanderAtNight,
   OnlyUnexplored=s.OnlyUnexplored==nil and NULL or s.OnlyUnexplored,
   search_radius=tlou and tlou.MaxDistanceToCheck or NULL,
   effective_hide_updates=tlou and tlou.HideIndoorsUpdates or NULL}}
end
local function fieldNumber(object,key)
 local ok,value=pcall(function()return object[key]end)
 return ok and finite(value)and value or NULL
end
local function describeTarget(target)
 if not target then return NULL end
 local kind='other'
 if instanceof then
  if instanceof(target,'IsoPlayer')then kind='player'elseif instanceof(target,'IsoZombie')then kind='zombie'end
 end
 return{kind=kind,tracking_id=job.identities[target]or NULL,online_id=num(target,'getOnlineID'),x=num(target,'getX'),y=num(target,'getY'),z=num(target,'getZ')}
end
local function anchor()
 if job.player=='-'then return NULL end
 local list=getOnlinePlayers()
 for i=0,list:size()-1 do
  local p=list:get(i)
  if p and p:getUsername()==job.player then
   return{x=num(p,'getX'),y=num(p,'getY'),z=num(p,'getZ'),
    invisible=bool(p,'isInvisible'),ghost=bool(p,'isGhostMode'),god=bool(p,'isGodMod'),
    sneaking=bool(p,'isSneaking'),running=bool(p,'isRunning'),sprinting=bool(p,'isSprinting')}
  end
 end
 return NULL
end
local function row(z,slot,meta,origin)
 local missing=arr();local identity=job.identities[z]
 if not identity then job.nextID=job.nextID+1;identity=job.id..':'..job.nextID;job.identities[z]=identity end
 local x,y,zz=num(z,'getX',missing),num(z,'getY',missing),num(z,'getZ',missing)
 assert(x~=NULL and y~=NULL and zz~=NULL,'coordinates_unavailable')
 local cache=job.forge and job.forge.NonPersistentZData
 local record=type(cache)=='table'and cache[z]or nil
 local ztype=type(record)=='table'and ascii(record.ZType,128)or nil
 local definition=ztype and job.forge and job.forge.ZTypes and job.forge.ZTypes[ztype]or nil
 local applies=NULL
 if type(definition)=='table'and job.tlou and type(job.tlou.HideIndoors)=='function'then
  applies=false
  if type(definition.onTick)=='table'then for _,f in ipairs(definition.onTick)do if f==job.tlou.HideIndoors then applies=true end end end
 end
 local sq=optional(z,'getCurrentSquare',missing)
 local building,buildingKnown=optional(z,'getBuilding',missing)
 local b=building and bounds(optional(building,'getDef'),false)or NULL
 local room=sq and optional(sq,'getRoom')or nil
 local r=room and bounds(optional(room,'getRoomDef'),true)or NULL
 local inside=NULL
 -- Failed getters must not turn unknown into outdoors/false.
 if sq and buildingKnown then inside=building~=nil end
 local target,targetKnown=optional(z,'getTarget',missing)
 local moving=bool(z,'isMoving',missing)
 local pfb=optional(z,'getPathFindBehavior2',missing)
 local rawState=optional(z,'getCurrentStateName',missing)
 local rawTime=nil
 local ok,value=pcall(function()return z.timeSinceSeenFlesh end)
 if ok and finite(value)then rawTime=value end
 local timer=meta.rules.effective_hide_updates
 local gate=NULL
 if rawTime and finite(timer)and timer>0 then gate=math.floor(rawTime/120)%timer==0 end
 local why='unknown'
 if applies==false then why='not_bound'
 elseif applies==true then
  if inside==true then why='already_inside'
  elseif not targetKnown then why='unknown'
  elseif target then why='has_target'
  elseif moving==true then why='moving'
  elseif gate==false then why='timer_gate'
  elseif inside==false and moving==false and gate==true then why='outside_idle_candidate'end
 end
 local phase='unknown';local night=meta.game.night_strength
 if finite(night)and type(meta.rules.WanderAtNight)=='boolean'then
  phase=(night<0.5 or not meta.rules.WanderAtNight)and'seek_building'or'wander'
 end
 local owner=nil
 pcall(function()owner=z.authOwnerPlayer end)
 local thump,thumpKnown=optional(z,'getThumpTarget',missing)
 local thumping=NULL;if thumpKnown then thumping=thump~=nil end
 local onlineID=num(z,'getOnlineID',missing)
 local data={kind='zombie',id=job.id,sample=job.samples,tracking_id=identity,slot=slot,
  online_id=onlineID,type=ztype or'unknown',x=x,y=y,z=zz,
  health=num(z,'getHealth',missing),alive=bool(z,'isAlive',missing),moving=moving,
  state=ascii(rawState)or NULL,previous_state=ascii((optional(z,'getPreviousStateName')))or NULL,
  crawling=bool(z,'isCrawling',missing),on_floor=bool(z,'isOnFloor',missing),useless=bool(z,'isUseless',missing),
  square_loaded=sq~=nil,inside=inside,building=b,room=r,target=describeTarget(target),
  thumping=thumping,path=pfb and{x=num(pfb,'getTargetX'),y=num(pfb,'getTargetY'),z=num(pfb,'getTargetZ'),
   length=num(pfb,'getPathLength'),cancelled=bool(pfb,'getIsCancelled'),using=bool(pfb,'isMovingUsingPathFind')}or NULL,
  owner_player_online_id=owner and num(owner,'getOnlineID')or NULL,
  time_since_seen_flesh=rawTime or NULL,time_since_respond_sound=fieldNumber(z,'timeSinceRespondToSound'),
  hide_rule={bound=applies,branch=phase,eligibility=why,timer_gate=gate,
   interpretation='reference_rule_inference_not_proven_AI_cause'},unavailable=missing}
 if origin~=NULL and finite(origin.x)and finite(origin.y)then
  data.distance_tiles_2d=math.sqrt((x-origin.x)^2+(y-origin.y)^2)
 end
 return data
end
local function sample(now)
 local started=getTimestampMs()
 local list=getCell():getZombieList();assert(list and list.size and list.get,'zombie_list_missing')
 local size=list:size();assert(finite(size)and size>=0 and size==math.floor(size),'invalid_list_size')
 if size>job.maxZombies then
  openLog();emit({kind='coverage_limit',id=job.id,observed_slots=size,max_zombies=job.maxZombies});closeLog()
  error('limit_zombies')
 end
 job.samples=job.samples+1
 local late=math.max(0,now-job.due);local missed=math.floor(late/job.interval);job.missed=job.missed+missed
 local meta=context();local origin=anchor();local current={};local valid,nulls,errors=0,0,0
 openLog()
 emit({kind='sample',id=job.id,seq=job.samples,expected_slots=size,context=meta,
  anchor=origin,late_by_ms=late,missed_intervals=missed})
 for i=0,size-1 do
  local z=list:get(i)
  if z then
   local ok,data=pcall(row,z,i,meta,origin)
   if ok then
    emit(data);valid=valid+1;current[data.tracking_id]=true
   else
    errors=errors+1
    local known=job.identities[z];if known then current[known]=true end
    emit({kind='entity_error',id=job.id,sample=job.samples,slot=i,tracking_id=known or NULL,reason='entity_getter_failed'})
   end
  else nulls=nulls+1 end
 end
 for id in pairs(job.previous)do
  if not current[id]then emit({kind='lost',id=job.id,sample=job.samples,tracking_id=id,reason='left_loaded_list_not_proof_of_death'})end
 end
 job.previous=current;job.errors=job.errors+errors
 emit({kind='sample_end',id=job.id,seq=job.samples,inspected=valid,null_slots=nulls,errors=errors,
  elapsed_ms=math.max(0,getTimestampMs()-started),coverage_complete=valid+nulls==size and errors==0})
 closeLog();status('running','sampling')
 job.due=now+(missed+1)*job.interval-late
 -- Never run catch-up samples in a burst when collection itself is expensive.
 local finished=getTimestampMs()
 if job.due<=finished then job.due=finished+job.interval end
end
local function parse(line)
 if not line then return nil end
 local f=split(line)
 if #f~=12 or f[1]~='v1'or not validID(f[2])or not validWorld(f[3])or(f[4]~='snapshot'and f[4]~='record')or f[12]~='end'then return nil end
 local seconds=integer(f[5],0,1800);local interval=integer(f[6],100,60000)
 local bytes=integer(f[7],65536,268435456);local rows=integer(f[8],100,1000000)
 local zombies=integer(f[9],1,100000);local expiry=integer(f[10],1,9999999999999)
 if not(seconds and interval and bytes and rows and zombies and expiry)then return nil end
 if(f[4]=='snapshot'and seconds~=0)or(f[4]=='record'and seconds<1)then return nil end
 if f[11]~='-'and(not f[11]:match('^[A-Za-z0-9_][A-Za-z0-9_.%-]*$')or#f[11]>31)then return nil end
 return{id=f[2],world=f[3],mode=f[4],seconds=seconds,interval=interval,maxBytes=bytes,maxRows=rows,maxZombies=zombies,expiry=expiry,player=f[11]}
end
local function poll(now)
 if not initialized then
  processed=readLine(GUARD);assert(not processed or validID(processed),'invalid_debug_guard')
  local old=parse(readLine(REQUEST))
  if old and old.id==processed then
   local raw=readLine(STATUS);local fields=raw and split(raw)or{}
   if fields[2]==old.id and fields[4]=='running'then
    -- A restart never resumes the recorder or pretends its old trace completed.
    -- Preserve the raw prefix exactly. A crash may have occurred between
    -- log close and status update, so cached counters cannot frame a footer.
    writeLine(STATUS,table.concat({'v1',old.id,old.world,'interrupted',
     'server_runtime_restarted',fields[6],fields[7],fields[8],logfile(old.id),
     string.format('%.0f',now)},'\t'))
   end
  end
  initialized=true
 end
 if job then
  if now<job.lastNow then finish('error','clock_went_backwards',now);return end
  job.lastNow=now
  if readLine(STOP)==job.id then finish('stopped','operator_stop',now);return end
  if job.mode=='record'and now>=job.deadline then
   finish(job.errors>0 and'error'or'complete',job.errors>0 and'entity_errors'or'duration_elapsed',now);return
  end
  if now>=job.due then sample(now)end
  if job and job.mode=='snapshot'then finish(job.errors>0 and'error'or'complete',job.errors>0 and'entity_errors'or'snapshot_complete',now)end
  return
 end
 if lastPoll and now>=lastPoll and now-lastPoll<1000 then return end
 lastPoll=now
 local req=parse(readLine(REQUEST))
 if not req or req.id==processed or req.world~=SiegerStoryScenes.world then return end
 -- Durable one-shot guard before opening the log. No replay after any failure.
 writeLine(GUARD,req.id);assert(readLine(GUARD)==req.id,'guard_write_failed');processed=req.id
 job=req;job.started=now;job.lastNow=now;job.deadline=now+req.seconds*1000;job.due=now
 job.samples=0;job.rows=0;job.bytes=0;job.missed=0;job.errors=0;job.nextID=0
 job.identities=setmetatable({},{__mode='k'});job.previous={}
 local existing=getFileReader(logfile(req.id),false)
 if existing then existing:close();status('error','request_log_exists');job=nil;return end
 openLog()
 emit({kind='start',schema=1,id=req.id,world=req.world,version=VERSION,
  timestamp_ms=now,seconds=req.seconds,interval_ms=req.interval,max_bytes=req.maxBytes,
  max_records=req.maxRows,max_zombies=req.maxZombies,player=req.player,
  identity='Lua_object_lifetime_in_this_recording; online_ID_is_not_identity',
  source='server_observation; AI_owner_client_details_may_be_unavailable',
  type_source='existing_Forge_cache_only; unknown_is_not_proof_of_vanilla',
  game_version=getCore and ascii((optional(getCore(),'getVersionNumber')))or NULL})
 closeLog();status('running','starting')
 if now>req.expiry or now<req.expiry-60000 then finish('error','expired_request',now);return end
 if readLine(STOP)==req.id then finish('stopped','operator_stop_before_sampling',now);return end
 job.forge=type(ZomboidForge)=='table'and ZomboidForge or loadedModule('ZomboidForge_module')
 job.tlou=loadedModule('TLOU_infected_module')
 sample(now)
 if job.mode=='snapshot'then finish(job.errors>0 and'error'or'complete',job.errors>0 and'entity_errors'or'snapshot_complete',now)end
end
local function tick()
 if not SiegerStoryScenes or not validWorld(SiegerStoryScenes.world)then return end
 local now=getTimestampMs()
 local ok,err=pcall(poll,now)
 if not ok then
  local reason=tostring(err):match('limit_[a-z]+')or'collector_error'
  print('SIEGER_ADMIN_ZOMBIE_DEBUG ERROR '..reason)
  if job then
   local success=pcall(finish,reason:match('^limit_')and'limited'or'error',reason,now)
   if not success then
    closeLog();pcall(status,'error','log_write_failed');job=nil
   end
  end
 end
end
if Events and Events.OnTickEvenPaused then Events.OnTickEvenPaused.Add(tick)
else print('SIEGER_ADMIN_ZOMBIE_DEBUG ERROR required event unavailable')end
