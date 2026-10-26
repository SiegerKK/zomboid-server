-- Trusted server source outside MODS and the game's Lua-directory scan.
-- Loaded once by the existing ZombieBuddy lifecycle callback, never from requests.
if isClient and isClient() then return end
local config=SiegerServerBootstrap
assert(type(config)=='table' and config.revision=='animals-v1','missing trusted bootstrap')
local world,boot=config.world,config.boot
assert(type(world)=='string' and world:match('^[A-Za-z0-9][A-Za-z0-9_%-]*$'),'invalid world')
assert(type(boot)=='string' and #boot==36,'invalid boot')
if SiegerServerModuleRevision then error('server module already loaded')end
local REQ,RESP,GUARD='SiegerServerAnimalsRequest.txt','SiegerServerAnimalsResult.txt','SiegerServerAnimalsGuard.txt'
local job=nil
local nextPoll=0
local function q(value)
    if value==nil then return 'null'end
    return '"'..tostring(value):gsub('[%z\1-\31\\"]',function(c)
        if c=='"'or c=='\\'then return '\\'..c end
        return string.format('\\u%04x',string.byte(c))end)..'"'
end
local function scalar(value)
    if type(value)=='boolean'then return value and 'true'or'false'end
    if type(value)=='number'and value==value and math.abs(value)<math.huge then return tostring(value)end
    if type(value)=='string'then return q(value)end
    return 'null'
end
local function read(name,max)
    local r=getFileReader(name,false)
    if not r then return nil end
    local a,b=r:readLine(),r:readLine();r:close()
    if not a or b or #a>max then return nil end
    return a
end
local function write(name,content)
    local w=getFileWriter(name,true,false);assert(w,'writer unavailable')
    w:write(content..'\n');w:close()
end
local function head(id,status)
    return '{"schema":1,"world":'..q(world)..',"boot":'..q(boot)..',"request_id":'..q(id)..',"status":'..q(status)
end
local function optional(o,method)
    local ok,v=pcall(function()return o[method](o)end)
    if ok then return v end
    return nil
end
local function step()
    local j=job;local budget=128;local deadline=getTimestampMs()+2
    while j.index<j.source:size()and budget>0 and getTimestampMs()<=deadline do
        local animal=j.source:get(j.index);j.index=j.index+1;budget=budget-1
        local ok,row=pcall(function()
            if not animal or not animal:getSquare()then j.unloaded=j.unloaded+1;return nil end
            local x,y,z=animal:getX(),animal:getY(),animal:getZ()
            assert(type(x)=='number'and x==x and type(y)=='number'and y==y and type(z)=='number'and z==z,'invalid coordinates')
            local d=math.sqrt((x-j.x)^2+(y-j.y)^2)
            if d>j.radius then return nil end
            local breed=optional(animal,'getBreed')
            return '{"animal_id":'..scalar(optional(animal,'getAnimalID'))..',"type":'..scalar(optional(animal,'getAnimalType'))..
                ',"breed":'..scalar(breed and optional(breed,'getName'))..',"x":'..scalar(x)..',"y":'..scalar(y)..',"z":'..scalar(z)..
                ',"distance_tiles_2d":'..scalar(d)..',"health":'..scalar(optional(animal,'getHealth'))..
                ',"dead":'..scalar(optional(animal,'isDead'))..',"age":'..scalar(optional(animal,'getAge'))..
                ',"baby":'..scalar(optional(animal,'isBaby'))..'}'
        end)
        if ok and row then j.rows[#j.rows+1]=row elseif not ok then j.errors=j.errors+1 end
    end
    if j.index<j.source:size()then return end
    write(RESP,head(j.id,j.errors==0 and'complete'or'partial')..',"player":'..q(j.player)..
        ',"anchor":{"x":'..scalar(j.x)..',"y":'..scalar(j.y)..',"z":'..scalar(j.z)..'}'..
        ',"radius":'..j.radius..',"inspected":'..j.index..',"unloaded":'..j.unloaded..',"errors":'..j.errors..
        ',"count":'..#j.rows..',"elapsed_ms":'..(getTimestampMs()-j.started)..
        ',"scope":"loaded IsoAnimal objects only; no virtual populations or hutch inventory","animals":['..table.concat(j.rows,',')..']}')
    job=nil
end
local function poll()
    if job then step();return end
    local now=getTimestampMs();if now<nextPoll then return end;nextPoll=now+1000
    local line=read(REQ,256);if not line then return end
    local id,w,player,r,expiry,b=line:match('^v1\t([0-9a-f]+)\t([A-Za-z0-9_%-]+)\t([A-Za-z0-9_%.%-]+)\t(%d+)\t(%d+)\t([0-9a-f%-]+)$')
    if not id or #id~=32 or w~=world or b~=boot or #player>31 or #r>3 or #expiry~=13 then return end
    if read(GUARD,64)==id then return end
    write(GUARD,id);assert(read(GUARD,64)==id,'guard persistence failed')
    local ok,why=pcall(function()
        r=tonumber(r);expiry=tonumber(expiry)
        assert(r>=1 and r<=500 and expiry>=now and expiry<=now+60000,'invalid radius/expiry')
        local anchor=nil;local players=getOnlinePlayers()
        for i=0,players:size()-1 do local p=players:get(i);if p:getUsername()==player then anchor=p;break end end
        assert(anchor,'player not connected')
        local source=getCell():getAnimals();assert(source and source.size and source:size()<=10000,'animal budget/API')
        job={id=id,player=player,radius=r,x=anchor:getX(),y=anchor:getY(),z=anchor:getZ(),source=source,index=0,errors=0,unloaded=0,rows={},started=now}
        write(RESP,head(id,'running')..'}');step()
    end)
    if not ok then job=nil;write(RESP,head(id,'error')..',"reason":"review_server_logs"}');print('SIEGER_SERVER animal error: '..tostring(why))end
end
write('SiegerServerReady.txt',head(nil,'ready')..',"module":"animals-v1","game_version":'..q(config.game_version)..'}')
Events.OnTickEvenPaused.Add(function()
    local ok,why=pcall(poll)
    if not ok then
        local id=job and job.id;job=nil
        if id then pcall(write,RESP,head(id,'error')..',"reason":"review_server_logs"}')end
        print('SIEGER_SERVER poll error: '..tostring(why))
    end
end)
SiegerServerModuleRevision='animals-v1'
SiegerServerBootstrap=nil
print('SIEGER_SERVER animals-v1 ready world='..world)
