-- Engine-shaped simulation, NOT multiplayer acceptance.
local clientFile=assert(arg[1]);local serverFile=assert(arg[2]);local shared=assert(arg[3])
package.preload.SiegerCharacterProfiles=function()return dofile(shared)end
local receive,ack,poll,removed,added,injured,stats,levels,files,commands,player
local function list(t)return {size=function()return #t end,get=function(_,i)return t[i+1]end}end
local function item(kind)
 return {getItemContainer=function()return {AddItem=function(_,i)added=added+1;return i end}end,
  getFullType=function()return kind end,getBodyLocation=function()return "loc"end,
  setCondition=function()end,getConditionMax=function()return 10 end}
end
local missing=false
local preinjured=false
local function setup()
 removed=0;added=0;injured=0;stats={};levels={};files={};commands={};missing=false;preinjured=false
 local invitems={item("Base.KeyRing"),item("Base.RollingPin")}
 local inv={getItems=function()return list(invitems)end,
  Remove=function(_,i)removed=removed+1 end,AddItem=function(_,i)added=added+1;return i end}
 local md={}
 local body={getBodyPart=function()return {
  IsInfected=function()return false end,scratched=function()return preinjured end,
  isCut=function()return false end,isDeepWounded=function()return false end,
  setScratched=function(_,a,b)assert(a and b);injured=injured+1 end,
  setScratchTime=function()end,setBandaged=function()end}end}
 player={getUsername=function()return "owner"end,isDead=function()return false end,
  getModData=function()return md end,getInventory=function()return inv end,
  removeFromHands=function()end,removeWornItem=function()end,removeAttachedItem=function()end,
  setClothingItem_Back=function()end,getBodyDamage=function()return body end,
  getStats=function()return {get=function(_,k)return stats[k]end,set=function(_,k,v)stats[k]=v;return false end}end,
  getXp=function()return {setXPToLevel=function()end}end,
  getPerkLevel=function()return 0 end,setPerkLevelDebug=function(_,k,v)levels[k]=v end}
 CharacterStat={HUNGER="HUNGER",THIRST="THIRST",FATIGUE="FATIGUE",STRESS="STRESS"}
 Perks=setmetatable({},{__index=function(_,k)return k end})
 BodyPartType={ForeArm_L="ForeArm_L",LowerLeg_R="LowerLeg_R"};ItemBodyLocation={BACK="BACK"}
 instanceItem=function(k)if missing then return nil end return item(k)end
 sendAddItemToContainer=function()end;sendRemoveItemFromContainer=function()end
 sendClothing=function()end;sendEquip=function()end;SyncXp=function()end
 sendPlayerStatsChange=function()end;triggerEvent=function()end
 getNumActivePlayers=function()return 1 end;getSpecificPlayer=function()return player end
 sendClientCommand=function(_,module,command,args)commands[#commands+1]=args end
 Events={OnServerCommand={Add=function(fn)receive=fn end}}
 isServer=function()return false end
 dofile(clientFile)
end
local req={id=string.rep("1",32),world="story_test",username="owner",profile="joel-arrival-v1"}
setup();receive("other","APPLY",req);assert(removed==0)
req.username="wrong";receive("SiegerCharacter","APPLY",req);assert(removed==0);req.username="owner"
missing=true;receive("SiegerCharacter","APPLY",req);assert(removed==0 and added==0 and commands[1].reason=="preflight_failed")
setup();preinjured=true;receive("SiegerCharacter","APPLY",req);assert(removed==0 and injured==0)
setup();receive("SiegerCharacter","APPLY",req)
assert(removed==1 and added==44 and injured==2) -- 22 entries + ammunition counts
assert(levels.Strength==7 and levels.Aiming==5 and stats.FATIGUE==.35)
assert(commands[1].state=="complete")
receive("SiegerCharacter","APPLY",req);assert(removed==1 and added==44 and injured==2)
assert(commands[2].reason=="duplicate_not_reapplied")
-- Server: forged ACK cannot dispatch or mutate; durable guard prevents resend after reload.
getFileReader=function(name)
 if not files[name]then return nil end
 local used=false
 return {readLine=function()if used then return nil end used=true;return files[name]end,close=function()end}
end
getFileWriter=function(name)return {write=function(_,s)files[name]=s:gsub("\n$","")end,close=function()end}end
getOnlinePlayers=function()return list({player})end
isClient=function()return false end
SiegerStoryScenes={world="story_test"}
local sent=0
sendServerCommand=function(p,m,c,a)assert(p==player and a.username=="owner");sent=sent+1 end
Events={OnTick={Add=function(fn)poll=fn end},OnClientCommand={Add=function(fn)ack=fn end}}
files.SiegerCharacterRequest={}
files["SiegerCharacterRequest.txt"]="v1\t"..req.id.."\tstory_test\towner\tjoel-arrival-v1"
dofile(serverFile);for i=1,120 do poll()end;assert(sent==1)
ack("SiegerCharacter","ACK",{getUsername=function()return "intruder"end},{id=req.id,world=req.world,profile=req.profile,state="complete",reason="client_applied"})
assert(files["SiegerCharacterResult.txt"]:find("waiting",1,true))
ack("SiegerCharacter","ACK",player,{id=req.id,world=req.world,profile=req.profile,state="complete",reason="client_applied"})
assert(files["SiegerCharacterResult.txt"]:find("complete",1,true))
dofile(serverFile);for i=1,240 do poll()end;assert(sent==1)
print("PASS character: full preflight, fixed target, noninfectious scratches, client replay, server ACK identity and restart no-resend")
