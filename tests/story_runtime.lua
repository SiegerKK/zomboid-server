-- Isolated Lua 5.1 behavioral tests; stubs do not prove game/network sync.
local runtime=arg[1] or 'story/runtime/SiegerStoryDirector.lua'
local function list(values)
    return {size=function() return #values end, get=function(_,i) return values[i+1] end}
end
local load, started, ticks
Events={LoadGridsquare={Add=function(f) load=f end},
    OnServerStarted={Add=function(f) started=f end}, OnTick={Add=function(f) ticks=f end}}
isClient=function() return false end
local sent=0
sendAddItemToContainer=function() sent=sent+1 end
instanceof=function(o,c) return o.class==c end
local made={}
instanceItem=function(t)
    local md,pages={},{}
    local item={kind=t,pages=pages,writable=false,numPages=0}
    function item:getModData() return md end
    function item:setName(v) self.name=v end
    function item:getName() return self.name or self.kind end
    function item:getFullType() return self.kind end
    function item:setCanBeWrite(v) self.writable=v end
    function item:setNumberOfPages(v) self.numPages=v end
    function item:addPage(i,v) pages[i]=v end
    function item:canBeWrite() return self.writable end
    function item:getNumberOfPages() return self.numPages end
    function item:seePage(i) return pages[i] end
    table.insert(made,item)
    return item
end
local ground,inventory,md={},{},{}
local container={getItems=function() return list(inventory) end,getType=function() return 'medicine' end,
    AddItem=function(_,item) table.insert(inventory,item);return item end}
local obj={class='IsoObject',getSprite=function() return {getName=function() return 'verified_cabinet' end} end,
    getContainer=function() return container end}
local square={getX=function() return 1 end,getY=function() return 2 end,getZ=function() return 0 end,
    getModData=function() return md end,transmitModdata=function() end,
    getObjects=function() return list({obj}) end,getWorldObjects=function() return list(ground) end,
    getRoom=function() return nil end,
    AddWorldInventoryItem=function(_,item) table.insert(ground,{getItem=function() return item end});return item end}
local note={id='note_one',type='note',at={x=1,y=2,z=0},placement='ground',
    title='Последняя смена',pages={'Первая страница','Вторая страница'}}
local loot={id='supplies',type='loot',at={x=1,y=2,z=0},placement='container',
    selector={object_index=0,class='IsoObject',sprite='verified_cabinet'},
    items={{type='Base.Bandage',count=2}}}
SiegerStoryScenes={schema=1,world='story_test',scenes={{id='test_clinic',actions={note,loot}}},inspect={}}
dofile(runtime);started();load(square)
assert(#ground==1 and #inventory==2 and sent==2)
local placed=ground[1]:getItem()
assert(placed.writable and placed.numPages==2 and placed.pages[2]=='Вторая страница')
load(square);assert(#ground==1 and #inventory==2,'duplicate on repeated square load')
-- Simulated Lua reload with persisted square/item modData.
dofile(runtime);started();load(square)
assert(#ground==1 and #inventory==2,'duplicate after runtime reload')
-- A partial completion (item exists but square flag missing) must not duplicate.
md['SiegerStory:test_clinic:supplies']=nil
load(square);assert(#inventory==2,'duplicate after interrupted action')
-- Invalid selector must not mark success or mutate container.
local bad={id='bad_container',type='loot',at={x=1,y=2,z=0},placement='container',
    selector={object_index=0,class='IsoObject',sprite='wrong_sprite'},items={{type='Base.Bandage',count=1}}}
SiegerStoryScenes={schema=1,world='story_test',scenes={{id='test_clinic',actions={bad}}},inspect={}}
dofile(runtime);started();load(square)
assert(#inventory==2 and md['SiegerStory:test_clinic:bad_container']==nil)
-- Missing networking API must fail BEFORE adding inventory.
bad.selector.sprite='verified_cabinet'
sendAddItemToContainer=nil
dofile(runtime);started();load(square)
assert(#inventory==2 and md['SiegerStory:test_clinic:bad_container']==nil)
print('PASS: Lua runtime note readability, item tokens, repeated load, reload and fail-before-mutation')
