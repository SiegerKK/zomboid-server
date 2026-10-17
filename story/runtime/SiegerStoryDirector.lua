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
local QUEST_LEDGER = "SiegerStoryQuestEvents.txt"

-- Stable, server-authored provenance. Online zombie IDs may change, so
-- the token (scene:action:ordinal) is the identity, not getOnlineID().
local function tagQuestObject(object, scene, actionId, token, kind)
    local md=object:getModData()
    if not md then error("Quest target has no modData") end
    md["SiegerStoryToken"]=token
    md["SiegerStoryQuest"]=scene
    md["SiegerStoryAction"]=actionId
    md["SiegerStoryKind"]=kind
end

-- Append-only audit trail; contents are private to the world, not published
-- to Git. This complements (does not replace) object modData.
local function recordQuestEvent(event, scene, actionId, token, kind, x, y, z, onlineId)
    local ok,err=pcall(function()
        local writer=getFileWriter(QUEST_LEDGER,true,true)
        if not writer then error("Ledger writer unavailable") end
        writer:write(table.concat({"v1",event,scene,actionId,token,kind,
            tostring(x),tostring(y),tostring(z),tostring(onlineId or -1)},"\t").."\n")
        writer:close()
    end)
    if not ok then
        print("SIEGER_STORY_LEDGER_ERROR "..tostring(err))
    end
    return ok
end

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
    -- In-memory API probe in the actual game JVM. No square, inventory or
    -- save mutation; this also catches Java methods hidden from Kahlua.
    local ok,err=pcall(function()
        local note=instanceItem("Base.Note")
        assert(note,"Base.Note unavailable")
        note:setCanBeWrite(true)
        note:setNumberOfPages(1)
        note:addPage(1,"Story API check")
        assert(note:canBeWrite() and note:getNumberOfPages()==1)
        assert(note:seePage(1)=="Story API check")
        local notebook=instanceItem("Base.Notebook")
        assert(notebook and notebook:getPageToWrite()>=8,"Notebook page capacity unavailable")
        assert(sendAddItemToContainer,"sendAddItemToContainer unavailable")
    end)
    if not ok then
        log("ERROR","Read-only API preflight failed: "..tostring(err))
        return false
    end
    log("API","Base.Note pages/readability and container sync API available")
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
    -- Kahlua does not necessarily expose java.lang.Object.getClass().
    for _,cls in ipairs({"IsoWindow", "IsoDoor", "IsoThumpable", "IsoBarricade", "IsoObject"}) do
        if instanceof(obj,cls) then return cls end
    end
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
        if container then
            local items=container:getItems()
            for j=0,math.min(items:size()-1,49) do
                local item=items:get(j)
                local token=item:getModData()["SiegerStoryToken"]
                if token then
                    log("INSPECT", "square="..k.." index="..i..
                        " story_item="..tostring(item:getFullType())..
                        " token="..tostring(token).." name="..tostring(item:getName()))
                end
            end
        end
    end
    local ground=square:getWorldObjects()
    for i=0,math.min(ground:size()-1,49) do
        local item=ground:get(i):getItem()
        local token=item and item:getModData()["SiegerStoryToken"]
        if token then
            log("INSPECT", "square="..k.." ground_story_item="..
                tostring(item:getFullType()).." token="..tostring(token)..
                " name="..tostring(item:getName()))
        end
    end
    inspectors[k]=nil -- inspect once, do not revisit on every periodic poll
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

local function placeItem(square, scene, action, item, token)
    tagQuestObject(item,scene,action.id,token,"item")
    if action.placement=="ground" then
        local spawned=square:AddWorldInventoryItem(item,0.5,0.5,0)
        if not spawned then error("AddWorldInventoryItem returned no item") end
    elseif action.placement=="container" then
        -- Check networking BEFORE mutation, otherwise a retry could find an
        -- unsynchronised item and incorrectly mark the action complete.
        if not sendAddItemToContainer then
            error("Build 42 sendAddItemToContainer is unavailable")
        end
        local obj=targetObject(square,action.selector)
        local container=obj:getContainer()
        if not container then error("Selected object has no container") end
        local added=container:AddItem(item)
        if not added then error("ItemContainer.AddItem failed") end
        sendAddItemToContainer(container,added)
    else
        error("Invalid placement")
    end
    if not recordQuestEvent("spawn",scene,action.id,token,"item",
                            square:getX(),square:getY(),square:getZ(),-1) then
        square:getModData()["SiegerStory:"..scene..":"..action.id..":ledger_error"]=true
        square:transmitModdata()
        error("Item created but quest ledger failed; manual review required")
    end
end

local function spawnTaggedZombie(square,scene,action,token)
    if action.subtype~="vanilla" or action.count~=1 then
        error("Only one vanilla zombie per action is allowed")
    end
    if not addZombiesInOutfit then error("Build 42 addZombiesInOutfit missing") end
    -- No furniture mutation, no arbitrary script, no TLOU class assumption.
    local zombies=addZombiesInOutfit(square:getX(),square:getY(),square:getZ(),1,nil,nil)
    if not zombies or zombies:size()~=1 then
        error("addZombiesInOutfit did not return one zombie")
    end
    local zombie=zombies:get(0)
    if not zombie or not instanceof(zombie,"IsoZombie") then
        error("Spawn API returned non-zombie")
    end
    tagQuestObject(zombie,scene,action.id,token,"infected")
    local onlineId=-1
    local ok,value=pcall(function() return zombie:getOnlineID() end)
    if ok and value then onlineId=value end
    if not recordQuestEvent("spawn",scene,action.id,token,"infected",
                            math.floor(zombie:getX()),math.floor(zombie:getY()),
                            math.floor(zombie:getZ()),onlineId) then
        error("Zombie created but quest ledger failed; do not retry blindly")
    end
end

-- A bathroom corpse and its nearby revolver form ONE live action, so
-- the revolver cannot appear as a success if the body spawn fails.
-- No zombie AI is involved and no existing body is deleted.
local function spawnBathroomCorpse(square,scene,action,flag)
    if action.room~="bathroom" or action.ground_item~="Base.Revolver"
        or type(action.blood)~="number" or action.blood<0 or action.blood>3 then
        error("Unapproved corpse parameters")
    end
    local room=square:getRoom()
    if not room or tostring(room:getName())~="bathroom" then
        error("Corpse target is no longer a bathroom")
    end
    local objects=square:getObjects()
    local floor=objects and objects:size()>0 and objects:get(0)
    if not floor or spriteName(floor)~=action.floor_sprite then
        error("Corpse target floor tile changed; manual remap required")
    end
    if not square.getDeadBodys then error("IsoGridSquare.getDeadBodys unavailable") end
    local before=square:getDeadBodys()
    if not before then error("Corpse registry unavailable") end
    if before:size()>0 then error("Corpse already occupies target square") end
    if not createRandomDeadBody then error("Build 42 createRandomDeadBody missing") end
    local gun=instanceItem(action.ground_item)
    if not gun then error("Base.Revolver unavailable in pinned game scripts") end
    if not square.AddWorldInventoryItem then error("Ground item API unavailable") end

    -- This mark precedes the first mutation. After an ambiguous server crash,
    -- retrying could duplicate bodies; require manual inspection instead.
    local md=square:getModData()
    md[flag..":spawn_attempted"]=true
    square:transmitModdata()
    local body=createRandomDeadBody(square,action.blood)
    if not body or not instanceof(body,"IsoDeadBody") then
        error("Corpse API did not return IsoDeadBody; retry prohibited")
    end
    local after=square:getDeadBodys()
    if not after or after:size()~=1 or after:get(0)~=body then
        error("Corpse API did not register exactly one body on target square")
    end
    tagQuestObject(body,scene,action.id,flag..":corpse","corpse")
    if body.transmitModdata then body:transmitModdata() end
    if not recordQuestEvent("spawn",scene,action.id,flag..":corpse","corpse",
                            square:getX(),square:getY(),square:getZ(),-1) then
        error("Corpse created but audit ledger failed; manual review needed")
    end
    -- The gun has a distinct token even though it shares an exact tile.
    -- Position within the tile is set apart from the corpse's default center.
    tagQuestObject(gun,scene,action.id,flag..":revolver","item")
    local placed=square:AddWorldInventoryItem(gun,0.72,0.60,0)
    if not placed then error("Corpse created but revolver placement failed") end
    if not recordQuestEvent("spawn",scene,action.id,flag..":revolver","item",
                            square:getX(),square:getY(),square:getZ(),-1) then
        error("Revolver created but audit ledger failed; manual review needed")
    end
end

local function onZombieDead(zombie)
    if not zombie then return end
    local ok,err=pcall(function()
        local md=zombie:getModData()
        if not md or md["SiegerStoryKind"]~="infected"
            or not md["SiegerStoryToken"] or md["SiegerStoryDeathLogged"] then return end
        local onlineId=-1
        local got,id=pcall(function() return zombie:getOnlineID() end)
        if got and id then onlineId=id end
        if recordQuestEvent("dead",md["SiegerStoryQuest"],md["SiegerStoryAction"],
            md["SiegerStoryToken"],"infected",
            math.floor(zombie:getX()),math.floor(zombie:getY()),
            math.floor(zombie:getZ()),onlineId) then
            md["SiegerStoryDeathLogged"]=true
        end
    end)
    if not ok then print("SIEGER_STORY_LEDGER_ERROR death "..tostring(err)) end
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
    -- Use the stock notebook for every authored document. Base.Note may have
    -- PageToWrite=0 in the actual B42 script despite supporting addPage().
    local itemType="Base.Notebook"
    local item=instanceItem(itemType)
    if not item then error(itemType.." unavailable in this Build 42") end
    if item:getPageToWrite()< #action.pages then error("Item script has insufficient page capacity") end
    if not item.addPage then error("Base.Note does not implement addPage") end
    item:setName(action.title)
    item:setCustomName(true)
    -- B42 Base.Note has ReadType=photo and is not writable by default.
    -- The vanilla Read Note context menu requires canBeWrite() and pages.
    item:setCanBeWrite(true)
    item:setNumberOfPages(#action.pages)
    -- PageToWrite comes from the item script and is not serialized.
    -- Notebook has ten slots on both server and vanilla clients.
    for i,page in ipairs(action.pages) do item:addPage(i,page) end
    return item
end

local function doAction(square, scene, action)
    local md=square:getModData()
    local flag="SiegerStory:"..scene..":"..action.id
    if md[flag..":ledger_error"] then error("Previous ledger failure requires manual review") end
    if md[flag] == true then return "already" end

    if action.type=="note" then
        if not itemExists(square,action,flag..":1") then
            placeItem(square,scene,action,noteItem(action),flag..":1")
        end
    elseif action.type=="loot" then
        for j,entry in ipairs(action.items) do
            for n=1,entry.count do
                local token=flag..":"..j..":"..n
                if not itemExists(square,action,token) then
                    local item=instanceItem(entry.type)
                    if not item then error("Unknown item type: "..entry.type) end
                    placeItem(square,scene,action,item,token)
                end
            end
        end
    elseif action.type=="corpse" then
        if md[flag..":spawn_attempted"] then
            error("Previous corpse attempt is uncertain; automatic retry prohibited")
        end
        spawnBathroomCorpse(square,scene,action,flag)
    elseif action.type=="infected" then
        if action.subtype~="vanilla" or action.count~=1 then
            error("Unsupported infected subtype/count")
        end
        if md[flag..":spawn_attempted"] then
            error("Previous spawn attempt is uncertain; automatic retry refused")
        end
        if not addZombiesInOutfit then error("Build 42 addZombiesInOutfit missing") end
        md[flag..":spawn_attempted"]=true
        square:transmitModdata()
        spawnTaggedZombie(square,scene,action,flag..":1")
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
    return "applied"
end

local function processSquare(square)
    if not square then return end
    if not boot() then return end
    inspect(square)
    local k=key(square:getX(),square:getY(),square:getZ())
    local actions=bySquare[k]
    if not actions then return end
    local pending=false
    for _,entry in ipairs(actions) do
        local token=entry.scene.."."..entry.action.id
        if not errorTimes[token] or tickNumber-errorTimes[token]>=1800 then
            local ok,err=pcall(doAction,square,entry.scene,entry.action)
            if not ok then
                pending=true
                errorTimes[token]=tickNumber
                log("ERROR","scene="..entry.scene.." action="..entry.action.id..
                    " reason="..tostring(err))
            else
                errorTimes[token]=nil
            end
        else
            pending=true -- retain failed actions until their retry window
        end
    end
    if not pending then
        bySquare[k]=nil -- persistent square modData remains idempotency authority
    end
end


-- Live editing session: bounded root-issued request file in /root/Zomboid/Lua.
-- It contains only fixed tagged data, NEVER executable Lua or RCON text.
local LIVE_REQUEST = "SiegerStoryLiveRequest.txt"
local LIVE_RESULT = "SiegerStoryLiveResult.txt"
local LIVE_MAX_BYTES = 128 * 1024
local liveLastId = nil
local liveJob = nil

-- Kahlua strings are Java UTF-16 strings; stock Lua 5.1 strings are bytes.
local wideStrings=pcall(string.char,256)
local function hex(str)
    local source=tostring(str or "")
    local encoded={}
    local function byte(n) encoded[#encoded+1]=string.format("%02x",n) end
    local i=1
    while i<=#source do
        local c=source:byte(i);i=i+1
        if wideStrings then
            if c>=55296 and c<=56319 then
                local lo=source:byte(i)
                if not lo or lo<56320 or lo>57343 then error("Invalid UTF-16 surrogate") end
                c=65536+(c-55296)*1024+lo-56320;i=i+1
            elseif c>=56320 and c<=57343 then error("Invalid UTF-16 surrogate") end
            if c<128 then byte(c)
            elseif c<2048 then byte(192+math.floor(c/64));byte(128+c%64)
            elseif c<65536 then
                byte(224+math.floor(c/4096));byte(128+math.floor(c/64)%64);byte(128+c%64)
            else
                byte(240+math.floor(c/262144));byte(128+math.floor(c/4096)%64)
                byte(128+math.floor(c/64)%64);byte(128+c%64)
            end
        else byte(c) end
    end
    return table.concat(encoded)
end

local function unhex(str,limit)
    if #str%2~=0 or #str>limit*2 or not str:match("^[0-9a-f]*$") then
        error("Invalid hex-encoded text")
    end
    local bytes={}
    for i=1,#str,2 do bytes[#bytes+1]=tonumber(str:sub(i,i+1),16) end
    local result={}
    local i=1
    while i<=#bytes do
        local first=bytes[i]
        local count,cp,min=1,first,0
        if first>=194 and first<=223 then count=2;cp=first-192;min=128
        elseif first>=224 and first<=239 then count=3;cp=first-224;min=2048
        elseif first>=240 and first<=244 then count=4;cp=first-240;min=65536
        elseif first>=128 then error("Invalid UTF-8 leading byte") end
        for j=1,count-1 do
            local c=bytes[i+j]
            if not c or c<128 or c>191 then error("Invalid UTF-8 continuation") end
            cp=cp*64+c-128
        end
        if cp<min or cp>1114111 or (cp>=55296 and cp<=57343) then error("Invalid UTF-8 codepoint") end
        if wideStrings then
            if cp>65535 then
                cp=cp-65536;result[#result+1]=string.char(55296+math.floor(cp/1024),56320+cp%1024)
            else result[#result+1]=string.char(cp) end
        else
            for j=0,count-1 do result[#result+1]=string.char(bytes[i+j]) end
        end
        i=i+count
    end
    return table.concat(result)
end

local function tabs(line)
    local t,idx={},1
    while true do
        local pos=string.find(line,"\t",idx,true)
        if pos then t[#t+1]=line:sub(idx,pos-1);idx=pos+1
        else t[#t+1]=line:sub(idx);return t end
    end
end

local function exactInteger(raw,min,max)
    if not raw or not raw:match("^%-?%d+$") then error("Integer field malformed") end
    local num=tonumber(raw)
    if not num or num<min or num>max then error("Integer out of range") end
    return num
end

local function validIdentifier(raw)
    return type(raw)=="string" and #raw>=3 and #raw<=64
        and raw:match("^[a-z][a-z0-9_-]+$")~=nil
end

local function decodeLine(line)
    local a=tabs(line)
    local typ=a[1]
    if typ~="note" and typ~="loot" and typ~="infected" and typ~="corpse" then
        error("Disallowed live action type")
    end
    local expected=(typ=="note" and 12) or (typ=="loot" and 10)
        or (typ=="infected" and 11) or 13
    if #a~=expected then error("Unexpected live action field count") end
    if not validIdentifier(a[2]) then error("Invalid live action id") end
    local x=exactInteger(a[3],0,40000)
    local y=exactInteger(a[4],0,40000)
    local z=exactInteger(a[5],-2,16)
    local place=a[6]
    if typ=="infected" or typ=="corpse" then
        if place~="-" then error("Actor may not have a placement selector") end
    elseif place~="ground" and place~="container" then
        error("Invalid placement")
    end
    local index=exactInteger(a[7],-1,255)
    local sprite,cls=a[8],a[9]
    local sel=nil
    if place=="container" then
        if index<0 or not sprite:match("^[A-Za-z0-9_]+$") or #sprite>90 or cls~="IsoObject" then
            error("Unsafe container selector")
        end
        sel={object_index=index,sprite=sprite,class=cls}
    elseif index~=-1 or sprite~="-" or cls~="-" then
        error("Non-container action has unexpected selector")
    end
    local obj={id=a[2],type=typ,at={x=x,y=y,z=z},placement=place,selector=sel}
    if typ=="infected" then
        if a[10]~="vanilla" or exactInteger(a[11],1,1)~=1 then
            error("Only a single vanilla infected spawn is permitted")
        end
        obj.subtype="vanilla"
        obj.count=1
    elseif typ=="corpse" then
        if a[10]~="bathroom" then error("Only bathroom corpses are approved") end
        if #a[11]<3 or #a[11]>90 or not a[11]:match("^[A-Za-z0-9_]+$") then
            error("Unsafe corpse floor selector")
        end
        if a[13]~="Base.Revolver" then error("Only Base.Revolver allowed with corpse") end
        obj.room="bathroom"
        obj.floor_sprite=a[11]
        obj.blood=exactInteger(a[12],0,3)
        obj.ground_item="Base.Revolver"
    elseif typ=="note" then
        obj.title=unhex(a[10],120*4)
        if obj.title=="" then error("Empty note title") end
        local count=exactInteger(a[11],1,8)
        obj.pages={}
        for chunk in string.gmatch(a[12],"([^:]+)") do
            obj.pages[#obj.pages+1]=unhex(chunk,2000*4)
            if #obj.pages>8 then error("Too many note pages") end
        end
        if #obj.pages~=count then error("Mismatched note pages") end
    else
        obj.items={}
        for chunk in string.gmatch(a[10],"([^;]+)") do
            local item,count=chunk:match("^([A-Za-z][A-Za-z0-9_]*%.[A-Za-z][A-Za-z0-9_]*)=(%d+)$")
            if not item then error("Unsafe loot item token") end
            obj.items[#obj.items+1]={type=item,count=exactInteger(count,1,20)}
            if #obj.items>25 then error("Too many item types") end
        end
        if #obj.items==0 then error("Loot is empty") end
    end
    return obj
end

local function parseLiveRequest()
    local ok,reader=pcall(getFileReader,LIVE_REQUEST,false)
    if not ok or not reader then return nil end
    local okParse,result=pcall(function()
        local line=reader:readLine()
        if not line then return nil end
        local hdr=tabs(line)
        if #hdr~=6 or hdr[1]~="v1" or not hdr[2]:match("^[0-9a-f]+$") or #hdr[2]~=32
           or not validIdentifier(hdr[3]) or not validIdentifier(hdr[4])
           or not hdr[5]:match("^[0-9a-f]+$") or #hdr[5]~=64 then
            error("Invalid live request header")
        end
        local count=exactInteger(hdr[6],1,32)
        if not STORY or hdr[3]~=STORY.world then error("World mismatch in live request") end
        if hdr[2]==liveLastId then return nil end
        local bytes=#line
        local parsed={id=hdr[2],world=hdr[3],scene=hdr[4],sha=hdr[5],actions={}}
        local keys={}
        for i=1,count do
            local content=reader:readLine()
            if not content then error("Truncated live request") end
            bytes=bytes+#content+1
            if bytes>LIVE_MAX_BYTES then error("Live request too large") end
            local action=decodeLine(content)
            if keys[action.id] then error("Duplicate action ID") end
            keys[action.id]=true
            parsed.actions[#parsed.actions+1]={data=action,state="pending",reason=""}
        end
        if reader:readLine()~=nil then error("Extra live request data") end
        return parsed
    end)
    pcall(function() reader:close() end)
    if not okParse then log("LIVE_ERROR","request refused: "..tostring(result));return nil end
    return result
end

local function writeLiveResult(job)
    local ok,writer=pcall(getFileWriter,LIVE_RESULT,true,false)
    if not ok or not writer then error("Live response writer unavailable") end
    local okWrite,err=pcall(function()
        writer:write(table.concat({"v1",job.id,job.world,job.scene,job.sha,tostring(#job.actions)},"\t").."\n")
        local applied,pending,failed=0,0,0
        for _,entry in ipairs(job.actions) do
            if entry.state=="pending" then pending=pending+1
            elseif entry.state=="error" then failed=failed+1
            else applied=applied+1 end
            writer:write(table.concat({"action",entry.data.id,entry.state,hex(entry.reason)},"\t").."\n")
        end
        local status = failed>0 and "failed" or (pending>0 and "pending" or "complete")
        writer:write(table.concat({"end",job.id,status,tostring(applied),tostring(pending),tostring(failed)},"\t").."\n")
        job.status=status
    end)
    pcall(function() writer:close() end)
    if not okWrite then error(err) end
end

local function tickLive()
    if not boot() then return end
    if not liveJob then
        local job=parseLiveRequest()
        if job then
            liveLastId=job.id
            liveJob=job
            log("LIVE_ACCEPTED","request="..job.id.." scene="..job.scene.." count="..#job.actions)
            local ok,err=pcall(writeLiveResult,job)
            if not ok then log("LIVE_ERROR","cannot send receipt "..tostring(err)) end
        end
    end
    if not liveJob then return end
    local job=liveJob
    local changed=false
    for _,entry in ipairs(job.actions) do
        if entry.state=="pending" then
            local at=entry.data.at
            local square=getCell() and getCell():getGridSquare(at.x,at.y,at.z)
            if square then
                local ok,outcome=pcall(doAction,square,job.scene,entry.data)
                if ok then
                    entry.state=outcome=="already" and "already" or "applied"
                    entry.reason=""
                else
                    entry.state="error"
                    entry.reason=tostring(outcome):sub(1,400)
                    log("LIVE_ERROR","scene="..job.scene.." action="..entry.data.id..
                        " reason="..entry.reason)
                end
                changed=true
            end
        end
    end
    if changed then
        local ok,err=pcall(writeLiveResult,job)
        if not ok then log("LIVE_ERROR","response write failed: "..tostring(err)) end
    end
    if job.status=="complete" or job.status=="failed" then
        log("LIVE_RESULT","request="..job.id.." status="..job.status)
        liveJob=nil
    end
end

local function periodic()
    tickNumber=tickNumber+1
    if tickNumber%60==0 then tickLive() end
    if tickNumber%300~=0 then return end
    if next(bySquare)==nil and next(inspectors)==nil then return end
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

if Events.OnZombieDead then Events.OnZombieDead.Add(onZombieDead) end
if Events.LoadGridsquare then Events.LoadGridsquare.Add(processSquare) end
if Events.OnTick then Events.OnTick.Add(periodic) end
if Events.OnServerStarted then Events.OnServerStarted.Add(boot) end
