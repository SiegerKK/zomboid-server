#!/usr/bin/env python3
"""Public SiegerAdmin Lua mirrors; independent of radio catalogs and music."""
from pathlib import Path
import argparse
ROOT=Path(__file__).resolve().parents[1]
MODULES=('SiegerStoryDirector','SiegerStoryAreaScan','SiegerStoryPlayerControl',
         'SiegerStoryBarControl','SiegerStoryVehicleControl','SiegerStoryBatch',
         'SiegerStoryCharacter','SiegerStoryOps','SiegerStoryTLOUDiagnostics',
         'ZZ_SiegerStoryScenes','SiegerAdminClock','SiegerAdminZombieDebug',
         'SiegerAdminBuildingAtlas')
def render():
    folder=ROOT/'mods/SiegerAdmin/42/media/lua/server'
    result={folder/(name+'.lua'):(ROOT/'story/runtime'/(name+'.lua')).read_text() for name in MODULES}
    result[folder/'SiegerRuntimeAudit.lua']='if isClient and isClient() then return end\n'+(ROOT/'scripts/runtime-tlou-audit.lua').read_text()
    return result

# Public package files are an explicit interface. Unknown Lua placed in a
# deploy/ZIP directory must never be silently loaded by game clients/server.
AUTHORED=(
    'mod.info','42/mod.info',
    '42/media/lua/client/SiegerStoryCharacterClient.lua',
    '42/media/lua/shared/SiegerCharacterProfiles.lua',
    '42/media/lua/shared/SiegerInventoryIdentity.lua',
)
def approved_paths():
    base=ROOT/'mods/SiegerAdmin'
    return set(AUTHORED)|{p.relative_to(base).as_posix() for p in render()}

def verify_layout(base, approved):
    found=set()
    for path in base.rglob('*'):
        if path.is_symlink():raise ValueError('Symlink in admin mod: '+str(path))
        if path.is_file():found.add(path.relative_to(base).as_posix())
    if found!=approved:
        extras=sorted(found-approved)
        missing=sorted(approved-found)
        raise ValueError('Unapproved or missing SiegerAdmin files: extras='+
                         repr(extras)+' missing='+repr(missing))

def verify_radio_layout(radio):
    expected={'client/SiegerRadioClient.lua','server/SiegerRadioStation.lua',
              'server/SiegerStoryRadio.lua'}
    found=set()
    for path in radio.rglob('*.lua'):
        if path.is_symlink():
            raise ValueError('Symlinked radio Lua not allowed: '+str(path))
        if path.is_file():found.add(path.relative_to(radio).as_posix())
    if found!=expected:
        raise ValueError('Radio contains stale, unexpected or missing Lua: extras='+
                         repr(sorted(found-expected))+' missing='+repr(sorted(expected-found)))

def check():
    for path,body in render().items():
        if path.read_text()!=body:raise ValueError('Out-of-sync admin mirror: '+str(path))
    verify_layout(ROOT/'mods/SiegerAdmin',approved_paths())
    verify_radio_layout(ROOT/'mods/SiegerRadio/42/media/lua')
    print('PASS: independent SiegerAdmin mirrors; radio contains only radio Lua')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('check','render'));args=parser.parse_args()
    if args.command=='render':
        for path,body in render().items():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body)
    else:check()
