-- Fixed trusted bootstrap only. Refuse mixed legacy/migrated server handlers.
assert(not (isClient and isClient()), 'dedicated server required')
assert(not SiegerServerLoadedModules, 'duplicate admin bootstrap')
assert(getLoadedLuaCount and getLoadedLua, 'loaded Lua inspection unavailable')
local legacyFiles={["siegeradminbuildingatlas.lua"]=true,["siegeradminclock.lua"]=true,["siegeradminconstruction.lua"]=true,["siegeradminzombiedebug.lua"]=true,["siegerruntimeaudit.lua"]=true,["siegerstoryareascan.lua"]=true,["siegerstorybarcontrol.lua"]=true,["siegerstorybatch.lua"]=true,["siegerstorycharacter.lua"]=true,["siegerstorydirector.lua"]=true,["siegerstoryops.lua"]=true,["siegerstoryplayercontrol.lua"]=true,["siegerstorytloudiagnostics.lua"]=true,["siegerstoryvehiclecontrol.lua"]=true,["zz_siegerstoryscenes.lua"]=true}
for i=0,getLoadedLuaCount()-1 do
    local path=tostring(getLoadedLua(i)):gsub('\\','/'):lower()
    assert(not path:find('siegeradmin/42/media/lua/server/',1,true), 'legacy admin server Lua already loaded')
    local base=path:match('([^/]+)$') or path
    assert(not legacyFiles[base], 'legacy administrative handler already loaded')
end
assert(not SiegerStoryScenes, 'story bundle already initialized')
SiegerServerLoadedModules={}
SiegerServerAdminPreflight=true
