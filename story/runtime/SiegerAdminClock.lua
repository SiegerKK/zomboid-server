-- B42.21 server-only bounded clock operations; never client-issued commands.
if isClient and isClient() then return end
local REQ,RESP,GUARD='SiegerAdminClockRequest.txt','SiegerAdminClockResult.txt','SiegerAdminClockGuard.txt'
local lastPoll=nil
local function read(name)
 local r=getFileReader(name,false);if not r then return nil end
 local line=r:readLine();local extra=r:readLine();r:close()
 if extra or (line and #line>512)then error('invalid_protocol_file')end
 return line
end
local function write(name,line)
 local w=getFileWriter(name,true,false);assert(w,'writer_missing');w:write(line..'\n');w:close()
end
local function split(line)
 local fields={};for f in (line..'\t'):gmatch('(.-)\t')do fields[#fields+1]=f end;return fields
end
local function snapshot(t)
 local h=t:getTimeOfDay();assert(type(h)=='number' and h==h and h>=0 and h<24,'invalid_game_clock')
 return {year=t:getYear(),month=t:getMonth(),day=t:getDay(),hour=h,nights=t:getNightsSurvived()}
end
local function date(s)return string.format('%04d-%02d-%02d',s.year,s.month+1,s.day+1)end
local function nextDate(s)
 local days={31,28,31,30,31,30,31,31,30,31,30,31}
 if s.year%4==0 and(s.year%100~=0 or s.year%400==0)then days[2]=29 end
 s.day=s.day+1
 if s.day>=days[s.month+1]then s.day=0;s.month=s.month+1 end
 if s.month==12 then s.month=0;s.year=s.year+1 end
end
local function poll()
 if not SiegerStoryScenes or SiegerStoryScenes.world~='story_test'then return end
 local raw=read(REQ);if not raw then return end
 local f=split(raw)
 if #f~=8 or f[1]~='v1' or #f[2]~=32 or not f[2]:match('^[0-9a-f]+$')or f[3]~='story_test'then return end
 local id,op=f[2],f[4]
 if op~='show'and op~='set'and op~='advance'then return end
 if not f[5]:match('^%d+$')or not f[6]:match('^%d+$')or not f[7]:match('^[01]$')or f[8]~='end'then return end
 local minutes,expires,allow=tonumber(f[5]),tonumber(f[6]),f[7]=='1'
 if minutes>1440 or(op=='set'and minutes>=1440)or(op=='advance'and minutes<1)or(op=='show'and minutes~=0)then return end
 local previous=read(GUARD)
 if previous then
  assert(previous:match('^[0-9a-f]+$')and #previous==32,'invalid_guard')
  if previous==id then return end
 end
 local before,after
 local ok,reason=pcall(function()
  assert(getTimestampMs()<=expires,'expired_request')
  assert(getTimestampMs()>=expires-60000,'invalid_request_expiry')
  local t=getGameTime();assert(t,'gametime_missing');before=snapshot(t)
  after={year=before.year,month=before.month,day=before.day,hour=before.hour,nights=before.nights}
  if op~='show'then
   local players=getOnlinePlayers();assert(players and players.size,'players_api_missing')
   assert(allow or players:size()==0,'players_connected')
   assert(t.setTimeOfDay and t.setLastTimeOfDay and t.setDay and t.setMonth and t.setYear and t.setNightsSurvived,'clock_api_missing')
   if op=='set'then after.hour=minutes/60 else
    local hours=minutes/60;after.hour=(before.hour+hours)%24
    if before.hour+hours>=24 then nextDate(after)end
    after.nights=before.nights+math.floor((before.hour-7+hours)/24)-math.floor((before.hour-7)/24)
   end
  end
  -- Persist and verify BEFORE any game-state change. A partial failure is never replayed.
  write(GUARD,id);assert(read(GUARD)==id,'guard_verification_failed')
  if op~='show'then
   t:setDay(after.day);t:setMonth(after.month);t:setYear(after.year);t:setNightsSurvived(after.nights)
   t:setLastTimeOfDay(after.hour);t:setTimeOfDay(after.hour)
   local actual=snapshot(t)
   assert(date(actual)==date(after)and math.abs(actual.hour-after.hour)<0.001 and actual.nights==after.nights,'clock_readback_failed')
   after=actual
  end
 end)
 if not ok then
  -- Do not retry a failed or potentially partial command on every tick/restart.
  write(GUARD,id)
  print('SIEGER_ADMIN_CLOCK ERROR id='..id..' reason='..tostring(reason))
 end
 local b,a=before or{},after or{}
 write(RESP,table.concat({'v1',id,'story_test',op,ok and'complete'or'error',ok and'game_clock_verified'or'review_server_logs',
  before and date(b)or'-',before and string.format('%.6f',b.hour)or'-',
  ok and date(a)or'-',ok and string.format('%.6f',a.hour)or'-',
  before and tostring(b.nights)or'-',ok and tostring(a.nights)or'-'},'\t'))
 print('SIEGER_ADMIN_CLOCK '..(ok and'complete'or'error')..' id='..id..' op='..op)
end
local function tick()
 local now=getTimestampMs()
 if lastPoll and now>=lastPoll and now-lastPoll<1000 then return end
 lastPoll=now
 local ok,err=pcall(poll);if not ok then print('SIEGER_ADMIN_CLOCK ERROR poll '..tostring(err))end
end
if Events and Events.OnTickEvenPaused then Events.OnTickEvenPaused.Add(tick)
else print('SIEGER_ADMIN_CLOCK ERROR OnTickEvenPaused unavailable; clock disabled')end
