-- Fixed root-requested audit and reconciliation only. Never creates inventory items.
if isServer and isServer() then return end
local profiles=require "SiegerCharacterProfiles"
local identity=require "SiegerInventoryIdentity"
local MODULE="SiegerCharacter"
local verifying=nil
local function validID(id)return type(id)=="string" and #id==32 and id:match("^[0-9a-f]+$")end
local function target(args)
 if type(args)~="table" or not validID(args.id) or args.world~="story_test" or not profiles[args.profile]then return nil end
 for i=0,getNumActivePlayers()-1 do
  local p=getSpecificPlayer(i)
  if p and p:getUsername()==args.username and not p:isDead()then return p end
 end
end
local function reply(p,args,command,extra)
 local result={id=args.id,world=args.world,profile=args.profile}
 for k,v in pairs(extra or {})do result[k]=v end
 sendClientCommand(p,MODULE,command,result)
end
local function report(p,profile)
 local rows=identity.snapshot(p:getInventory());local result={inventory=p:getInventory():getItems():size()}
 for _,entry in ipairs(profile.items)do result["item_"..entry[1]]=0 end
 for _,row in ipairs(rows)do if result["item_"..row.kind]then result["item_"..row.kind]=result["item_"..row.kind]+1 end end
 for name in pairs(profile.skills)do result["skill_"..name]=p:getPerkLevel(Perks[name])end
 for name in pairs(profile.stats)do result["stat_"..name]=p:getStats():get(CharacterStat[name])end
 for _,w in ipairs(profile.wounds)do
  local part=p:getBodyDamage():getBodyPart(BodyPartType[w.part])
  result["scratch_"..w.part]=part:scratched()and 1 or 0
  result["scratch_time_"..w.part]=part:getScratchTime()
  result["bandaged_"..w.part]=part:bandaged()and 1 or 0
 end
 local marker=p:getModData().SiegerCharacterProfile;result.marker=marker and marker.state or "none"
 return result,rows
end
local function clean(p,args)
 local _,index=identity.snapshot(p:getInventory())
 local expected=identity.rows(args.expected);local ghosts=identity.rows(args.ghosts)
 local selected={}
 assert(p.removeFromHands and p.removeAttachedItem and p.removeWornItem and sendEquip and sendClothing,"equipment_cleanup_api_missing")
 for id,row in pairs(ghosts)do
  assert(not expected[id],"ghost_is_server_owned")
  local actual=index[id]
  assert(actual and actual.row.kind==row.kind and actual.row.path==row.path,"ghost_changed_since_snapshot")
  selected[id]=true
 end
 -- A ghost bag may not swallow unrelated or server-owned items.
 for id in pairs(selected)do
  local prefix=index[id].row.path.."/"..id
  for childId,entry in pairs(index)do
   if entry.row.path==prefix or entry.row.path:sub(1,#prefix+1)==prefix.."/"then
    assert(selected[childId],"ghost_bag_contains_preserved_item")
   end
  end
 end
 local operations={}
 for id in pairs(selected)do operations[#operations+1]=index[id]end
 table.sort(operations,function(a,b)return #a.row.path>#b.row.path end)
 local md=p:getModData();local old=md.SiegerInventoryRepair
 if old and old.id==args.id then
  assert(old.state=="cleaned","previous_cleanup_uncertain");return
 end
 md.SiegerInventoryRepair={id=args.id,state="uncertain"}
 for _,entry in ipairs(operations)do
  local item=entry.item;local worn=p:isEquippedClothing(item);local loc=item:getBodyLocation()
  p:removeFromHands(item);p:removeAttachedItem(item);p:removeWornItem(item,false)
  entry.container:Remove(item) -- ONLY server-attested client-only ghosts, never authoritative items
  if worn and loc then sendClothing(p,loc,nil)end
 end
 sendEquip(p);triggerEvent("OnClothingUpdated",p)
 md.SiegerInventoryRepair.state="cleaned"
end
local function receive(module,command,args)
 if module~=MODULE then return end
 local p=target(args);if not p then return end
 if command=="PREPARE" or command=="COMMIT"then
  reply(p,args,"ACK",{state="error",reason="legacy_apply_disabled"});return
 end
 if command=="AUDIT" or command=="INVENTORY"then
  local ok,detail,rows=pcall(report,p,profiles[args.profile])
  if not ok then print("SIEGER_CHARACTER AUDIT ERROR "..tostring(detail));reply(p,args,"ACK",{state="error",reason="audit_failed"});return end
  reply(p,args,command=="AUDIT"and "ACK"or "SNAPSHOT",{state="complete",reason="audit_only",report=detail,items=rows})
 elseif command=="CLEAN"then
  local ok,err=pcall(clean,p,args)
  if not ok then print("SIEGER_CHARACTER CLEAN ERROR "..tostring(err));reply(p,args,"ACK",{state="error",reason="cleanup_uncertain"});return end
  reply(p,args,"CLEANED",{})
 elseif command=="VERIFY"then
  local ok,expected=pcall(identity.rows,args.expected)
  if not ok then reply(p,args,"ACK",{state="error",reason="invalid_manifest"});return end
  verifying={player=p,args=args,expected=expected,started=getTimestampMs()}
 end
end
local function tick()
 if not verifying then return end
 local v=verifying;local p=v.player
 local ok,rows,index=pcall(identity.snapshot,p:getInventory())
 local matches=ok
 if ok then for id,wanted in pairs(v.expected)do
  local actual=index[id]
  if not actual or actual.row.kind~=wanted.kind or actual.row.path~=wanted.path or actual.row.condition~=wanted.condition then matches=false;break end
 end end
 if matches then
  verifying=nil;p:getModData().SiegerInventoryRepair={id=v.args.id,state="verified"}
  reply(p,v.args,"VERIFIED",{items=rows})
 elseif getTimestampMs()-v.started>20000 then
  verifying=nil;reply(p,v.args,"ACK",{state="error",reason="delivery_timeout"})
 end
end
if Events then
 if Events.OnServerCommand then Events.OnServerCommand.Add(receive)end
 if Events.OnTick then Events.OnTick.Add(tick)end
end
