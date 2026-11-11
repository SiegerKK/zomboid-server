#!/usr/bin/env python3
"""Read-only engine/mount/mod metadata. Never print container env or secrets."""
import json,re,subprocess
from pathlib import Path
import scanctl

def run(world):
 if scanctl.active_world()!=world:raise ValueError('Requested world is not active')
 cp=subprocess.run(['docker','inspect','zomboid-server'],capture_output=True,text=True,check=True,timeout=15)
 info=json.loads(cp.stdout)[0]
 mounts={m['Destination']:Path(m['Source'])for m in info['Mounts']}
 if mounts.get('/root/Zomboid')!=(scanctl.slot(world)/'data').resolve():raise ValueError('Wrong world mount')
 image=json.loads(subprocess.run(['docker','image','inspect',info['Image']],capture_output=True,text=True,check=True,timeout=15).stdout)[0]
 labels=image.get('Config',{}).get('Labels')or{}
 out={'world':world,'image':info['Config']['Image'],'game_labels':{k:v for k,v in labels.items()if k.startswith('com.projectzomboid.')},'running':info['State']['Running']}
 ini=scanctl.slot(world)/'data/Server/SiegerZomboid.ini'
 if ini.is_symlink()or not ini.is_file()or ini.stat().st_size>1024*1024:raise ValueError('Unsafe/missing game configuration')
 lines=ini.read_text().splitlines();allowed={}
 for line in lines:
  if '='in line:
   k,v=line.split('=',1)
   if k in ('Mods','WorkshopItems','DoLuaChecksum','Map','SleepAllowed','SleepNeeded','PVP','PauseEmpty','MaxPlayers','PingLimit','Public','Open'):allowed[k]=v
 out['config']=allowed
 if world=='walking_dead':
  path=scanctl.slot(world)/'data/Server/SiegerZomboid_SandboxVars.lua'
  if path.is_symlink()or not path.is_file()or path.stat().st_size>1024*1024:raise ValueError('Unsafe Sandbox file')
  source=path.read_text()
  selected={}
  groups={'':('StartMonth','StartDay','StartTime','TimeSinceApo','DayLength','AmmoLootNew'), 'ZombieLore':('Speed','SprinterPercentage','Transmission'), 'ZombieConfig':('PopulationMultiplier','PopulationStartMultiplier','PopulationPeakMultiplier','RespawnHours'), 'ALife':('Drops_WeaponCondition',), 'ExtractionMode':('GameMode','RaidMode','NPCProvider','HordeSize','AmbientSprinterPercentWeek2','HordeSprinterPercent')}
  for group,keys in groups.items():
   block=source
   if group:
    match=re.search(r'^\s*'+group+r'\s*=\s*\{(.*?)^\s*\}',source,re.S|re.M)
    if not match:raise ValueError('Missing Sandbox block '+group)
    block=match.group(1)
   for key in keys:
    match=re.search(r'^\s*'+key+r'\s*=\s*([0-9.]+|true|false)\s*,',block,re.M)
    if not match:raise ValueError('Missing Sandbox option '+group+'.'+key)
    selected[(group+'.'if group else '')+key]=match.group(1)
  out['sandbox_file_values']=selected
  regions=scanctl.slot(world)/'data/Server/SiegerZomboid_spawnregions.lua'
  if regions.is_symlink()or not regions.is_file()or regions.stat().st_size>65536:raise ValueError('Unsafe spawnregions')
  out['spawn_regions_file']=regions.read_text()
 snapshot=mounts.get('/root/.local/share/Steam/steamapps/workshop')
 out['workshop_snapshot']=str(snapshot)if snapshot else None
 out['workshop_metadata']=[]
 for wid in allowed.get('WorkshopItems','').split(';'):
  if not re.fullmatch('[0-9]{5,12}',wid):continue
  root=snapshot/'content/108600'/wid if snapshot else None
  rows=[]
  if root and root.is_dir()and not root.is_symlink():
   for n,path in enumerate(root.rglob('mod.info')):
    if n>=200:raise ValueError('Workshop metadata budget exceeded')
    if path.is_symlink()or path.stat().st_size>65536:continue
    fields={}
    for line in path.read_text(errors='replace').splitlines():
     if '='in line:
      k,v=line.split('=',1)
      if k.lower()in('id','name','require','version','versionmin','versionmax'):fields[k]=v[:500]
    rows.append({'path':str(path.relative_to(root)),'fields':fields})
  out['workshop_metadata'].append({'id':wid,'installed':bool(root and root.is_dir()),'mods':rows})
 print(json.dumps(out,indent=2,ensure_ascii=False))
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('world');a=p.parse_args()
 try:run(a.world)
 except(ValueError,OSError,subprocess.SubprocessError)as e:p.exit(2,'Engine info: '+str(e)+'\n')
