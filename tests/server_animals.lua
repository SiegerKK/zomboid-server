local runtime=arg and arg[1]
local files,update,stamp,actors,players
local source=_serverSource or assert(io.open(runtime)):read('*a')
local function list(a)return {size=function()return #a end,get=function(_,i)return a[i+1]end}end
local function start()
 files={};stamp=1790000000000
 SiegerServerModuleRevision=nil
 SiegerServerBootstrap={world='story_test',boot='11111111-1111-1111-1111-111111111111',revision='animals-v1',game_version='42.21'}
 isClient=function()return false end
 getTimestampMs=function()return stamp end
 Events={OnTickEvenPaused={Add=function(fn)update=fn end}}
 getFileReader=function(name)
  local a=files[name];if not a then return nil end
  local seen=false;return {readLine=function()if seen then return nil end;seen=true;return a:match('([^\n]+)')end,close=function()end}
 end
 getFileWriter=function(name)
  return {write=function(_,v)files[name]=v end,close=function()end}
 end
 players={{getUsername=function()return 'admin'end,getX=function()return 10 end,getY=function()return 20 end,getZ=function()return 0 end}}
 actors={}
 getOnlinePlayers=function()return list(players)end
 getCell=function()return {getAnimals=function()return list(actors)end}end
 assert(loadstring(source,'SiegerServer.lua'))()
 assert(SiegerServerModuleRevision=='animals-v1')
end
local function animal(x,y)
 return {getSquare=function()return {}end,getX=function()return x end,getY=function()return y end,getZ=function()return 0 end,
 getAnimalType=function()return 'cow'end,getAnimalID=function()return 5 end,getHealth=function()return 1 end,isDead=function()return false end,
 isBaby=function()return true end,getAge=function()return 3 end}
end
local function request(id,who,r,expires,boot)
 files.SiegerServerAnimalsRequest=nil
 files['SiegerServerAnimalsRequest.txt']=table.concat({'v1',string.rep(id,32),'story_test',who or'admin',tostring(r or 100),string.format('%.0f',expires or(stamp+30000)),boot or'11111111-1111-1111-1111-111111111111'},'\t')..'\n'
 stamp=stamp+1100;for i=1,5 do update()end
 return files['SiegerServerAnimalsResult.txt']or''
end
start();actors={animal(13,24),animal(200,200),animal(10,20)}
local result=request('a')
assert(result:find('"count":2',1,true)and result:find('"distance_tiles_2d":5',1,true),result)
assert(result:find('"dead":false',1,true)and result:find('"baby":true',1,true),result)
assert(result:find('"status":"complete"',1,true),result)
local same=files['SiegerServerAnimalsResult.txt'];stamp=stamp+1100;update();assert(same==files['SiegerServerAnimalsResult.txt'],'replay')
assert(request('b','missing'):find('"status":"error"',1,true))
assert(request('c','admin',0):find('"status":"error"',1,true))
assert(request('d','admin',100,stamp-100):find('"status":"error"',1,true))
start();actors={animal(13,24)};request('e','admin',100,nil,'22222222-2222-2222-2222-222222222222')
assert(not files['SiegerServerAnimalsResult.txt'],'wrong boot must not execute')
start();local bad=animal(10,20);bad.getX=function()error('bad entity')end;actors={bad}
assert(request('f'):find('"status":"partial"',1,true),'entity error must not masquerade as zero')
start();for i=1,10001 do actors[i]=animal(10,20)end
assert(request('a'):find('"status":"error"',1,true),'budget must fail explicitly')
print('PASS: server-only animals counts, distance, booleans, replay, expiry, boot, missing player and partial errors')
