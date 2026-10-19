-- Engine-shaped transport simulation: server creates IDs; native helper delivers serialized instances.
-- It is not evidence of real multiplayer equip/save acceptance.
local clientFile,serverFile,shared=arg[1],arg[2],arg[3]
local sharedDir=shared:match("^(.*)/")
package.preload.SiegerCharacterProfiles=function()return dofile(shared)end
package.preload.SiegerInventoryIdentity=function()return dofile(sharedDir.."/SiegerInventoryIdentity.lua")end
local identity=require "SiegerInventoryIdentity"
local profiles=require "SiegerCharacterProfiles"
local function list(a)return {size=function()return #a end,get=function(_,i)return a[i+1]end}end
local files,serverInv,clientInv,sp,cp,serverTick,clientTick,serverReceive,clientReceive,queue,created,delivered,deleted,idSequence,now,failDelivery
local function container(owner)
 local a={}
 local c={getCharacter=function()return owner end,getItems=function()return list(a)end}
 function c:AddItem(item)a[#a+1]=item;item.owner=self;return item end
 function c:Remove(item)for i,v in ipairs(a)do if v==item then table.remove(a,i);deleted=deleted+1;return end end error("missing item")end
 return c
end
local function item(kind,id,condition)
 local md={}
 return {getFullType=function()return kind end,getID=function()return id end,
  getCondition=function()return condition end,getConditionMax=function()return 10 end,
  setCondition=function(_,v)condition=v end,getModData=function()return md end,
  getBodyLocation=function()return nil end,getItemContainer=function()return nil end}
end
local function loadServer()
 isClient=function()return false end
 Events={OnTick={Add=function(f)serverTick=f end},OnClientCommand={Add=function(f)serverReceive=f end}}
 dofile(serverFile)
end
local function setup(mode,selector,withGhost)
 files={};queue={};created=0;delivered=0;deleted=0;idSequence=1000;now=0;failDelivery=false
 local cmd={}
 sp={getUsername=function()return "owner"end};cp={getUsername=function()return "owner"end,isDead=function()return false end,getModData=function()return cmd end}
 serverInv=container(sp);clientInv=container(cp)
 sp.getInventory=function()return serverInv end;cp.getInventory=function()return clientInv end
 cp.removeFromHands=function()end;cp.removeAttachedItem=function()end;cp.removeWornItem=function()end;cp.isEquippedClothing=function()return false end
 serverInv:AddItem(item("Base.KeyRing",1,10));clientInv:AddItem(item("Base.KeyRing",1,10))
 clientInv:AddItem(item("Example.PersonalItem",99,10)) -- unrelated client item must be preserved
 if withGhost then clientInv:AddItem(item("Base.Revolver",20,7))end
 cp.getStats=function()return {get=function()return .1 end}end;CharacterStat={HUNGER="h",THIRST="t",FATIGUE="f",STRESS="s"}
 cp.getPerkLevel=function()return 5 end;Perks=setmetatable({},{__index=function(_,k)return k end})
 cp.getBodyDamage=function()return {getBodyPart=function()return {scratched=function()return false end,
  getScratchTime=function()return 0 end,bandaged=function()return false end}end}end
 BodyPartType={ForeArm_L=1,LowerLeg_R=2}
 getFileReader=function(name)
  if not files[name]then return nil end
  local lines={};for line in files[name]:gmatch("[^\n]+")do lines[#lines+1]=line end;local i=0
  return {readLine=function()i=i+1;return lines[i]end,close=function()end}
 end
 getFileWriter=function(name)return {write=function(_,s)files[name]=s end,close=function()end}end
 getOnlinePlayers=function()return list({sp})end
 getNumActivePlayers=function()return 1 end;getSpecificPlayer=function()return cp end
 getTimestampMs=function()return now end
 instanceItem=function(kind)created=created+1;idSequence=idSequence+1;return item(kind,idSequence,10)end
 sendEquip=function()end;sendClothing=function()end;triggerEvent=function()end
 sendServerCommand=function(p,m,c,a)assert(p==sp);queue[#queue+1]=function()clientReceive(m,c,a)end end
 sendClientCommand=function(p,m,c,a)assert(p==cp);queue[#queue+1]=function()serverReceive(m,c,sp,a)end end
 sendAddItemToContainer=function(c,i)
  assert(c:getCharacter()==sp)
  if failDelivery then error("native transport failure")end
  delivered=delivered+1
  queue[#queue+1]=function()
   local _,index=identity.snapshot(clientInv)
   if not index[tostring(i:getID())]then clientInv:AddItem(item(i:getFullType(),i:getID(),i:getCondition()))end
  end
 end
 syncItemFields=function(_,i)
  queue[#queue+1]=function()local _,index=identity.snapshot(clientInv);index[tostring(i:getID())].item:setCondition(i:getCondition())end
 end
 SiegerStoryScenes={world="story_test"}
 isServer=function()return false end
 Events={OnServerCommand={Add=function(f)clientReceive=f end},OnTick={Add=function(f)clientTick=f end}}
 dofile(clientFile);loadServer()
 local id=string.rep("1",32)
 files["SiegerCharacterRequest.txt"]="v1\t"..id.."\tstory_test\towner\tjoel-arrival-v1\t"..mode..(selector and "\t"..selector or "").."\n"
 return id
end
local function pump()
 for round=1,600 do
  now=now+20;serverTick();clientTick()
  local pending=queue;queue={};for _,f in ipairs(pending)do f()end
 end
end
local function count(inv,kind)local n=0;for _,r in ipairs(identity.snapshot(inv))do if r.kind==kind then n=n+1 end end return n end
local id=setup("repair","Base.Revolver",true);pump()
assert(files["SiegerCharacterResult.txt"]:find("server_inventory_verified",1,true))
assert(created==1 and delivered==1 and count(serverInv,"Base.Revolver")==1 and count(clientInv,"Base.Revolver")==1)
assert(count(clientInv,"Example.PersonalItem")==1)
local sr,si=identity.snapshot(serverInv);local cr,ci=identity.snapshot(clientInv)
assert(si['1001'] and ci['1001'] and not ci['20']) -- mock native equip lookup resolves the same new ID
pump();assert(created==1 and delivered==1)
files["SiegerCharacterGuard.txt"]=string.rep("2",32) -- even an older historical request has its own ledger
loadServer();pump();assert(created==1 and delivered==1) -- no restart/historical resend
-- Already canonical items are reused, not replenished or duplicated.
setup("repair","Base.Revolver",false);serverInv:AddItem(item("Base.Revolver",30,6));clientInv:AddItem(item("Base.Revolver",30,6));pump()
assert(created==0 and delivered==0 and files["SiegerCharacterResult.txt"]:find("server_inventory_verified",1,true))
-- Missing server-native API: fail before local ghost cleanup and before server attachment.
setup("repair","Base.Revolver",true);sendAddItemToContainer=nil;pump()
assert(deleted==0 and created==0 and files["SiegerCharacterResult.txt"]:find("partial_possible",1,true))
-- Old unsafe apply is rejected without packets/mutations.
setup("apply",nil,true);pump();assert(created==0 and deleted==0 and files["SiegerCharacterResult.txt"]:find("legacy_apply_disabled",1,true))
-- A transport failure after server attachment is durable uncertain and never auto-replayed.
setup("repair","Base.Revolver",true);failDelivery=true;pump();assert(created==1 and count(serverInv,"Base.Revolver")==1)
assert(files["SiegerCharacterResult.txt"]:find("partial_possible",1,true));loadServer();pump();assert(created==1)
-- Unknown selector fails closed before deleting client ghosts.
setup("repair","Base.NotInPreset",true);pump();assert(created==0 and deleted==0)
-- A ghost bag containing a non-profile item must never delete that legitimate item.
setup("repair","-",true)
local personal=container(cp);personal:AddItem(item("Example.PersonalItem",51,10))
local bag=item("Base.Bag_NormalHikingBag",50,7);bag.getItemContainer=function()return personal end;clientInv:AddItem(bag)
pump();assert(created==0 and deleted==0 and count(clientInv,"Example.PersonalItem")==2)
-- No packet delivered: verify must time out, not report complete or retry automatically.
setup("repair","Base.Revolver",true);sendAddItemToContainer=function()delivered=delivered+1 end
pump();pump();assert(created==1 and count(serverInv,"Base.Revolver")==1)
assert(files["SiegerCharacterResult.txt"]:find("delivery_timeout",1,true));loadServer();pump();assert(created==1)
print("PASS inventory reconciliation simulation: server IDs, native delivery, exact ghost cleanup, preserve unrelated, reuse, fail-closed, restart replay")
