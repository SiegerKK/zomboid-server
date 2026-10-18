-- Root-only fixed preset request -> target client, never arbitrary client mutations.
if isClient and isClient() then return end
local REQUEST="SiegerCharacterRequest.txt"
local RESULT="SiegerCharacterResult.txt"
local GUARD="SiegerCharacterGuard.txt"
local profiles=require "SiegerCharacterProfiles"
local pending=nil
local processed=nil
local ticks=0
local function read(name)
 local f=getFileReader(name,false);if not f then return nil end
 local s=f:readLine();local extra=f:readLine();f:close()
 if extra or not s or #s>256 then return nil end
 return s
end
local function write(name,s)
 local f=assert(getFileWriter(name,true,false));f:write(s.."\n");f:close()
end
local function request()
 local line=read(REQUEST)
 if not line then return nil end
 local id,world,user,profile=line:match("^v1\t([0-9a-f]+)\t([A-Za-z0-9_]+)\t([A-Za-z0-9_.%-]+)\t([A-Za-z0-9_%-]+)$")
 if not id or #id~=32 or #user>31 or world~="story_test" or not profiles[profile]then return nil end
 return {id=id,world=world,username=user,profile=profile}
end
local function result(req,state,reason)
 write(RESULT,table.concat({"v1",req.id,req.world,req.username,req.profile,state,reason},"\t"))
end
local function poll()
 local req=request();if not req or req.id==processed then return end
 if not SiegerStoryScenes or SiegerStoryScenes.world~=req.world then return end
 if read(GUARD)==req.id then processed=req.id;return end -- never resend after process restart
 local players=getOnlinePlayers();local player=nil
 for i=0,players:size()-1 do if players:get(i):getUsername()==req.username then player=players:get(i)end end
 if not player then return end -- keep offline request pending, do not mutate
 assert(sendServerCommand,"server_command_api_missing")
 write(GUARD,req.id);processed=req.id;pending=req
 result(req,"waiting","client_ack_required")
 sendServerCommand(player,"SiegerCharacter","APPLY",req)
end
local function ack(module,command,player,args)
 if module~="SiegerCharacter" or command~="ACK" or not pending or not player or type(args)~="table" then return end
 if args.id~=pending.id or args.world~=pending.world or args.profile~=pending.profile
  or player:getUsername()~=pending.username then return end
 if args.state~="complete" and args.state~="error"then return end
 local allowed={client_applied=true,preflight_failed=true,partial_possible=true,duplicate_not_reapplied=true}
 if not allowed[args.reason]then return end
 result(pending,args.state,args.reason);pending=nil
end
if Events and Events.OnTick then Events.OnTick.Add(function()
 ticks=ticks+1;if ticks%120==0 then
  local ok,err=pcall(poll);if not ok then print("SIEGER_CHARACTER ERROR "..tostring(err))end
 end
end)end
if Events and Events.OnClientCommand then Events.OnClientCommand.Add(ack)end
