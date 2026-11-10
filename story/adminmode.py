#!/usr/bin/env python3
"""Reversible stopped-world switch, independent of the deferred admin migration."""
import argparse,datetime,json,subprocess
from pathlib import Path
import scanctl,livectl
MARKER='sieger-admin.disabled'
def disabled(world,base=None):return scanctl.admin_disabled(world,base)
def run(a):
 if a.world!='story_test':raise ValueError('Experiment approved only for story_test')
 old=disabled(a.world)
 if a.mode=='status':print('SiegerAdmin selected: '+('OFF'if old else'ON'));return
 if not a.yes:raise ValueError('Explicit --yes required')
 if old==(a.mode=='off'):print('Already selected '+a.mode);return
 if scanctl.active_world()!=a.world:raise ValueError('Wrong active world')
 bundle=scanctl.slot(a.world)/'story/bundle.lua'
 if bundle.is_symlink()or not bundle.is_file():raise ValueError('Reviewed world bundle required')
 cp=subprocess.run(['docker','inspect','zomboid-server'],capture_output=True,text=True,check=True,timeout=15)
 info=json.loads(cp.stdout)[0]
 if info['State']['Running']:raise ValueError('Stop game in an authorized maintenance window first')
 mounted={m['Destination']:Path(m['Source']).resolve()for m in info['Mounts']}
 if mounted.get('/root/Zomboid')!=(scanctl.slot(a.world)/'data').resolve():raise ValueError('Wrong world data mount')
 stopped=datetime.datetime.fromisoformat(info['State']['FinishedAt'].replace('Z','+00:00')).timestamp()
 backups=list((scanctl.STORE/'backups/worlds'/a.world).glob('world-*.tar.gz'))
 if not backups:raise ValueError('Fresh cold backup required')
 backup=max(backups,key=lambda p:p.stat().st_mtime)
 now=datetime.datetime.now(datetime.timezone.utc).timestamp()
 if backup.is_symlink()or backup.stat().st_mtime<stopped or now-backup.stat().st_mtime>1800:raise ValueError('Fresh cold backup after stop required (30 min)')
 livectl.checksum_backup(a.world,backup)
 marker=scanctl.slot(a.world)/'story'/MARKER
 if a.mode=='off':scanctl.atomic_request(marker,'off-v1\n')
 else:marker.unlink()
 print('Selected SiegerAdmin '+a.mode.upper()+'. Game remains stopped; start same world.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=('on','off','status'));p.add_argument('world');p.add_argument('--yes',action='store_true');a=p.parse_args()
 try:run(a)
 except(ValueError,OSError,subprocess.SubprocessError)as e:p.exit(2,'Admin mode: '+str(e)+'\n')
