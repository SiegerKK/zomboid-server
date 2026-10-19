#!/usr/bin/env python3
"""Public SiegerAdmin Lua mirrors; independent of radio catalogs and music."""
from pathlib import Path
import argparse
ROOT=Path(__file__).resolve().parents[1]
MODULES=('SiegerStoryDirector','SiegerStoryAreaScan','SiegerStoryPlayerControl',
         'SiegerStoryBarControl','SiegerStoryVehicleControl','SiegerStoryBatch',
         'SiegerStoryCharacter','SiegerStoryOps','SiegerStoryTLOUDiagnostics',
         'ZZ_SiegerStoryScenes','SiegerAdminClock')
def render():
    folder=ROOT/'mods/SiegerAdmin/42/media/lua/server'
    result={folder/(name+'.lua'):(ROOT/'story/runtime'/(name+'.lua')).read_text() for name in MODULES}
    result[folder/'SiegerRuntimeAudit.lua']='if isClient and isClient() then return end\n'+(ROOT/'scripts/runtime-tlou-audit.lua').read_text()
    return result

def check():
    for path,body in render().items():
        if path.read_text()!=body:raise ValueError('Out-of-sync admin mirror: '+str(path))
    radio=ROOT/'mods/SiegerRadio/42/media/lua'
    expected={'client/SiegerRadioClient.lua','server/SiegerRadioStation.lua','server/SiegerStoryRadio.lua'}
    actual={p.relative_to(radio).as_posix() for p in radio.rglob('*.lua')}
    if actual!=expected:raise ValueError('Radio contains non-radio Lua or is missing radio code')
    print('PASS: independent SiegerAdmin mirrors; radio contains only radio Lua')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('check','render'));args=parser.parse_args()
    if args.command=='render':
        for path,body in render().items():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body)
    else:check()
