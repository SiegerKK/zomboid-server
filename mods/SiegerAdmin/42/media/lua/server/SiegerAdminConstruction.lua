-- On-demand staged construction, dedicated-server only; private root-owned
-- request files, native Build 42 classes and native object replication.
-- No arbitrary code, chunk generation, global ticking mutations or world reset.
if isClient and isClient() then return end
local REQ="SiegerAdminConstructionRequest.txt"
local ACK="SiegerAdminConstructionResult.txt"
local GUARD="SiegerAdminConstructionGuard.txt"
local LEDGER="SiegerAdminConstructionStages.txt"
local MAX_PER_TICK=48
local POLL_TICKS=120
local tickCount=0
local initialized=false
local processed=nil
local job=nil
local function log(msg) print("SIEGER_ADMIN_CONSTRUCTION "..tostring(msg))end
local function split(line)
    local parts,at={},1
    while true do
        local n=line:find("\t",at,true)
        if not n then parts[#parts+1]=line:sub(at);return parts end
        parts[#parts+1]=line:sub(at,n-1);at=n+1
    end
end
local function word(s)
    return type(s)=="string" and #s>=1 and #s<=64 and
        s:match("^[A-Za-z0-9_][A-Za-z0-9_%-]*$")~=nil
end
local function spriteName(s)
    return type(s)=="string" and #s<=96 and
        s:match("^[A-Za-z][A-Za-z0-9_]*$")~=nil
end
local function itemName(s)
    return type(s)=="string" and #s<=96 and
        s:match("^[A-Za-z][A-Za-z0-9_]*%.[A-Za-z][A-Za-z0-9_]*$")~=nil
end
local function hash(s)
    return type(s)=="string" and #s==64 and s:match("^[0-9a-f]+$")~=nil
end
local function requestId(s)
    return type(s)=="string" and #s==32 and s:match("^[0-9a-f]+$")~=nil
end
local function integer(s,low,high)
    if type(s)~="string" or not s:match("^%-?%d+$") then error("not_integer") end
    local n=tonumber(s)
    if not n or n~=math.floor(n) or n<low or n>high then error("integer_out_of_range")end
    return n
end
local function writeAck(id,world,settlement,stage,digest,status,applied,count,reason)
    local w=getFileWriter(ACK,true,false)
    if not w then error("ack_writer_missing") end
    w:write(table.concat({"v1",id,world,settlement,stage,digest,status,
        tostring(applied),tostring(count),reason},"\t").."\n")
    w:close()
end
local function readHeader(name)
    local r=getFileReader(name,false)
    if not r then return nil end
    local a,b=r:readLine(),r:readLine();r:close()
    if not a or b or #a>520 then error("unsafe_control_file") end
    return a
end
local function writeGuard(id,settlement,stage)
    if readHeader(GUARD)==id then error("replayed_request")end
    local w=getFileWriter(GUARD,true,false)
    if not w then error("guard_writer_missing")end
    w:write(id.."\n");w:close()
    if readHeader(GUARD)~=id then error("guard_persistence_failed")end
end
local function ledger()
    local found={}
    local r=getFileReader(LEDGER,false)
    if not r then return found end
    while true do
        local line=r:readLine()
        if not line then break end
        local f=split(line)
        if #f~=3 or not word(f[1]) or not word(f[2]) or not hash(f[3])then
            r:close();error("invalid_construction_stage_ledger")end
        local key=f[1]..":"..f[2]
        if found[key] then r:close();error("duplicate_construction_stage_ledger")end
        found[key]=f[3]
    end
    r:close()
    return found
end
local function markStage(j)
    local w=getFileWriter(LEDGER,true,true)
    if not w then error("stage_ledger_writer_missing")end
    w:write(j.settlement.."\t"..j.stage.."\t"..j.digest.."\n")
    w:close()
end
local function currentWorld(world)
    if not SiegerStoryScenes or SiegerStoryScenes.world~=world then
        error("active_story_world_mismatch")end
end
local function square(x,y,z)
    local cell=getCell and getCell()
    if not cell or not cell.getGridSquare then error("game_cell_api_missing")end
    local sq=cell:getGridSquare(x,y,z)
    if not sq then error("target_square_not_loaded")end
    return sq
end
local function allObjects(sq)
    local o=sq.getObjects and sq:getObjects()
    if not o or not o.size or not o.get then error("square_objects_unavailable")end
    return o
end
local function sprite(name)
    if not spriteName(name) or not getSprite then error("sprite_api_missing")end
    local found=getSprite(name)
    if not found or not found.getName or tostring(found:getName())~=name then
        error("uninstalled_sprite")end
    return found
end
local function classOf(obj,n)
    if not instanceof then error("instanceof_api_unavailable")end
    return instanceof(obj,n)==true
end
local function matches(obj,kind)
    return classOf(obj,kind)
end
local function spriteOf(obj)
    local sp=obj and obj.getSprite and obj:getSprite()
    if sp and sp.getName then return tostring(sp:getName()) end
    return "-"
end
local function tagOf(obj)
    local md=obj and obj.getModData and obj:getModData()
    return md and md.SiegerAdminConstructionTag or nil
end
local function faceOf(obj)
    if obj and obj.getNorth then return obj:getNorth() and "N" or "W" end
    return "-"
end
local function sameSquareObject(sq,obj)
    local list=allObjects(sq)
    for i=0,list:size()-1 do if list:get(i)==obj then return true end end
    return false
end
local function inspectRemoval(a,reserved)
    local sq=square(a.x,a.y,a.z)
    local list=allObjects(sq)
    local selected=nil
    if a.verb=="remove_exact" then
        if not job.allowExisting then error("native_removal_not_authorized")end
        if a.kind~="IsoWindow" and a.kind~="IsoDoor" and a.kind~="IsoThumpable"then
            error("native_removal_class_not_approved")end
        local index=integer(a.index,0,2147483647)
        selected=index<list:size() and list:get(index) or nil
    else
        for i=0,list:size()-1 do
            local obj=list:get(i)
            if obj and tagOf(obj)==a.expected then
                if selected then error("duplicate_construction_tag")end
                selected=obj
            end
        end
    end
    if not selected or reserved[selected] then error("target_object_not_unique")end
    if not matches(selected,a.kind) then error("target_class_changed")end
    if a.kind=="IsoGenerator" then
        if a.verb=="remove_exact" then error("cannot_remove_native_generator")end
        if not selected.isActivated or selected:isActivated() then
            error("generator_must_be_off_before_removal")end
    elseif spriteOf(selected)~=a.sprite then
        error("target_sprite_changed")
    end
    if a.face~="-" and faceOf(selected)~=a.face then error("target_face_changed")end
    if a.verb=="remove_tag" and tagOf(selected)~=a.expected then
        error("target_tag_mismatch")end
    if selected.getContainerCount and selected:getContainerCount()>0 then
        error("object_contains_inventory")end
    if not sq.transmitRemoveItemFromSquare then
        error("native_object_removal_network_api_missing")end
    reserved[selected]=true
    return function()
        local now=square(a.x,a.y,a.z)
        if now~=sq or not sameSquareObject(sq,selected) then
            error("object_changed_during_construction")end
        if a.verb=="remove_tag" and tagOf(selected)~=a.expected then
            error("object_tag_changed_during_construction")end
        sq:transmitRemoveItemFromSquare(selected)
    end
end
local function checkVacant(sq,a)
    local list=allObjects(sq)
    if sq.isVehicleIntersecting and sq:isVehicleIntersecting() then
        error("vehicle_overlaps_placement")end
    if a.kind=="generator" or a.kind=="decor" or a.kind=="floor"
        or a.kind=="storage" or a.kind=="bed" then
        if sq.getMovingObjects then
            local moving=sq:getMovingObjects()
            if moving and moving.size and moving:size()>0 then
                error("occupant_overlaps_object")end
        end
    end
    if a.kind=="bed" and (not sq.getFloor or not sq:getFloor()) then
        error("bed_requires_existing_floor")end
    if a.kind=="floor" then
        if sq.getFloor and sq:getFloor() then error("floor_already_exists")end
        if a.z>0 and not square(a.x,a.y,a.z-1) then
            error("upper_floor_has_no_support")end
    end
    for i=0,list:size()-1 do
        local obj=list:get(i)
        if obj and not job.reserved[obj] then
            if a.face~="-" then
                local oriented=classOf(obj,"IsoThumpable") or
                    classOf(obj,"IsoDoor") or classOf(obj,"IsoWindow")
                if oriented and faceOf(obj)==a.face then
                    error("wall_edge_already_occupied")end
                -- Vanilla unmoving walls do not have getNorth(). Use native
                -- sprite collision flags rather than ignoring base-map walls.
                local props=obj.getProperties and obj:getProperties()
                local flag=IsoFlagType and
                    (a.face=="N" and IsoFlagType.collideN or IsoFlagType.collideW)
                if props then
                    -- Installed B42.21 exposes has(), not the old Is().
                    local test=props.has or props.Is
                    if not flag or not test then
                        error("collision_property_api_missing")end
                    if test(props,flag) then
                        error("vanilla_wall_edge_occupied")end
                end
            elseif a.kind=="generator" or a.kind=="decor" or a.kind=="storage" or a.kind=="bed" then
                if classOf(obj,"IsoGenerator") or classOf(obj,"IsoThumpable")
                    or classOf(obj,"IsoDoor") or classOf(obj,"IsoWindow") then
                    error("existing_structural_object_on_tile")end
                local sp=spriteOf(obj)
                if sp~="-" and (sp:match("^fixtures_") or
                    sp:match("^furniture_") or sp:match("^appliances_")) then
                    error("existing_furniture_on_tile")end
                if a.kind=="bed" and sp:match("^walls_") then
                    error("existing_wall_on_bed_tile")end
            end
        end
    end
end
-- Read the installed native sprite property; never alter a shared sprite.
-- B42 builds expose get(), older property tables expose Val().
local function nativeBedType(object)
    local props=object.getProperties and object:getProperties()
    local read=props and (props.get or props.Val)
    if not read then error("bed_property_api_missing")end
    return read(props,"BedType")
end
local function inspectPlace(a,reservedTargets)
    local sq=square(a.x,a.y,a.z)
    checkVacant(sq,a)
    local token=job.settlement..":"..job.stage..":"..a.id
    if a.kind=="generator" then
        if not itemName(a.sprite) or not instanceItem or
            not IsoGenerator or not IsoGenerator.new then
            error("generator_constructor_unavailable")end
        if sq.getRoom and sq:getRoom() then error("generator_must_be_outdoors")end
        local check=instanceItem(a.sprite)
        if not check or not check.setCondition or not check.getModData then
            error("generator_item_not_installed")end
        local health=integer(a.health,1,100)
        return function()
            checkVacant(square(a.x,a.y,a.z),a)
            local item=instanceItem(a.sprite)
            if not item then error("generator_item_creation_failed")end
            item:setCondition(health);item:getModData().fuel=0
            local obj=IsoGenerator.new(item,getCell(),sq)
            if not obj or not obj.getModData or not obj.transmitCompleteItemToClients then
                error("generator_constructor_failed")end
            obj:getModData().SiegerAdminConstructionTag=token
            -- Vanilla generator constructor registers its object on square.
            if not sameSquareObject(sq,obj) then
                error("generator_not_registered_on_square")end
            obj:transmitCompleteItemToClients()
        end
    end
    local spr=sprite(a.sprite)
    local bedType=nil
    if a.kind=="bed" then
        if a.face~="-" or a.alt~="-" or a.index~="-" or a.health~="-" or
            (a.expected~="native" and a.expected~="badBed" and a.expected~="averageBed" and
             a.expected~="goodBed") then error("invalid_bed_payload")end
        bedType=nativeBedType(spr)
        if (bedType~="badBed" and bedType~="averageBed" and bedType~="goodBed") or
            (a.expected~="native" and bedType~=a.expected) then
            error("sprite_is_not_requested_native_bed")end
    end
    local health=nil
    if a.health~="-" then health=integer(a.health,1,100000)end
    if a.kind=="door" and a.alt~="-" then sprite(a.alt) end
    local storageCapacity=nil
    if a.kind=="storage" then
        if a.face~="-" or a.alt~="-" or a.index~="-" or
            not IsoThumpable or not IsoThumpable.new then
            error("native_storage_constructor_unavailable")end
        storageCapacity=integer(a.expected,10,100)
    end
    if a.kind=="wall" or a.kind=="fence" or a.kind=="floor"
        or a.kind=="storage" then
        if not IsoThumpable or not IsoThumpable.new then
            error("thumpable_constructor_unavailable")end
    elseif a.kind=="door" then
        if a.alt=="-" and (not IsoDoor or not IsoDoor.new) then
            error("door_constructor_unavailable")end
        if a.alt~="-" and (not IsoThumpable or not IsoThumpable.new)then
            error("door_thumpable_constructor_unavailable")end
    elseif a.kind=="window" then
        if not IsoWindow or not IsoWindow.new then
            error("window_constructor_unavailable")end
    elseif a.kind=="decor" or a.kind=="bed" then
        if not IsoObject or not IsoObject.new then
            error("decor_constructor_unavailable")end
    else error("unsupported_place_kind")end
    if not sq.AddSpecialObject or not sq.AddTileObject then
        error("native_square_placement_api_missing")end
    return function()
        checkVacant(square(a.x,a.y,a.z),a)
        local north=a.face=="N"
        local cell=getCell()
        local obj
        if a.kind=="wall" or a.kind=="fence" or a.kind=="floor"
            or a.kind=="storage" then
            obj=IsoThumpable.new(cell,sq,a.sprite,north)
            if not obj then error("thumpable_creation_failed")end
            if health then
                if not obj.setMaxHealth or not obj.setHealth then
                    error("health_api_missing")end
                obj:setMaxHealth(health);obj:setHealth(health)
            end
            -- Sprite flags define whether a fence is hoppable.
            -- Never silently make every fence climbable.
            if a.kind=="floor" and obj.setIsFloor then obj:setIsFloor(true)end
            if a.kind=="storage" then
                -- Built-in IsoThumpable creates a real native ItemContainer.
                -- A decorated IsoObject sprite is not storage.
                if not obj.setIsContainer or not obj.getContainer then
                    error("native_storage_container_api_missing")end
                if not obj:getContainer() then obj:setIsContainer(true)end
                local c=obj:getContainer()
                if not c or not c.getType or not c.setCapacity or
                    not c.getCapacity or tostring(c:getType())~="crate" then
                    error("native_crate_container_creation_failed")end
                c:setCapacity(storageCapacity)
                if c:getCapacity()~=storageCapacity then
                    error("native_crate_capacity_not_applied")end
                if obj.setBlockAllTheSquare then
                    obj:setBlockAllTheSquare(true)end
            end
        elseif a.kind=="door" then
            if a.alt=="-" then
                obj=IsoDoor.new(cell,sq,a.sprite,north)
            else
                obj=IsoThumpable.new(cell,sq,a.sprite,a.alt,north,nil)
                if obj and obj.setIsDoor then obj:setIsDoor(true)end
            end
            if not obj then error("door_creation_failed")end
            if health and obj.setHealth then obj:setHealth(health)end
            if obj.setIsLocked then obj:setIsLocked(false)end
        elseif a.kind=="window" then
            obj=IsoWindow.new(cell,sq,spr,north)
        elseif a.kind=="decor" or a.kind=="bed" then
            -- Native overload is IsoObject(IsoCell, IsoGridSquare, IsoSprite).
            -- Passing a String to this overload fails in B42.
            obj=IsoObject.new(cell,sq,spr)
        end
        if not obj or not obj.getModData or not obj.transmitCompleteItemToClients then
            error("object_constructor_or_sync_unavailable")end
        if a.kind=="bed" and nativeBedType(obj)~=bedType then
            error("created_object_lost_native_bed_property")end
        obj:getModData().SiegerAdminConstructionTag=token
        if a.kind=="decor" or a.kind=="bed" then sq:AddTileObject(obj)
        else sq:AddSpecialObject(obj)end
        if sq.RecalcAllWithNeighbours then sq:RecalcAllWithNeighbours(true)end
        obj:transmitCompleteItemToClients()
    end
end
-- An existing vanilla window may be fortified without replacing its tile.
-- Require one exact native object and the operator's --allow-existing flag.
local function inspectBarricade(a,reserved)
    if not job.allowExisting then error("barricade_requires_allow_existing")end
    if a.kind~="IsoWindow" or a.alt~="-" or a.expected~="-" or
        (a.face~="N" and a.face~="W") then
        error("invalid_window_barricade_action")end
    local planks=integer(a.health,1,4)
    local sq=square(a.x,a.y,a.z)
    local objects=allObjects(sq)
    local index=integer(a.index,0,2147483647)
    local window=index<objects:size() and objects:get(index) or nil
    if not window or reserved[window] or not matches(window,"IsoWindow") or
        spriteOf(window)~=a.sprite or faceOf(window)~=a.face then
        error("window_selector_or_sprite_changed")end
    if not window.isBarricadeAllowed or not window:isBarricadeAllowed() or
        not window.getBarricadeOnSameSquare or
        window:getBarricadeOnSameSquare() then
        error("window_not_available_for_barricade")end
    if not IsoBarricade or not IsoBarricade.AddBarricadeToObject then
        error("native_barricade_api_unavailable")end
    reserved[window]=true
    local token=job.settlement..":"..job.stage..":"..a.id
    return function()
        if square(a.x,a.y,a.z)~=sq or not sameSquareObject(sq,window) or
            not window:isBarricadeAllowed() or
            window:getBarricadeOnSameSquare() then
            error("window_changed_during_barricade")end
        local barricade=IsoBarricade.AddBarricadeToObject(window,false)
        if not barricade or not barricade.addPlank or
            not barricade.getModData or
            not barricade.transmitCompleteItemToClients then
            error("native_barricade_creation_failed")end
        for i=1,planks do barricade:addPlank(nil,nil)end
        barricade:getModData().SiegerAdminConstructionTag=token
        barricade:transmitCompleteItemToClients()
    end
end

local function actionFields(row)
    if #row~=13 or row[1]~="a" or not word(row[2]) then error("bad_action_row")end
    local a={id=row[2],verb=row[3],kind=row[4],
        x=integer(row[5],-100000,1000000),
        y=integer(row[6],-100000,1000000),
        z=integer(row[7],-16,32),face=row[8],sprite=row[9],
        alt=row[10],health=row[11],expected=row[12],index=row[13]}
    if a.face~="N" and a.face~="W" and a.face~="-" then
        error("invalid_action_face")end
    return a
end
local function loadRequest()
    local r=getFileReader(REQ,false)
    if not r then return nil end
    local header=r:readLine()
    if not header or #header>540 then r:close();return nil end
    local h=split(header)
    if #h~=11 or h[1]~="v1" or not requestId(h[2]) or
       not word(h[3]) or not word(h[4]) or not word(h[5]) or
       not hash(h[6]) or h[11]~="end" then r:close();return nil end
    local count=integer(h[7],1,4096)
    local deps={}
    if h[8]~="-" then
        for dep in h[8]:gmatch("[^,]+") do
            if not word(dep) or dep==h[5] or deps[dep]then
                r:close();error("invalid_stage_dependency")end
            deps[dep]=true
        end
    end
    if h[9]~="0" and h[9]~="1" then r:close();error("invalid_removal_permission")end
    local expiration=integer(h[10],1,9999999999999)
    local actions={}
    local ok,why=pcall(function()
        local sawPlace=false
        for i=1,count do
            local line=r:readLine()
            if not line or #line>420 then error("invalid_construction_action_line")end
            local action=actionFields(split(line))
            if action.verb=="place" or action.verb=="barricade" then
                sawPlace=true
            elseif sawPlace then error("removal_after_placement_in_stage")end
            actions[i]=action
        end
        if r:readLine()~=nil then error("unreviewed_extra_construction_actions")end
    end)
    r:close()
    if not ok then error(why)end
    return {id=h[2],world=h[3],settlement=h[4],stage=h[5],digest=h[6],
            count=count,requires=deps,allowExisting=h[9]=="1",
            expires=expiration,actions=actions}
end
local function checkStage(j)
    currentWorld(j.world)
    local l=ledger()
    if l[j.settlement..":"..j.stage] then error("stage_already_completed")end
    for prev in pairs(j.requires) do
        if not l[j.settlement..":"..prev] then
            error("stage_prerequisite_missing:"..prev)end
    end
end
local function abort(reason)
    if not job then return end
    local j=job
    -- The FIRST native action can mutate and then fail while replicating.
    -- An ACK counter of zero must never advertise a clean preflight refusal.
    local status=(j.applied>0 or j.phase=="apply") and "partial_possible" or reason
    local ok,err=pcall(writeAck,j.id,j.world,j.settlement,j.stage,j.digest,
        "error",j.applied,j.count,status)
    if not ok then log("ERROR cannot write construction failure "..tostring(err))end
    job=nil
end
local function start(j)
    local time=getTimestampMs and getTimestampMs() or 0
    if time<j.expires-60000 or time>j.expires then
        error("construction_request_expired")end
    checkStage(j)
    if readHeader(GUARD)==j.id then error("replayed_request")end
    job=j
    job.phase="remove"
    job.index=1
    job.applied=0
    job.tasks={}
    job.reserved={}
    job.placed={}
    writeAck(j.id,j.world,j.settlement,j.stage,j.digest,"running",0,j.count,"preflight")
end
local function advance()
    if not job then return end
    local j=job
    local ok,err=pcall(function()
        local budget=MAX_PER_TICK
        while budget>0 and job do
            if j.phase=="remove" then
                if j.index>j.count then j.phase="place";j.index=1
                else
                    local a=j.actions[j.index]
                    if a.verb=="remove_tag" or a.verb=="remove_exact" then
                        j.tasks[j.index]=inspectRemoval(a,j.reserved)
                    elseif a.verb~="place" and a.verb~="barricade" then
                        error("unrecognized_construction_verb")end
                    j.index=j.index+1;budget=budget-1
                end
            elseif j.phase=="place" then
                if j.index>j.count then
                    -- A complete validation pass precedes any world mutation.
                    writeGuard(j.id,j.settlement,j.stage)
                    j.phase="apply";j.index=1
                else
                    local a=j.actions[j.index]
                    if a.verb=="place" or a.verb=="barricade" then
                        local key=table.concat({a.x,a.y,a.z,a.face},",")
                        if j.placed[key] then error("overlapping_stage_placement")end
                        j.placed[key]=true
                        if a.verb=="barricade" then
                            j.tasks[j.index]=inspectBarricade(a,j.reserved)
                        else j.tasks[j.index]=inspectPlace(a)end
                    end
                    j.index=j.index+1;budget=budget-1
                end
            elseif j.phase=="apply" then
                if j.index>j.count then
                    markStage(j)
                    writeAck(j.id,j.world,j.settlement,j.stage,j.digest,
                        "complete",j.applied,j.count,"server_applied")
                    job=nil
                else
                    currentWorld(j.world)
                    j.tasks[j.index]()
                    j.applied=j.applied+1
                    j.index=j.index+1;budget=budget-1
                end
            end
        end
        if job then
            writeAck(j.id,j.world,j.settlement,j.stage,j.digest,
                "running",j.applied,j.count,j.phase=="apply" and "applying" or "preflight")
        end
    end)
    if not ok then
        log("ERROR id="..j.id.." phase="..j.phase.." applied="..j.applied..
            "/"..j.count.." error="..tostring(err))
        abort("preflight_failed")
    end
end
local function poll()
    if not initialized then
        local r=readHeader(ACK)
        if r then
            local f=split(r)
            if f[1]=="v1" and requestId(f[2]) and #f==10 then
                processed=f[2]
                if f[7]=="running" then
                    pcall(writeAck,f[2],f[3],f[4],f[5],f[6],"error",
                        tonumber(f[8]) or 0,tonumber(f[9]) or 0,"runtime_interrupted")
                end
            end
        end
        initialized=true
    end
    if job then advance();return end
    if tickCount%POLL_TICKS~=0 then return end
    local ok,new=pcall(loadRequest)
    if not ok then log("ERROR construction request parse "..tostring(new));return end
    if not new or new.id==processed then return end
    processed=new.id
    local fine,why=pcall(start,new)
    if not fine then
        log("ERROR refusing construction "..tostring(why))
        pcall(writeAck,new.id,new.world,new.settlement,new.stage,new.digest,
            "error",0,new.count,"preflight_failed")
        job=nil
        return
    end
    advance()
end
if Events and Events.OnTickEvenPaused then
    Events.OnTickEvenPaused.Add(function()
        tickCount=tickCount+1
        local ok,err=pcall(poll)
        if not ok then
            log("ERROR construction dispatch "..tostring(err))
            abort("runtime_error")
        end
    end)
else log("ERROR OnTickEvenPaused missing, construction disabled")end
