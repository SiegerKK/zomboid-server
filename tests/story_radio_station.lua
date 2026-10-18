-- Lua 5.1 unit test for real-time server station random rotation.
-- Replace the owner playlist with three deterministic fixture tracks.
local runtime=arg[1] or "mods/SiegerRadio/42/media/lua/server/SiegerRadioStation.lua"
local f=assert(io.open(runtime,"rb"));local source=f:read("*a");f:close()
local version=assert(source:match('local VERSION%s*=%s*"([^\"]+)"'))
source=source:gsub("(    %-%- BEGIN RADIO PLAYLIST\n).-([ ]*%-%- END RADIO PLAYLIST)",
 [[%1    {id="song_one",duration=5000},
    {id="song_two",duration=6500},
    {id="song_three",duration=7500},
%2]])
local compile=assert(loadstring(source, "SiegerRadioStation test"))
local event,files={},{}
Events={OnTick={Add=function(fn)event.tick=fn end},
 OnClientCommand={Add=function(fn)event.hello=fn end}}
isClient=function()return false end
SiegerStoryScenes={world="story_test",schema=1}
local ms=100000
getTimestampMs=function()return ms end
local rand=0
ZombRand=function(max)rand=(rand+1)%max;return rand end
local commands={}
sendServerCommand=function(...)
 commands[#commands+1]={...}
end
getFileReader=function(path)
 if not files[path]then return nil end
 local rows={}
 for line in files[path]:gmatch("[^\n]+")do rows[#rows+1]=line end
 local i=0
 return {readLine=function()i=i+1;return rows[i]end,close=function()end}
end
getFileWriter=function(path,make,append)
 if not append then files[path]="" end
 return {write=function(_,s)files[path]=(files[path]or"")..s end,close=function()end}
end
local function advance(delta)
 ms=ms+delta
 event.tick()
end
local function req(id,mode)
 files["SiegerRadioStationRequest.txt"]=table.concat({
 "v1",string.rep(id,32),"story_test",mode,version},"\t").."\n"
 advance(500)
 return files["SiegerRadioStationResult.txt"]
end
compile()
local accepted=req("a","start")
assert(accepted:find("\tstart\tcomplete\ton",1,true))
assert(files["SiegerRadioStationState.txt"]=="v1\ton\n")
local function starts()
 local tracks={}
 for _,row in ipairs(commands)do
  if row[1]=="SiegerRadio" and row[2]=="STATION_TRACK" then
   tracks[#tracks+1]=row[3].clip
   assert(#row[3].requestId==32)
  end
 end
 return tracks
end
for i=1,5 do advance(10000)end
local tracks=starts()
assert(#tracks>=4,"Random station did not automatically advance tracks")
local firstCycle={};for i=1,3 do firstCycle[tracks[i]]=true end
assert(firstCycle.song_one and firstCycle.song_two and firstCycle.song_three,
       "Each song must appear once before the bag repeats")
for i=2,#tracks do assert(tracks[i]~=tracks[i-1],"No immediate replay across shuffle cycles")end
local player={name="listener"}
event.hello("SiegerRadio","HELLO",player,{version=version})
assert(commands[#commands][1]==player and commands[#commands][2]=="SiegerRadio"
   and commands[#commands][3]=="STATION_TRACK","Late listener should learn current track")
local stopped=req("b","stop")
assert(stopped:find("\tstop\tcomplete\toff",1,true))
assert(files["SiegerRadioStationState.txt"]=="v1\toff\n")
assert(commands[#commands][2]=="STATION_STOP")
local before=#commands
for i=1,5 do advance(9000)end
assert(#commands==before,"No track changes after station stopped")
-- A restart with the same request must not re-open the station.
compile()
advance(500)
assert(files["SiegerRadioStationState.txt"]=="v1\toff\n")
assert(#commands==before)
print("PASS: random shuffled rotation, auto-next, late listener and stop across reload")
