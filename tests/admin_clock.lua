local files,callback={},nil
local now=100000
local count=0
local clock={year=1993,month=11,day=0,hour=21,nights=3}
for _,f in ipairs({'Year','Month','Day','TimeOfDay','NightsSurvived'})do
 local k=({Year='year',Month='month',Day='day',TimeOfDay='hour',NightsSurvived='nights'})[f]
 clock['get'..f]=function(self)return self[k]end
 clock['set'..f]=function(self,v)self[k]=v end
end
clock.setLastTimeOfDay=function(self,v)self.last=v end
getGameTime=function()return clock end
getTimestampMs=function()return now end
getOnlinePlayers=function()return{size=function()return count end}end
isClient=function()return false end
SiegerStoryScenes={world='story_test'}
Events={OnTickEvenPaused={Add=function(f)callback=f end}}
getFileReader=function(name)
 if not files[name]then return nil end
 local called=false
 return{readLine=function()if called then return nil end;called=true;return files[name]:gsub('\n$','')end,close=function()end}
end
getFileWriter=function(name)
 local text=''
 return{write=function(_,s)text=text..s end,close=function()files[name]=text end}
end
local runtime=arg[1]or'story/runtime/SiegerAdminClock.lua'
dofile(runtime);assert(callback)
local index=0
local function issue(op,minutes,allow,expiry)
 index=index+1;now=now+1100
 local id=string.format('%032x',index)
 files.SiegerAdminClockRequest= nil
 files['SiegerAdminClockRequest.txt']=table.concat({'v1',id,'story_test',op,tostring(minutes),tostring(expiry or now+30000),allow and'1'or'0','end'},'\t')..'\n'
 callback()
 return files['SiegerAdminClockResult.txt']or'',id
end
local r,id=issue('set',450)
assert(r:find('\tcomplete\t',1,true));assert(clock.hour==7.5 and clock.last==7.5)
assert(clock.year==1993 and clock.month==11 and clock.day==0 and clock.nights==3)
clock.hour=8;now=now+1100;callback();assert(clock.hour==8) -- no duplicate
-- Restart also sees the durable guard; never reapplies stale request.
dofile(runtime);now=now+1100;callback();assert(clock.hour==8)
count=1;r=issue('set',450);assert(r:find('\terror\t',1,true));assert(clock.hour==8)
r=issue('set',450,true);assert(r:find('\tcomplete\t',1,true));assert(clock.hour==7.5)
count=0;clock.year=1996;clock.month=1;clock.day=27;clock.hour=23.5;clock.nights=10
r=issue('advance',120);assert(r:find('\tcomplete\t',1,true))
assert(clock.year==1996 and clock.month==1 and clock.day==28 and clock.hour==1.5 and clock.nights==10)
r=issue('advance',360);assert(clock.hour==7.5 and clock.nights==11)
clock.year=1993;clock.month=11;clock.day=30;clock.hour=23.5
r=issue('advance',60);assert(clock.year==1994 and clock.month==0 and clock.day==0 and clock.hour==0.5)
local before=clock.hour;r=issue('set',450,false,now-10000);assert(r:find('\terror\t',1,true));assert(clock.hour==before)
r=issue('show',0);assert(r:find('\tcomplete\t',1,true));assert(clock.hour==before)
SiegerStoryScenes.world='road_home';r=issue('set',450);assert(clock.hour==before)
print('PASS: online clock empty-paused event, same-day set, rollover/leap/year, explicit players, expiry and restart replay')
