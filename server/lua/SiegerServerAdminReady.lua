-- Installed after every handler, before the engine's real OnServerStarted event.
local config=SiegerServerAdminBootstrap
assert(config and config.world=='story_test' and type(config.boot)=='string', 'missing admin metadata')
assert(SiegerServerLoadedModules and SiegerStoryScenes and SiegerStoryScenes.world==config.world, 'wrong/missing world bundle')
Events.OnServerStarted.Add(function()
    local w=getFileWriter('SiegerServerAdminReady.txt',true,false)
    assert(w,'admin ready writer unavailable')
    w:write('v1\t'..config.world..'\t'..config.boot..'\tadmin-v1\n');w:close()
    print('SIEGER_SERVER_ADMIN ready world='..config.world)
end)
SiegerServerAdminRevision='admin-v1'
SiegerServerAdminBootstrap=nil
