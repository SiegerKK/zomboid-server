-- SiegerStoryDirector v1 (Build 42.21): isolated, server-only scene executor.
-- The global SiegerStoryScenes table is generated exclusively from validated
-- JSON and mounted read-only ONLY for the selected world by compose.story.yaml.
-- NEVER accept Lua/RCON sent by players. Scene execution is not rollback.
if isClient and isClient() then return end

local PREFIX = "SIEGER_STORY"
local STORY = nil
local bySquare = {}
local inspectors = {}
local inspected = {}
local errorTimes = {}
local tickNumber = 0

local function log(kind, message)
    print(PREFIX .. "_" .. kind .. " " .. tostring(message))
end

local function key(x,y,z)
    return tostring(x) .. ":" .. tostring(y) .. ":" .. tostring(z)
end

local function boot()
    local data = SiegerStoryScenes
    if type(data) ~= "table" or data.schema ~= 1 then
        log("ERROR", "No valid compiled scene bundle loaded")
        return false
    end
    if STORY == data then return true end
    STORY = data
    bySquare = {}
    inspectors = {}
    for _,s in ipairs(data.scenes or {}) do
        for _,a in ipairs(s.actions or {}) do
            local at = a.at
            local k = key(at.x, at.y, at.z)
            bySquare[k] = bySquare[k] or {}
            table.insert(bySquare[k], {scene=s.id, action=a})
        end
    end
    for _,p in ipairs(data.inspect or {}) do
        inspectors[key(p.x, p.y, p.z)] = true
    end
    log("READY", "world="..tostring(data.world).." scenes="..
        tostring(#(data.scenes or {})).." read_only_probes="..
        tostring(#(data.inspect or {})))
    return true
end

local function spriteName(obj)
    if not obj then return "<null>" end
    local sp = obj:getSprite()
    return sp and sp:getName() or "<no-sprite>"
end

local function className(obj)
    local ok,value = pcall(function() return obj:getClass():getSimpleName() end)
    return ok and tostring(value) or "<unknown>"
end

local function inspect(square)
    local k=key(square:getX(),square:getY(),square:getZ())
    if not inspectors[k] or inspected[k] then return end
    inspected[k]=true
    local room=square:getRoom()
    local roomName="<none>"
    if room then
        local ok,value=pcall(function() return room:getName() end)
        if ok and value then roomName=tostring(value) end
    end
    log("INSPECT", "square="..k.." room="..roomName)
    local objects=square:getObjects()
    for i=0,math.min(objects:size()-1,255) do
        local obj=objects:get(i)
        local container=obj:getContainer()
        local info="index="..i.." class="..className(obj)..
            " sprite="..spriteName(obj)
        if container then
            info=info.." container="..tostring(container:getType())..
                " items="..tostring(container:getItems():size())
        end
        log("INSPECT", "square="..k.." "..info)
    end
    log("INSPECT", "square="..k.." completed; exact indexes can change after map edits")
end

local function targetObject(square, selector)
    local objects=square:getObjects()
    local index=selector.object_index
    if index<0 or index>=objects:size() then
        error("expected object index is absent: "..tostring(index))
    end
    local obj=objects:get(index)
    if not instanceof(obj,selector.class) then
        error("class changed at index "..index..": "..className(obj))
    end
    if spriteName(obj)~=selector.sprite then
        error("sprite changed: expected "..selector.sprite.." got "..spriteName(obj))
    end
    return obj
end

local function placeItem(square, action, item, token)
    item:getModData()["SiegerStoryToken"]=token
    if action.placement=="ground" then
        local spawned=square:AddWorldInventoryItem(item,0.5,0.5,0)
        if not spawned then error("AddWorldInventoryItem returned no item") end
    elseif action.placement=="container" then
        local obj=targetObject(square,action.selector)
        local container=obj:getContainer()
        if not container then error("Selected object has no container") end
        local added=container:AddItem(item)
        if not added then error("ItemContainer.AddItem failed") end
        if not sendAddItemToContainer then
            error("Build 42 sendAddItemToContainer is unavailable")
        end
        sendAddItemToContainer(container,added)
    else
        error("Invalid placement")
    end
end

local function itemExists(square, action, token)
    local items=nil
    if action.placement=="container" then
        local obj=targetObject(square,action.selector)
        local container=obj:getContainer()
        if not container then error("Container missing at selected object") end
        items=container:getItems()
    else
        items=square:getWorldObjects()
    end
    for i=0,items:size()-1 do
        local candidate=items:get(i)
        if action.placement=="ground" then candidate=candidate:getItem() end
        if candidate and candidate:getModData()["SiegerStoryToken"]==token then
            return true
        end
    end
    return false
end

local function noteItem(action)
    local item=instanceItem("Base.Note")
    if not item then error("Base.Note unavailable in this Build 42") end
    if not item.addPage then error("Base.Note does not implement addPage") end
    item:setName(action.title)
    for i,page in ipairs(action.pages) do item:addPage(i,page) end
    return item
end

local function doAction(square, scene, action)
    local md=square:getModData()
    local flag="SiegerStory:"..scene..":"..action.id
    if md[flag] == true then return end

    if action.type=="note" then
        if not itemExists(square,action,flag..":1") then
            placeItem(square,action,noteItem(action),flag..":1")
        end
    elseif action.type=="loot" then
        for j,entry in ipairs(action.items) do
            for n=1,entry.count do
                local token=flag..":"..j..":"..n
                if not itemExists(square,action,token) then
                    local item=instanceItem(entry.type)
                    if not item then error("Unknown item type: "..entry.type) end
                    placeItem(square,action,item,token)
                end
            end
        end
    elseif action.type=="barricade" then
        local obj=targetObject(square,action.selector)
        if not obj.isBarricadeAllowed or not obj:isBarricadeAllowed() then
            error("Target object cannot be barricaded")
        end
        if obj:getBarricadeOnSameSquare() or obj:getBarricadeOnOppositeSquare() then
            error("Window/door already has a barricade; refusing to modify it")
        end
        local barr=IsoBarricade.AddBarricadeToObject(obj,false)
        if not barr then error("IsoBarricade creation failed") end
        for i=1,action.planks do
            if not barr:canAddPlank() then error("Cannot add requested planks") end
            barr:addPlank(nil,nil)
        end
        barr:transmitCompleteItemToClients()
    else
        error("Action type is not approved for server runtime: "..tostring(action.type))
    end

    md[flag]=true
    square:transmitModdata()
    log("APPLIED","scene="..scene.." action="..action.id..
        " square="..key(square:getX(),square:getY(),square:getZ()))
end

local function processSquare(square)
    if not square then return end
    if not boot() then return end
    inspect(square)
    local k=key(square:getX(),square:getY(),square:getZ())
    local actions=bySquare[k]
    if not actions then return end
    for _,entry in ipairs(actions) do
        local token=entry.scene.."."..entry.action.id
        if not errorTimes[token] or tickNumber-errorTimes[token]>=1800 then
            local ok,err=pcall(doAction,square,entry.scene,entry.action)
            if not ok then
                errorTimes[token]=tickNumber
                log("ERROR","scene="..entry.scene.." action="..entry.action.id..
                    " reason="..tostring(err))
            end
        end
    end
end

local function periodic()
    tickNumber=tickNumber+1
    if tickNumber%300~=0 then return end
    if not boot() then return end
    local cell=getCell()
    if not cell then return end
    for k,_ in pairs(bySquare) do
        local x,y,z=string.match(k,"^(-?%d+):(-?%d+):(-?%d+)$")
        if x then processSquare(cell:getGridSquare(tonumber(x),tonumber(y),tonumber(z))) end
    end
    for k,_ in pairs(inspectors) do
        local x,y,z=string.match(k,"^(-?%d+):(-?%d+):(-?%d+)$")
        if x then processSquare(cell:getGridSquare(tonumber(x),tonumber(y),tonumber(z))) end
    end
end

if Events.LoadGridsquare then Events.LoadGridsquare.Add(processSquare) end
if Events.OnTick then Events.OnTick.Add(periodic) end
if Events.OnServerStarted then Events.OnServerStarted.Add(boot) end
