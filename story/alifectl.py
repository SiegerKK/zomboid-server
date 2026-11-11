#!/usr/bin/env python3
"""Install the reviewed A-Life profile into stopped story_test with a cold backup."""
import argparse,datetime,json,shutil,subprocess
from pathlib import Path
import scanctl,livectl,workshopctl,adminmode

def run(a):
 if a.world!='story_test'or not a.yes:raise ValueError('Explicit story_test --yes required')
 slot=scanctl.slot(a.world)
 if scanctl.active_world()!=a.world:raise ValueError('Wrong active world')
 if not adminmode.disabled(a.world):raise ValueError('This install preserves the reviewed Admin OFF configuration')
 info=json.loads(subprocess.run(['docker','inspect','zomboid-server'],capture_output=True,text=True,check=True,timeout=15).stdout)[0]
 if info['State']['Running']:raise ValueError('Stop game before changing profiles')
 mounts={m['Destination']:Path(m['Source']).resolve()for m in info['Mounts']}
 if mounts.get('/root/Zomboid')!=(slot/'data').resolve():raise ValueError('Wrong save mount')
 finished=datetime.datetime.fromisoformat(info['State']['FinishedAt'].replace('Z','+00:00')).timestamp()
 backups=list((scanctl.STORE/'backups/worlds'/a.world).glob('world-*.tar.gz'))
 if not backups:raise ValueError('Fresh cold backup required')
 backup=max(backups,key=lambda p:p.stat().st_mtime)
 if backup.is_symlink()or backup.stat().st_mtime<finished or datetime.datetime.now(datetime.timezone.utc).timestamp()-backup.stat().st_mtime>1800:raise ValueError('Fresh cold backup after stop required')
 livectl.checksum_backup(a.world,backup)
 profile,mods=slot/'profile',slot/'mods.env'
 if profile.is_symlink()or mods.is_symlink():raise ValueError('Unsafe profile metadata')
 old_name=profile.read_text().strip()
 if old_name not in ('mp-test','alife'):raise ValueError('Unexpected previous profile; manual review required')
 expected=scanctl.REPO/('config/mods.mp-test.env'if old_name=='mp-test'else'config/mods.alife.env')
 reviewed=expected.read_text()
 legacy=reviewed.replace(';3806944055','').replace(';ProjectALifeJimmy','')
 if mods.read_text() not in (reviewed,legacy):raise ValueError('Existing profile differs from reviewed source')
 target=scanctl.REPO/'config/mods.alife.env'
 text=target.read_text()
 lines=dict(line.split('=',1)for line in text.splitlines()if line and not line.startswith('#'))
 ids=lines.get('WORKSHOP_ITEMS','').split(';');names=lines.get('MODS','').split(';')
 if '3803984183'not in ids or 'ProjectALifeNPCs'not in names:raise ValueError('A-Life identity missing')
 if set(ids)&{'3776274080','3781448194','3776164832','3268487204','3469292499'}or set(names)&{'ZomboidForge','TLOU_Infected_MP','TLOU_Infected_42_20','Bandits2','BanditsCreator'}:raise ValueError('Conflicting zombie/NPC processors in A-Life profile')
 # Retain configuration history. Never copy/restore/delete the game save here.
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 history=slot/'profile-history'/('alife-'+stamp);history.mkdir(parents=True,mode=0o700)
 radio=slot/'story/radio.enabled'
 if radio.is_symlink():raise ValueError('Unsafe radio marker')
 originals={p:p.read_bytes()if p.exists()else None for p in (profile,mods,slot/'deployment.txt',slot/'workshop-snapshot',radio)}
 for p,data in originals.items():
  if data is not None:(history/p.name).write_bytes(data)
 try:
  scanctl.atomic_request(mods,text)
  scanctl.atomic_request(profile,'alife\n')
  revision=scanctl.REPO/'DEPLOYED_COMMIT'
  commit=revision.read_text().strip()if revision.is_file()else'unrecorded-local-test'
  scanctl.atomic_request(slot/'deployment.txt','profile=alife\ncommit='+commit+'\nPZ_IMAGE='+workshopctl.IMAGE+'\n')
  if radio.exists():radio.unlink()
  workshopctl.run(argparse.Namespace(world=a.world,yes=True))
  marker=(slot/'workshop-snapshot').read_text().strip()
  root=scanctl.STORE/'mod-snapshots'/marker/'workshop/content/108600'
  metadata=[]
  for p in root.rglob('mod.info'):
   fields=dict(line.split('=',1)for line in p.read_text(errors='replace').splitlines()if '='in line)
   if fields.get('id') in ('ProjectALifeNPCs','ProjectALifeJimmy'):metadata.append(fields)
  required={'ProjectALifeNPCs','ProjectALifeJimmy'} & set(names)
  if not required.issubset({m.get('id') for m in metadata}):raise ValueError('Downloaded A-Life or Jeem Mod ID missing')
  for fields in metadata:
   dependencies=fields.get('require','').replace('\\','').replace(',', ';').split(';')
   if set(filter(None,dependencies))-set(names):raise ValueError('New A-Life dependency requires review')
   if fields.get('javaJarFile'):raise ValueError('Unexpected new Java component requires review')
  (history/'installed.json').write_text(json.dumps({'profile':'alife','radio_enabled':False,'snapshot':marker,'mod_metadata':metadata,'backup':backup.name},indent=2)+'\n')
 except Exception:
  # Repair only the small configuration transaction; never restore world data.
  for p,data in originals.items():
   if data is None:
    if p.exists():p.unlink()
   else:scanctl.atomic_request(p,data.decode())
  raise
 print('A-Life profile and new snapshot selected; TLOU/Forge/Radio disabled. All previous saves/snapshots retained. Start story_test.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('world');p.add_argument('--yes',action='store_true');a=p.parse_args()
 try:run(a)
 except(ValueError,OSError,subprocess.SubprocessError)as e:p.exit(2,'A-Life install: '+str(e)+'\n')
