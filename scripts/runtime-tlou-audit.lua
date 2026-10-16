-- Read-only server-side diagnostics. No spawn, movement or gameplay changes.
-- Server-only base Lua; never added to the Workshop client/shared checksum.
Events.OnServerStarted.Add(function()
    if not SandboxVars.TLOU_infected then return end
    local function emit(key,value)
        print("ROAD_HOME_AUDIT " .. key .. "=" .. tostring(value))
    end
    local ok, err = pcall(function()
        local paths = {
            "StartMonth", "StartDay", "DayLength", "TimeSinceApo", "Temperature",
            "Rain", "Zombies", "ZombieConfig.PopulationMultiplier",
            "ZombieConfig.RespawnHours", "ZombieConfig.RespawnMultiplier",
            "AmmoLootNew", "RangedWeaponLootNew", "MultiplierConfig.GlobalToggle",
            "MultiplierConfig.Strength", "MultiplierConfig.Fitness",
            "MultiplierConfig.Mechanics", "MultiplierConfig.Woodwork",
            "TLOU_infected.VanillaSpawn", "TLOU_infected.VanillaSpawnWeight",
            "TLOU_infected.RunnerSpawnWeight", "TLOU_infected.StalkerSpawnWeight",
            "TLOU_infected.ClickerSpawnWeight", "TLOU_infected.BloaterSpawn",
            "TLOU_infected.HideIndoors", "TLOU_infected.OnlyUnexplored",
            "TLOU_infected.WanderAtNight"
        }
        for _,path in ipairs(paths) do
            local value=SandboxVars
            for part in string.gmatch(path,"[^.]+") do value=value[part] end
            emit(path,value)
        end
        local clock=getGameTime()
        emit("calendar", tostring(clock:getYear()).."-"..tostring(clock:getMonth()+1).."-"..tostring(clock:getDay()+1))
        local climateOK, temperature=pcall(function() return getClimateManager():getTemperature():getFinalValue() end)
        if climateOK then emit("ambient_temperature",temperature) end
        local nativeOK, population=pcall(function()
            return getSandboxOptions():getOptionByName("ZombieConfig.PopulationMultiplier"):getValue()
        end)
        if nativeOK then emit("native_population_multiplier",population) end
        local forge=require "ZomboidForge_module"
        local tlou=require "TLOU_infected_module"
        local keys={}
        for key,_ in pairs(forge.ZTypes or {}) do table.insert(keys,key) end
        table.sort(keys)
        for _,key in ipairs(keys) do
            emit("ZTYPE."..key,forge.ZTypes[key].chance)
            if key=="TLOU_Stalker" or key=="TLOU_Clicker" then
                local attached=false
                for _,fn in ipairs(forge.ZTypes[key].onTick or {}) do
                    if fn==tlou.HideIndoors then attached=true end
                end
                emit("INDOOR_CALLBACK."..key,attached)
            end
        end
        emit("REGISTRY_COUNT",#keys)
        emit("NORMAL_TYPE_PRESENT",forge.ZTypes.ZF_Zomboid~=nil or forge.ZTypes.TLOU_Vanilla~=nil)
        emit("COMPLETE",true)
    end)
    if not ok then emit("ERROR",err) end
end)
