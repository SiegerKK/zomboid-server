-- Root-issued inventory reconciliation. No client-created authoritative items, XP or health writes.
if isClient and isClient()then return end
local profiles=require "SiegerCharacterProfiles"
local identity=require "SiegerInventoryIdentity"
local REQUEST="SiegerCharacterRequest.txt"
local RESULT="SiegerCharacterResult.txt"
local GUARD="SiegerCharacterGuard.txt"
local pending=nil
local processed=nil
local ticks=0
local function read(name)
 local f=getFileReader(name,false);if not f then return nil end
 local s=f:readLine();local extra=f:readLine();f:close()
 if extra or not s or #s>300 then return nil end
 return s
end
local function firstLine(name)
 local f=getFileReader(name,false);if not f then return nil end
 local line=f:readLine();f:close();return line
end
local function write(name,s)
 local f=assert(getFileWriter(name,true,false));f:write(s.."\n");f:close()
end
local function fields(line)
 local t={};for v in (line.."\t"):gmatch("([^\t]*)\t")do t[#t+1]=v end;return t
end
local function request()
 local line=read(REQUEST);if not line then return nil end
 local f=fields(line)
 if #f<5 or #f>7 or f[1]~="v1"or #f[2]~=32 or not f[2]:match("^[0-9a-f]+$")
  or f[3]~="story_test"or #f[4]>31 or not f[4]:match("^[A-Za-z0-9_][A-Za-z0-9_.%-]*$")or not profiles[f[5]]then return nil end
 local mode=f[6]or "apply";if mode~="apply"and mode~="audit"and mode~="repair"then return nil end
 return {id=f[2],world=f[3],username=f[4],profile=f[5],mode=mode,item=f[7]or "-"}
end
local function result(req,state,reason)
 write(RESULT,table.concat({"v1",req.id,req.world,req.username,req.profile,state,reason},"\t"))
end
local function journal(req,phase,rows)
 local text={req.id.."\t"..phase}
 for _,r in ipairs(rows or {})do text[#text+1]=table.concat({tostring(r.id),r.kind,r.path,tostring(r.condition)},"\t")end
 write("SiegerInventoryRepair-"..req.id..".txt",table.concat(text,"\n"))
end
local function same(a,b)return a.id==b.id and a.kind==b.kind and a.path==b.path and a.condition==b.condition end
local function stable(before,now)
 local old=identity.rows(before);local fresh=identity.rows(now)
 assert(#before==#now,"server_inventory_changed")
 for id,row in pairs(old)do assert(fresh[id]and same(row,fresh[id]),"server_inventory_changed")end
end
local function prepare(player,req,clientRows)
 local client=identity.rows(clientRows)
 local serverRows,index=identity.snapshot(player:getInventory())
 local inventory=player:getInventory()
 assert(inventory.getCharacter and inventory:getCharacter()==player and inventory.AddItem
  and sendAddItemToContainer and sendServerCommand,"player_inventory_delivery_api_missing")
 local choices={};local counts={};local selected={}
 for _,entry in ipairs(profiles[req.profile].items)do
  if req.item=="-"or req.item==entry[1]then choices[#choices+1]=entry;selected[entry[1]]=true;counts[entry[1]]=0 end
 end
 assert(#choices>0,"item_not_in_profile")
 local expected,ghosts,delivery,staged={},{},{},{}
 for _,row in ipairs(serverRows)do if selected[row.kind]then
  counts[row.kind]=counts[row.kind]+1;expected[#expected+1]=row
  local item=index[tostring(row.id)]
  assert(item.container:getCharacter()==player,"server_owner_mismatch")
  local seen=client[tostring(row.id)]
  if seen then
   assert(seen.kind==row.kind and seen.path==row.path,"shared_identity_or_container_mismatch")
   assert(seen.condition==row.condition or syncItemFields,"condition_sync_api_missing")
   if seen.condition~=row.condition then delivery[#delivery+1]={entry=item,fieldsOnly=true}end
  else
   -- Existing nested items require their parent to be known or delivered as part of this profile.
   if row.path~="main"then
    local parentId=row.path:match("/([%d%-]+)$");local parent=index[parentId]
    assert(parent and (client[parentId]or selected[parent.row.kind]),"parent_container_not_shared")
   end
   delivery[#delivery+1]={entry=item}
  end
 end end
 for _,row in ipairs(clientRows)do if selected[row.kind]then
  local owned=index[tostring(row.id)]
  if owned then assert(owned.row.kind==row.kind and owned.row.path==row.path,"id_collision_or_container_mismatch")
  else ghosts[#ghosts+1]=row end
 end end
 local ghostIds={};for _,row in ipairs(ghosts)do ghostIds[tostring(row.id)]=true end
 for _,row in ipairs(ghosts)do
  local prefix=row.path.."/"..tostring(row.id)
  for _,child in ipairs(clientRows)do
   if child.path==prefix or child.path:sub(1,#prefix+1)==prefix.."/"then
    assert(ghostIds[tostring(child.id)],"ghost_bag_contains_preserved_item")
   end
  end
 end
 local reserved={}
 for _,choice in ipairs(choices)do
  for i=1,math.max(0,choice[2]-counts[choice[1]])do
   local item=nil
   for attempt=1,8 do
    local candidate=instanceItem(choice[1]);assert(candidate,"profile_item_unavailable")
    local id=tostring(candidate:getID())
    if not index[id]and not client[id]and not reserved[id]then item=candidate;reserved[id]=true;break end
   end
   assert(item,"fresh_item_id_collision")
   if choice[3]then item:setCondition(math.max(1,math.floor(item:getConditionMax()*choice[3]+.5)))end
   item:getModData().SiegerInventoryRepair=req.id..":"..tostring(#staged+1)
   staged[#staged+1]=item
   expected[#expected+1]={id=item:getID(),kind=tostring(item:getFullType()),path="main",condition=item:getCondition()}
  end
 end
 return {before=serverRows,expected=expected,ghosts=ghosts,delivery=delivery,staged=staged}
end
local function commit(player,req,plan)
 local now=identity.snapshot(player:getInventory());stable(plan.before,now)
 journal(req,"server_mutation_started",plan.expected) -- durable before first attachment or resend
 local inv=player:getInventory()
 for _,item in ipairs(plan.staged)do
  local placed=assert(inv:AddItem(item),"server_add_failed")
  assert(placed:getID()==item:getID(),"server_add_changed_id")
  sendAddItemToContainer(inv,placed) -- actual B42 server serializes this very instance to its owner
 end
 table.sort(plan.delivery,function(a,b)return #a.entry.row.path<#b.entry.row.path end)
 for _,d in ipairs(plan.delivery)do
  if d.fieldsOnly then syncItemFields(player,d.entry.item)
  else sendAddItemToContainer(d.entry.container,d.entry.item)end
 end
 journal(req,"awaiting_identity_verification",plan.expected)
end
local function audit(req,detail,clientRows,player)
 assert(type(detail)=="table","invalid_audit")
 local serverRows=identity.snapshot(player:getInventory());identity.rows(clientRows)
 local rows={req.id};local allowed={inventory=true,marker=true}
 for _,entry in ipairs(profiles[req.profile].items)do allowed["item_"..entry[1]]=true end
 for name in pairs(profiles[req.profile].skills)do allowed["skill_"..name]=true end
 for name in pairs(profiles[req.profile].stats)do allowed["stat_"..name]=true end
 for _,w in ipairs(profiles[req.profile].wounds)do
  for _,prefix in ipairs({"scratch_","scratch_time_","bandaged_"})do allowed[prefix..w.part]=true end
 end
 for key in pairs(allowed)do
  local v=detail[key]
  if type(v)=="number"and v==v and math.abs(v)<100000 then rows[#rows+1]=key.."\t"..tostring(v)
  elseif key=="marker"and(v=="none"or v=="complete"or v=="error")then rows[#rows+1]=key.."\t"..v end
 end
 write("SiegerCharacterAudit.txt",table.concat(rows,"\n"))
 local before={req.id.."\tserver_before"}
 for _,r in ipairs(serverRows)do before[#before+1]=table.concat({tostring(r.id),r.kind,r.path,tostring(r.condition)},"\t")end
 write("SiegerInventoryServer-"..req.id..".txt",table.concat(before,"\n"))
 local text={req.id.."\tclient_audit"}
 for _,r in ipairs(clientRows)do text[#text+1]=table.concat({tostring(r.id),r.kind,r.path,tostring(r.condition)},"\t")end
 write("SiegerInventoryClient-"..req.id..".txt",table.concat(text,"\n"))
end
local function poll()
 local req=request();if not req or req.id==processed then return end
 if not SiegerStoryScenes or SiegerStoryScenes.world~=req.world then return end
 if read(GUARD)==req.id or firstLine("SiegerInventoryRepair-"..req.id..".txt")then processed=req.id;return end
 local all=getOnlinePlayers();local player=nil
 for i=0,all:size()-1 do if all:get(i):getUsername()==req.username then player=all:get(i)end end
 if not player then return end
 assert(sendServerCommand,"server_command_api_missing")
 write(GUARD,req.id);processed=req.id
 if req.mode=="apply"then result(req,"error","legacy_apply_disabled");return end
 pending={req=req,phase="snapshot",player=player}
 journal(req,"snapshot_requested");result(req,"waiting","identity_snapshot_required")
 sendServerCommand(player,"SiegerCharacter",req.mode=="audit"and "AUDIT"or "INVENTORY",req)
end
local function handle(module,command,player,args)
 if module~="SiegerCharacter"or not pending or not player or type(args)~="table"then return end
 local req=pending.req
 if args.id~=req.id or args.world~=req.world or args.profile~=req.profile
  or player~=pending.player or player:getUsername()~=req.username then return end
 if command=="ACK"and args.state=="error"then
  local allowed={audit_failed=true,cleanup_uncertain=true,delivery_timeout=true,invalid_manifest=true,legacy_apply_disabled=true}
  if not allowed[args.reason]then return end
  journal(req,"error_"..args.reason,pending.plan and pending.plan.expected)
  result(req,"error",args.reason);pending=nil;return
 end
 if req.mode=="audit"then
  if command~="ACK"or args.reason~="audit_only"or pending.phase~="snapshot"then return end
  pending.phase="audit_record"
  audit(req,args.report,args.items,player);result(req,"complete","audit_only");pending=nil;return
 end
 if command=="SNAPSHOT"and pending.phase=="snapshot"then
  pending.phase="preflight"
  local plan=prepare(player,req,args.items);pending.plan=plan
  audit(req,args.report,args.items,player)
  journal(req,"prepared",plan.expected);pending.phase="cleanup"
  local payload={id=req.id,world=req.world,username=req.username,profile=req.profile,
   ghosts=plan.ghosts,expected=plan.expected}
  sendServerCommand(player,"SiegerCharacter","CLEAN",payload)
 elseif command=="CLEANED"and pending.phase=="cleanup"then
  pending.phase="server_commit";commit(player,req,pending.plan)
  pending.phase="verify"
  sendServerCommand(player,"SiegerCharacter","VERIFY",{id=req.id,world=req.world,
   username=req.username,profile=req.profile,expected=pending.plan.expected})
 elseif command=="VERIFIED"and pending.phase=="verify"then
  pending.phase="verify_record"
  local client=identity.rows(args.items);local _,server=identity.snapshot(player:getInventory())
  for _,r in ipairs(pending.plan.expected)do
   local id=tostring(r.id)
   assert(client[id]and server[id]and same(client[id],r)and same(server[id].row,r),"post_delivery_identity_mismatch")
  end
  local after={req.id.."\tclient_after"}
  for _,r in ipairs(args.items)do after[#after+1]=table.concat({tostring(r.id),r.kind,r.path,tostring(r.condition)},"\t")end
  write("SiegerInventoryClientAfter-"..req.id..".txt",table.concat(after,"\n"))
  journal(req,"server_inventory_verified",pending.plan.expected)
  result(req,"complete","server_inventory_verified");pending=nil
 end
end
local function onCommand(...)
 local ok,err=pcall(handle,...)
 if not ok then
  print("SIEGER_CHARACTER ERROR inventory "..tostring(err))
  if pending then
   pcall(journal,pending.req,"error_partial_possible",pending.plan and pending.plan.expected)
   pcall(result,pending.req,"error","partial_possible");pending=nil
  end
 end
end
if Events then
 if Events.OnTick then Events.OnTick.Add(function()
  ticks=ticks+1;if ticks%120==0 then local ok,err=pcall(poll);if not ok then print("SIEGER_CHARACTER ERROR poll "..tostring(err))end end
 end)end
 if Events.OnClientCommand then Events.OnClientCommand.Add(onCommand)end
end
