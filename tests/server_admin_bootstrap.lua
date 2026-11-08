-- Lifecycle harness only: no claim of multiplayer acceptance.
local preflight=arg and arg[1] or 'server/lua/SiegerServerAdminPreflight.lua'
local ready=arg and arg[2] or 'server/lua/SiegerServerAdminReady.lua'
local function read(path)local f=assert(io.open(path));local s=f:read('*a');f:close();return s end
local pre=assert(loadstring(read(preflight)))
local finish=assert(loadstring(read(ready)))
isClient=function()return false end
local paths={}
getLoadedLuaCount=function()return #paths end
getLoadedLua=function(i)return paths[i+1]end
local function reset()
 SiegerServerLoadedModules=nil;SiegerServerAdminPreflight=nil;SiegerStoryScenes=nil
end
reset();paths={'mods/SiegerAdmin/42/media/lua/server/SiegerAdminClock.lua'}
assert(not pcall(pre),'legacy modules must be rejected before registration')
assert(not SiegerServerLoadedModules)
reset();paths={'mods/SiegerAdmin/42/media/lua/shared/SiegerCharacterProfiles.lua'}
pre();assert(SiegerServerAdminPreflight)
assert(not pcall(pre),'duplicate bootstrap must fail')
SiegerServerAdminBootstrap={world='story_test',boot='11111111-1111-1111-1111-111111111111'}
assert(not pcall(finish),'missing bundle must fail')
SiegerStoryScenes={world='road_home'}
assert(not pcall(finish),'different bundle must fail')
SiegerStoryScenes={world='story_test'}
local events={}
Events={OnServerStarted={Add=function(fn)events[#events+1]=fn end}}
local output
getFileWriter=function(name,create,append)
 assert(name=='SiegerServerAdminReady.txt' and create and not append)
 return {write=function(_,s)output=s end,close=function()end}
end
finish();assert(not output,'must wait for actual OnServerStarted')
assert(#events==1 and SiegerServerAdminRevision=='admin-v1')
events[1]()
assert(output=='v1\tstory_test\t11111111-1111-1111-1111-111111111111\tadmin-v1\n')
print('PASS: migration refuses duplicate/legacy handlers, wrong bundle and early readiness')
