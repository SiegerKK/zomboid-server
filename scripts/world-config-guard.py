#!/usr/bin/env python3
"""Fixed pre-JVM guard; no player data, secrets or arbitrary configuration input."""
import os,re
from pathlib import Path

def configure(server,maps):
    points=sorted(maps.glob('*/spawnpoints.lua'))
    expected={'Muldraugh, KY','West Point, KY','Riverside, KY','Rosewood, KY','March Ridge, KY','Echo Creek, KY','Fallas Lake, KY','Ekron, KY','Irvington, KY','Brandenburg, KY','Valley Station, KY'}
    if {p.parent.name for p in points}!=expected:raise ValueError('Pinned-image spawn cities differ')
    for p in points:
        if p.is_symlink()or not p.read_text().strip():raise ValueError('Unsafe spawnpoints')
    ini=server/'SiegerZomboid.ini'
    if ini.is_symlink()or not ini.is_file()or ini.stat().st_size>1024*1024:raise ValueError('Unsafe INI')
    text,n=re.subn(r'(?m)^Map=.*$','Map=Muldraugh, KY',ini.read_text())
    if n!=1:raise ValueError('Expected one Map setting')
    regions=server/'SiegerZomboid_spawnregions.lua'
    if regions.is_symlink():raise ValueError('Unsafe spawnregions')
    import json
    rows=[{'name':p.parent.name,'file':'media/maps/'+p.parent.name+'/spawnpoints.lua'}for p in points]
    regions.write_text('function SpawnRegions()\n return {\n'+''.join('  { name = '+json.dumps(r['name'])+', file = '+json.dumps(r['file'])+' },\n'for r in rows)+' }\nend\n')
    ini.write_text(text)
    print('SIEGER_WORLD_CONFIG ordinary survival; 11 verified spawn cities; Extraction inactive')

if __name__=='__main__':
    if os.environ.get('PZ_SERVER_TOOLS_WORLD')=='walking_dead'and'ExtractionMode'not in os.environ.get('MODS','').split(';'):
        configure(Path('/root/Zomboid/Server'),Path('/pzomboid-server/media/maps'))
