-- Independent optional Viewpoint 42.21 Lua optimization.
-- The Viewpoint renderer/JAR, game render, saves, networking, and Steam files
-- are never modified. No native hooks and no remote telemetry.
if isServer and isServer() then return end

SiegerViewpointLite = SiegerViewpointLite or {}
local Lite = SiegerViewpointLite
local TTL_MS = 50 -- at 60 FPS: coalesce at most about three duplicate frames
local opt = nil
local originalHarvest, originalRun, wrappedHarvest
local cachedPlayer, cachedTarget, cachedActions, cachedResult, cachedAt
local attempts, misses, hits = 0, 0, 0

local function clear()
    cachedPlayer, cachedTarget, cachedActions, cachedResult, cachedAt = nil, nil, nil, nil, nil
end

local function log(message)
    print("[SiegerViewpointLite] " .. tostring(message))
end

local function enabled()
    -- Intentional fail-closed default: only the Mod Options checkbox enables it.
    if not opt or type(opt.getValue)~="function" then return false end
    local ok, value = pcall(opt.getValue, opt)
    return ok and value==true
end

local function millis()
    if type(getTimestampMs)~="function" then return nil end
    local ok, value = pcall(getTimestampMs)
    if not ok or type(value)~="number" or value~=value then return nil end
    return value
end

local function compatible()
    -- Do not suppress other known interaction/cursor mods' per-frame callbacks.
    return not ViewpointFixes and not ViewpointPlacementFix
end

local function installOptions()
    if opt or not (PZAPI and PZAPI.ModOptions) then return end
    local ok,err=pcall(function()
        local page=PZAPI.ModOptions:create("SiegerViewpointLite", "Viewpoint Lite (experimental)")
        opt=page:addTickBox(
            "cacheHarvest",
            "Reduce duplicate Viewpoint interaction menu builds",
            false,
            "Only repeats on exactly the same object within 50 ms. Experimental. Turn off if interaction options lag.")
        PZAPI.ModOptions:load()
    end)
    if not ok then opt=nil;log("options unavailable; cache remains disabled: "..tostring(err)) end
end

local function install()
    installOptions()
    if not ViewpointInteract or type(ViewpointInteract.harvest)~="function"
       or type(ViewpointInteract.run)~="function" then
        log("public interaction API unavailable; no patch applied")
        return
    end
    if wrappedHarvest and ViewpointInteract.harvest==wrappedHarvest then return end
    -- A changed downstream API or another wrapper after us naturally disables
    -- our cache; never force-install by bytecode guessing.
    originalHarvest=ViewpointInteract.harvest
    originalRun=ViewpointInteract.run
    ViewpointInteract.run=function(...)
        clear() -- a selected action may change inventory/world state immediately
        return originalRun(...)
    end

    wrappedHarvest=function(player,target,...)
        attempts=attempts+1
        local now=millis()
        if not enabled() or not compatible() or not now or target==nil
           or select("#",...)>0 then
            clear()
            return originalHarvest(player,target,...)
        end
        if cachedAt and now>=cachedAt and now-cachedAt<TTL_MS
           and cachedPlayer==player and cachedTarget==target
           and cachedActions==ViewpointInteract.actions
           and type(cachedResult)=="table" then
            hits=hits+1
            -- Viewpoint's Java caller consumes the original harvest result
            -- (title/labels/enabled/seen), not just the actions side effect.
            return cachedResult
        end
        clear()
        misses=misses+1
        local result=originalHarvest(player,target,...)
        -- Actual Viewpoint harvest returns a structured result table.
        -- Cache successful menu snapshots ONLY, not nil/error/why-only results.
        if type(result)=="table" and type(result.labels)=="table"
           and type(result.enabled)=="table"
           and type(ViewpointInteract.actions)=="table" then
            cachedPlayer, cachedTarget=player,target
            cachedActions,cachedResult,cachedAt=ViewpointInteract.actions,result,now
        end
        return result
    end
    ViewpointInteract.harvest=wrappedHarvest
    log("installed; cache OFF by default in Options > Mods; TTL=50ms, no Java hooks")
end

Lite.enabled=enabled
Lite.stats=function() return {attempts=attempts,misses=misses,hits=hits} end
Lite.clear=clear

if Events then
    if Events.OnGameBoot then Events.OnGameBoot.Add(installOptions) end
    if Events.OnGameStart then Events.OnGameStart.Add(install) end
    if Events.OnGameExit then Events.OnGameExit.Add(clear) end
    if Events.OnTick then Events.OnTick.Add(function()
        if not cachedAt then return end
        local now=millis()
        if not enabled() or not now or now<cachedAt or now-cachedAt>=TTL_MS then
            clear() -- don't retain world/player references when the menu closes
        end
    end) end
end
