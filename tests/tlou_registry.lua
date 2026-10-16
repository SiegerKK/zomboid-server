-- Run ONLY in the disposable, network-isolated source-audit container.
-- Loads the exact Workshop initializer and exact Forge OnLoad function body.
-- Engine APIs are stubbed; this is not a two-client multiplayer simulation.
local snapshot, preset = assert(arg[1]), assert(arg[2])
assert(loadfile(preset))()
local forge = { SPEED_OPTION_TO_WALKTYPE = {1,2,3}, ZTypes = {} }
local tlou = setmetatable({}, {__index=function(t,k)
    local f=function() end; rawset(t,k,f); return f
end})
package.loaded.ZomboidForge_module = forge
package.loaded.TLOU_infected_module = tlou
ZomboidForge = forge
isDebugEnabled = function() return false end
isClient = function() return arg[3] == 'client' end
isServer = function() return arg[3] ~= 'client' end
ImmutableColor = { new = function() return {} end }
Color = setmetatable({new=function() return {} end}, {__index=function() return {} end})
local mp = snapshot .. '/content/108600/3781448194/mods/TLOU_Infected_MP/42.20/media/lua/shared/TLOU_infected.lua'
assert(loadfile(mp))()
local core = snapshot .. '/content/108600/3776274080/mods/ZomboidForge_B42_20/42.20/media/lua/shared/ZomboidForge_core.lua'
local f=assert(io.open(core)); local source=f:read('*a'); f:close()
local body=assert(source:match('ZomboidForge%.OnLoad = function%(%)%s*(.-)\nend'), 'Unknown OnLoad boundary')
triggerEvent=function(name,types)
    assert(name=='OnLoadZTypes'); tlou.Initialize_TLOUInfected(types)
end
forge.OnLoad=assert(loadstring('return function()\n'..body..'\nend'))()
forge.OnLoad()
local expected={TLOU_Runner=560,TLOU_Stalker=330,TLOU_Clicker=110}
local count=0
for k,v in pairs(forge.ZTypes) do
    assert(expected[k] and expected[k]==v.chance, 'Unexpected ZType/weight: '..k)
    print('REGISTRY '..k..' weight='..v.chance); count=count+1
end
assert(count==3 and forge.TotalChance==1000)
assert(not forge.ZTypes.ZF_Zomboid and not forge.ZTypes.TLOU_Vanilla and not forge.ZTypes.TLOU_Bloater)
for _,k in ipairs({'TLOU_Stalker','TLOU_Clicker'}) do
    local found=false
    for _,fn in ipairs(forge.ZTypes[k].onTick or {}) do if fn==tlou.HideIndoors then found=true end end
    assert(found, 'HideIndoors not installed on '..k)
end
-- Repeat initialization: no stale ordinary types or accumulated registry weights.
forge.OnLoad(); assert(forge.TotalChance==1000)
print('PASS: actual Forge/TLOU registry: special types only, weights 560/330/110, indoor callbacks attached')
