#!/usr/bin/env python3
"""Explicit stopped-world Workshop refresh into a NEW retained snapshot."""
import argparse,datetime,json,os,re,subprocess,tempfile,zipfile
from pathlib import Path
import scanctl
IMAGE='ghcr.io/meshi-team/project-zomboid-server@sha256:cec925cd86a7d1d5e020c0c94a30abbf59fd7bc94707fc5649e786d48306898a'
def run(a):
 if a.world!='story_test' or not a.yes:raise ValueError('Only explicit story_test --yes is approved')
 slot=scanctl.slot(a.world)
 state=subprocess.run(['docker','inspect','-f','{{.State.Running}}','zomboid-server'],capture_output=True,text=True,check=True,timeout=15).stdout.strip()
 if state!='false':raise ValueError('Stop game before refreshing the snapshot')
 mods=slot/'mods.env'
 if mods.is_symlink():raise ValueError('Unsafe mods config')
 line=next((l.split('=',1)[1]for l in mods.read_text().splitlines()if l.startswith('WORKSHOP_ITEMS=')),None)
 if not line or not re.fullmatch('[0-9;]+',line):raise ValueError('Invalid Workshop ID set')
 ids=line.split(';')
 if not 1<=len(ids)<=20 or len(set(ids))!=len(ids)or any(not re.fullmatch('[0-9]{5,12}',i)for i in ids):raise ValueError('Invalid ID budget')
 # Neither pull nor downloader sees the game's environment, secrets or save.
 subprocess.run(['docker','pull',IMAGE],check=True)
 root=scanctl.STORE/'mod-snapshots';root.mkdir(mode=0o700,exist_ok=True)
 if root.is_symlink():raise ValueError('Snapshot root must not be a symlink')
 name='workshop-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 target=root/name;target.mkdir(mode=0o700)
 cache=target/'workshop';cache.mkdir(mode=0o700)
 request=target/'request.json';request.write_text(json.dumps(ids));request.chmod(0o600)
 script=scanctl.REPO/'scripts/workshop_download_stage.py'
 subprocess.run(['docker','run','--rm','--name','pz-workshop-maintenance','--memory','2g','--pids-limit','256',
  '--mount','type=bind,src='+str(cache)+',dst=/root/.local/share/Steam/steamapps/workshop',
  '--mount','type=bind,src='+str(request)+',dst=/bootstrap/workshop-request.json,readonly',
  '--mount','type=bind,src='+str(script)+',dst=/bootstrap/workshop_download_stage.py,readonly',
  '--entrypoint','python3',IMAGE,'/bootstrap/workshop_download_stage.py'],check=True)
 for wid in ids:
  path=cache/'content/108600'/wid
  if path.is_symlink()or not path.is_dir()or not any(path.rglob('mod.info')):raise ValueError('Downloaded item missing metadata: '+wid)
  if any(p.is_symlink()for p in path.rglob('*')):raise ValueError('Symlink in Workshop payload: '+wid)
 agent=cache/'content/108600/3619862853/mods/ZombieBuddy/libs/ZombieBuddy.jar'
 with zipfile.ZipFile(agent)as z:
  if 'me/zed_0xff/zombie_buddy/Callbacks.class'not in z.namelist():raise ValueError('ZombieBuddy callback missing')
  if 'Premain-Class: me.zed_0xff.zombie_buddy.Agent'not in z.read('META-INF/MANIFEST.MF').decode():raise ValueError('Unexpected agent metadata')
 # Metadata needed for root audit; no raw gameplay or secret data.
 (target/'verified.json').write_text(json.dumps({'ids':ids,'image':IMAGE,'world':a.world},indent=2)+'\n')
 scanctl.atomic_request(slot/'workshop-snapshot',name+'\n')
 print('Selected new Workshop snapshot '+name+'; all previous snapshots retained. Game remains stopped.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('world');p.add_argument('--yes',action='store_true');a=p.parse_args()
 try:run(a)
 except(ValueError,OSError,subprocess.SubprocessError)as e:p.exit(2,'Workshop refresh: '+str(e)+'\n')
