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
 local mode=line:match("\t(audit)$") and "audit" or "apply"
 line=line:gsub("\taudit$","")
 local id,world,user,profile=line:match("^v1\t([0-9a-f]+)\t([A-Za-z0-9_]+)\t([A-Za-z0-9_.%-]+)\t([A-Za-z0-9_%-]+)$")
 if not id or #id~=32 or #user>31 or world~="story_test" or not profiles[profile]then return nil end
 return {id=id,world=world,username=user,profile=profile,mode=mode}
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
 write(GUARD,req.id);processed=req.id;pending=req;pending.phase="prepare"
 result(req,"waiting","client_ack_required")
 sendServerCommand(player,"SiegerCharacter",req.mode=="audit" and "AUDIT" or "PREPARE",req)
end
local function serverBaseline(player,profile)
 -- These operations originate from the root request. No privileged client XP/stats packets.
 local xp=player:getXp();local stats=player:getStats()
 assert(player.setPerkLevelDebug and xp and xp.setXPToLevel and stats and stats.set
  and addXpNoMultiplier,"server_baseline_api_missing")
 for name in pairs(profile.skills)do assert(Perks[name],"server_perk_missing")end
 for name in pairs(profile.stats)do assert(CharacterStat[name],"server_stat_missing")end
 for name,level in pairs(profile.skills)do
  player:setPerkLevelDebug(Perks[name],level);xp:setXPToLevel(Perks[name],level)
 end
 for name,value in pairs(profile.stats)do stats:set(CharacterStat[name],value)end
 addXpNoMultiplier(player,Perks.Strength,0) -- exposed B42 global -> GameServer.addXp -> internal updateXpChecker
end
local function audit(req,detail)
 if type(detail)~="table" then return end
 local rows={req.id}
 local allowed={inventory=true,marker=true}
 for _,entry in ipairs(profiles[req.profile].items)do allowed["item_"..entry[1]]=true end
 for name in pairs(profiles[req.profile].skills)do allowed["skill_"..name]=true end
 for name in pairs(profiles[req.profile].stats)do allowed["stat_"..name]=true end
 for _,w in ipairs(profiles[req.profile].wounds)do allowed["scratch_"..w.part]=true end
 for key in pairs(allowed)do
  local value=detail[key]
  if type(value)=="number" and value==value and math.abs(value)<100000 then
   rows[#rows+1]=key.."\t"..tostring(value)
  elseif key=="marker" and (value=="none" or value=="error" or value=="complete")then
   rows[#rows+1]=key.."\t"..value
  end
 end
 write("SiegerCharacterAudit.txt",table.concat(rows,"\n"))
end
local function ack(module,command,player,args)
 if module~="SiegerCharacter" or not pending or not player or type(args)~="table" then return end
 if args.id~=pending.id or args.world~=pending.world or args.profile~=pending.profile
  or player:getUsername()~=pending.username then return end
 if command=="READY" then
  if pending.mode~="apply" or pending.phase~="prepare"then return end
  pending.phase="server_commit" -- prevent duplicate READY baseline writes
  local ok,err=pcall(serverBaseline,player,profiles[pending.profile])
  if not ok then
   print("SIEGER_CHARACTER ERROR baseline "..tostring(err))
   result(pending,"error","server_partial_possible");pending=nil;return
  end
  pending.phase="client_commit"
  sendServerCommand(player,"SiegerCharacter","COMMIT",pending)
  return
 end
 if command~="ACK" or (args.state~="complete" and args.state~="error")then return end
 local allowed={client_applied=true,preflight_failed=true,partial_possible=true,
  duplicate_not_reapplied=true,prepare_missing=true,audit_only=true,audit_failed=true}
 if not allowed[args.reason]then return end
 if pending.mode=="audit" then
  if args.reason~="audit_only" and args.reason~="audit_failed"then return end
 elseif pending.phase~="client_commit" and args.reason~="preflight_failed"
  and args.reason~="duplicate_not_reapplied"then return end
 audit(pending,args.report)
 result(pending,args.state,args.reason);pending=nil
end

if Events and Events.OnTick then Events.OnTick.Add(function()
 ticks=ticks+1;if ticks%120==0 then
  local ok,err=pcall(poll);if not ok then print("SIEGER_CHARACTER ERROR "..tostring(err))end
 end
end)end
if Events and Events.OnClientCommand then Events.OnClientCommand.Add(ack)end
