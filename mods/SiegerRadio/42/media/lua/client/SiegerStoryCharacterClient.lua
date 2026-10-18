-- Client-authoritative health/XP/equipment. Only fixed server-issued presets.
if isServer and isServer() then return end
local profiles=require "SiegerCharacterProfiles"
local MODULE="SiegerCharacter"
local function validID(id)return type(id)=="string" and #id==32 and id:match("^[0-9a-f]+$")end
local function preflight(p,profile)
 assert(p and not p:isDead(),"player_not_alive")
 assert(p.getModData and p.removeFromHands and p.removeWornItem and p.removeAttachedItem,
  "equipment_api_missing")
 assert(sendClothing and sendEquip
  and triggerEvent,"sync_api_missing")
 assert(p.setPerkLevelDebug and p.getPerkLevel and p.setClothingItem_Back,"player_api_missing")
 local inv=p:getInventory();assert(inv and inv.getItems and inv.AddItem and inv.Remove,"inventory_api_missing")
 assert(inv:getItems():size()<=256,"inventory_too_large")
 local stats=p:getStats();assert(stats and stats.get and stats.set,"b42_stats_api_missing")
 local xp=p:getXp();assert(xp and xp.setXPToLevel,"xp_api_missing")
 local skills={}
 for name,level in pairs(profile.skills) do
  local perk=Perks and Perks[name];assert(perk,"unknown_perk_"..name)
  skills[#skills+1]={perk,level}
 end
 for name in pairs(profile.stats) do assert(CharacterStat and CharacterStat[name],"unknown_stat")end
 local body=p:getBodyDamage();assert(body and body.getBodyPart,"body_api_missing")
 local wounds={}
 for _,w in ipairs(profile.wounds) do
  local kind=BodyPartType and BodyPartType[w.part];assert(kind,"body_part_missing")
  local part=body:getBodyPart(kind)
  assert(part and part.setScratched and part.setScratchTime and part.setBandaged
   and part.IsInfected and part.scratched and part.isCut and part.isDeepWounded,
   "scratch_api_missing")
  assert(not part:IsInfected() and not part:scratched() and not part:isCut()
   and not part:isDeepWounded(),"existing_injury_requires_review")
  wounds[#wounds+1]={part,w.time}
 end
 local staged={}
 for _,entry in ipairs(profile.items) do
  for i=1,entry[2] do
   local item=instanceItem(entry[1]);assert(item,"missing_item_"..entry[1])
   if entry[3] then
    assert(item.setCondition and item.getConditionMax,"condition_api_missing")
    item:setCondition(math.max(1,math.floor(item:getConditionMax()*entry[3]+.5)))
   end
   staged[#staged+1]={item,entry[4]}
  end
 end
 assert(staged[1][1].getItemContainer and staged[1][1]:getItemContainer(),"backpack_container_missing")
 local remove={};local all=inv:getItems()
 for i=0,all:size()-1 do
  local item=all:get(i)
  if not profile.keep[tostring(item:getFullType())] then
   assert(item.getBodyLocation,"body_location_api_missing")
   remove[#remove+1]=item
  end
 end
 return function()
  for _,item in ipairs(remove) do
   local loc=item:getBodyLocation()
   p:removeFromHands(item);p:removeAttachedItem(item);p:removeWornItem(item,false)
   if loc then sendClothing(p,loc,nil)end
   inv:Remove(item) -- own inventory is client-authoritative and saved by the game
  end
  local pack=nil
  for _,entry in ipairs(staged) do
   local kind=entry[1]:getFullType()
   local top=entry[2]=="back" or kind=="Base.Revolver" or kind=="Base.Shotgun"
    or kind=="Base.HuntingRifle" or kind=="Base.HuntingKnife"
   local destination=top and inv or assert(pack,"backpack_not_ready")
   local item=assert(destination:AddItem(entry[1]),"inventory_add_failed")
   if entry[2]=="back" then
    p:setClothingItem_Back(item);sendClothing(p,ItemBodyLocation.BACK,item)
    pack=item:getItemContainer()
   end
  end
  for _,v in ipairs(skills) do p:setPerkLevelDebug(v[1],v[2]);xp:setXPToLevel(v[1],v[2])end
  for name,v in pairs(profile.stats) do stats:set(CharacterStat[name],v);assert(math.abs(stats:get(CharacterStat[name])-v)<.0001,"stat_set_failed")end
  for _,v in ipairs(wounds) do
   v[1]:setScratched(true,true) -- engine's non-zombie/environmental scratch path
   v[1]:setScratchTime(v[2]);v[1]:setBandaged(true,8,true,"Base.Bandage")
  end
  sendEquip(p);triggerEvent("OnClothingUpdated",p)
 end
end
local prepared=nil
local function report(p,profile)
 local result={inventory=p:getInventory():getItems():size()}
 local expected={}
 for _,entry in ipairs(profile.items)do expected[entry[1]]=true;result["item_"..entry[1]]=0 end
 local visited=0
 local function count(inv,depth)
  assert(depth<=4,"inventory_nesting_limit")
  local items=inv:getItems()
  for i=0,items:size()-1 do
   visited=visited+1;assert(visited<=512,"inventory_audit_limit")
   local item=items:get(i);local kind=tostring(item:getFullType())
   if expected[kind]then result["item_"..kind]=result["item_"..kind]+1 end
   if item.getItemContainer then local nested=item:getItemContainer();if nested then count(nested,depth+1)end end
  end
 end
 count(p:getInventory(),0)
 for name in pairs(profile.skills) do result["skill_"..name]=p:getPerkLevel(Perks[name])end
 for name in pairs(profile.stats) do result["stat_"..name]=p:getStats():get(CharacterStat[name])end
 for _,w in ipairs(profile.wounds)do
  local part=p:getBodyDamage():getBodyPart(BodyPartType[w.part])
  result["scratch_"..w.part]=part:scratched() and 1 or 0
 end
 local marker=p:getModData().SiegerCharacterProfile
 result.marker=marker and marker.state or "none"
 return result
end
local function receive(module,command,args)
 if module~=MODULE or (command~="PREPARE" and command~="COMMIT" and command~="AUDIT")
  or type(args)~="table" or not validID(args.id)
  or args.world~="story_test" or not profiles[args.profile]then return end
 local p=nil
 for i=0,getNumActivePlayers()-1 do
  local candidate=getSpecificPlayer(i)
  if candidate and candidate:getUsername()==args.username then p=candidate;break end
 end
 if not p then return end
 local function reply(state,reason,extra)
  sendClientCommand(p,MODULE,"ACK",{id=args.id,world=args.world,profile=args.profile,
   state=state,reason=reason,report=extra})
 end
 if command=="AUDIT" then
  local ok,detail=pcall(report,p,profiles[args.profile])
  if ok then reply("complete","audit_only",detail)else reply("error","audit_failed")end
  return
 end
 local md=p:getModData();local marker=md.SiegerCharacterProfile
 if marker and marker.id==args.id then reply(marker.state,"duplicate_not_reapplied");return end
 if command=="PREPARE" then
  local ok,apply=pcall(preflight,p,profiles[args.profile])
  if not ok then print("SIEGER_CHARACTER PREFLIGHT "..tostring(apply));reply("error","preflight_failed");return end
  prepared={id=args.id,player=p,apply=apply}
  sendClientCommand(p,MODULE,"READY",{id=args.id,world=args.world,profile=args.profile})
  return
 end
 if not prepared or prepared.id~=args.id or prepared.player~=p then
  reply("error","prepare_missing");return
 end
 local apply=prepared.apply;prepared=nil
 md.SiegerCharacterProfile={id=args.id,state="error"}
 local done,err=pcall(apply)
 if not done then print("SIEGER_CHARACTER ERROR "..tostring(err));reply("error","partial_possible");return end
 md.SiegerCharacterProfile.state="complete"
 local ok,detail=pcall(report,p,profiles[args.profile])
 reply("complete","client_applied",ok and detail or nil)
end
if Events and Events.OnServerCommand then Events.OnServerCommand.Add(receive)end
