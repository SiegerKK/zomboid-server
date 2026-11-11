#!/usr/bin/env python3
"""Owner-approved new Walking Dead slot; never restore/delete an existing world."""
import argparse, datetime, json, subprocess
from pathlib import Path
import scanctl, livectl, workshopctl

def preflight():
    if scanctl.active_world() != 'story_test':
        raise ValueError('Expected preserved story_test as the previous active world')
    info=json.loads(subprocess.run(['docker','inspect','zomboid-server'],capture_output=True,text=True,check=True,timeout=15).stdout)[0]
    if info['State']['Running']:raise ValueError('Stop game before creation')
    mounts={m['Destination']:Path(m['Source']).resolve()for m in info['Mounts']}
    if mounts.get('/root/Zomboid')!=(scanctl.slot('story_test')/'data').resolve():raise ValueError('Unexpected previous world mount')
    ended=datetime.datetime.fromisoformat(info['State']['FinishedAt'].replace('Z','+00:00')).timestamp()
    backups=list((scanctl.STORE/'backups/worlds/story_test').glob('world-*.tar.gz'))
    if not backups:raise ValueError('Cold backup required')
    backup=max(backups,key=lambda p:p.stat().st_mtime)
    if backup.is_symlink() or backup.stat().st_mtime<ended or datetime.datetime.now(datetime.timezone.utc).timestamp()-backup.stat().st_mtime>1800:raise ValueError('Fresh cold backup after clean stop required')
    livectl.checksum_backup('story_test',backup)
    print('Verified preserved story_test backup: '+backup.name)

SPAWNS = r'''
from pathlib import Path
import json,hashlib
maps=Path('/pzomboid-server/media/maps')
if not (maps/'Muldraugh, KY/spawnpoints.lua').is_file():raise SystemExit('Pinned vanilla map missing')
root=Path('/workshop/content/108600/3785397275')
files=list(root.rglob('ExtractionMap/spawnpoints.lua'))
if len(files)!=1:raise SystemExit('Expected exactly one ExtractionMap spawn file')
p=files[0]
if not (p.parent/'map.info').is_file() or not p.read_text().strip():raise SystemExit('Incomplete Extraction map')
rows=[{'name':'Hideout','file':'media/maps/ExtractionMap/spawnpoints.lua','sha256':hashlib.sha256(p.read_bytes()).hexdigest()}]
out=Path('/world-server/SiegerZomboid_spawnregions.lua')
if out.exists():raise SystemExit('Existing spawn region file: refusing overwrite')
text='function SpawnRegions()\n    return {\n'+''.join('        { name = '+json.dumps(r['name'])+', file = '+json.dumps(r['file'])+' },\n'for r in rows)+'    }\nend\n'
out.write_text(text)
Path('/world-server/WalkingDead_spawn_audit.json').write_text(json.dumps(rows,indent=2)+'\n')
ini=Path('/world-server/SiegerZomboid.ini')
if ini.exists():raise SystemExit('Refusing overwrite of existing INI')
ini.write_text('Map=ExtractionMap;Muldraugh, KY\nDoLuaChecksum=true\n')
print('Verified ExtractionMap, vanilla base map, and Hideout spawn')
'''

def prepare():
    preflight()
    slot=scanctl.slot('walking_dead')
    if (slot/'profile').read_text().strip()!='walkingdead':raise ValueError('Wrong destination profile')
    if (slot/'workshop-snapshot').exists():raise ValueError('Already prepared; review before retry')
    for name in ('Saves','db'):
        if (slot/'data'/name).exists():raise ValueError('Existing game data; refusing preparation')
    workshopctl.run(argparse.Namespace(world='walking_dead',yes=True))
    snapshot=scanctl.STORE/'mod-snapshots'/(slot/'workshop-snapshot').read_text().strip()/'workshop'
    mod=snapshot/'content/108600/3810674933'
    infos=[p.read_text(errors='replace') for p in mod.rglob('mod.info')]
    if not any('\nid=TacticalGridInventory\n' in '\n'+s for s in infos):raise ValueError('TGI identity missing')
    em=snapshot/'content/108600/3785397275'
    if not any('\nid=ExtractionMode\n' in '\n'+p.read_text(errors='replace') for p in em.rglob('mod.info')):raise ValueError('ExtractionMode identity missing')
    if (slot/'story/bundle.lua').exists():raise ValueError('New world must not load old story scenes')
    server=slot/'data/Server'
    subprocess.run(['docker','run','--rm','--read-only','--network','none','--memory','512m','--pids-limit','64','--mount','type=bind,src='+str(server)+',dst=/world-server','--mount','type=bind,src='+str(snapshot)+',dst=/workshop,readonly','--entrypoint','python3',workshopctl.IMAGE,'-c',SPAWNS],check=True,timeout=90)
    commit=(scanctl.REPO/'DEPLOYED_COMMIT').read_text().strip()
    scanctl.atomic_request(slot/'deployment.txt','profile=walkingdead\ncommit='+commit+'\nPZ_IMAGE='+workshopctl.IMAGE+'\n')
    print('Prepared walking_dead. No existing saves changed. Start explicitly with pz start walking_dead.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['preflight','prepare']);a=p.parse_args()
    try:globals()[a.action]()
    except(ValueError,OSError,subprocess.SubprocessError)as e:p.exit(2,'Walking Dead: '+str(e)+'\n')
