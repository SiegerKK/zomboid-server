#!/usr/bin/env python3
"""Root-owned fixed-file read-only animal queries; no client Lua/module required."""
import argparse,datetime,json,re,secrets,time,subprocess
from pathlib import Path
import scanctl
REQUEST='SiegerServerAnimalsRequest.txt'
RESPONSE='SiegerServerAnimalsResult.txt'
def read_json(path,limit=8*1024*1024):
 if path.is_symlink()or not path.is_file()or path.stat().st_size>limit:raise ValueError('Unsafe/missing result')
 return json.loads(path.read_text())
def ready(world):
 if scanctl.active_world()!=world:raise ValueError('Wrong active world')
 base=scanctl.lua_dir(world)
 call=subprocess.run(['docker','inspect','--format','{{json .}}','zomboid-server'],capture_output=True,text=True,check=True,timeout=15)
 info=json.loads(call.stdout)
 mounts={m['Destination']:Path(m['Source']).resolve() for m in info['Mounts']}
 if not info['State']['Running']or mounts.get('/root/Zomboid')!=(scanctl.slot(world)/'data').resolve():raise ValueError('Running world mount mismatch')
 if (mounts.get('/bootstrap/SiegerServer.jar')!=(scanctl.REPO/'server/runtime/SiegerServer.jar').resolve()or mounts.get('/bootstrap/sieger-server')!=(scanctl.REPO/'server/lua').resolve()):raise ValueError('Server-only extension not mounted')
 p=base/'SiegerServerReady.txt';data=read_json(p,2048)
 started=datetime.datetime.fromisoformat(info['State']['StartedAt'].replace('Z','+00:00')).timestamp()
 if p.stat().st_mtime<started or data.get('world')!=world or data.get('module')!='animals-v1' or data.get('status')!='ready':raise ValueError('Stale/unsupported readiness')
 if not re.fullmatch(r'[0-9a-f-]{36}',data.get('boot','')):raise ValueError('Invalid boot identity')
 return base,data['boot']
def run(a):
 base,boot=ready(a.world);req=base/REQUEST
 if a.command=='snapshot':
  if not scanctl.USERNAME.fullmatch(a.player)or not 1<=a.radius<=500:raise ValueError('Invalid player/radius')
  if not a.yes:print('PREVIEW read-only animals',a.world,a.player,a.radius);return
  if req.is_symlink()or (req.exists()and req.stat().st_size>256):raise ValueError('Unsafe request')
  if req.exists()and req.stat().st_size>0:
   f=req.read_text().strip().split('\t')
   if len(f)!=7:raise ValueError('Malformed old request')
   if f[6]==boot:
    prev=read_json(base/RESPONSE)
    if prev.get('request_id')!=f[1]or prev.get('status')=='running':raise ValueError('Prior request pending; inspect status')
  rid=secrets.token_hex(16)
  scanctl.atomic_request(req,'\t'.join(['v1',rid,a.world,a.player,str(a.radius),str(int(time.time()*1000)+30000),boot])+'\n')
  print('QUEUED',rid,'; pz story animals status',a.world);return
 if req.is_symlink()or not req.is_file()or req.stat().st_size>256:raise ValueError('No safe request')
 f=req.read_text().strip().split('\t')
 if len(f)!=7 or f[2]!=a.world or f[6]!=boot:raise ValueError('Request belongs to a different world/boot')
 data=read_json(base/RESPONSE)
 if data.get('schema')!=1 or data.get('request_id')!=f[1]or data.get('boot')!=boot or data.get('world')!=a.world:raise ValueError('Pending/stale response')
 if data.get('status') not in ('running','complete','partial','error'):raise ValueError('Invalid status')
 if data['status']in('complete','partial'):
  rows=data.get('animals')
  if not isinstance(rows,list)or len(rows)!=data.get('count')or len(rows)>10000:raise ValueError('Invalid animal count')
  if a.command=='report':rows.sort(key=lambda r:r['distance_tiles_2d'])
 if a.output:
  if data['status']!='complete':raise ValueError('Only complete captures can be exported')
  from zombiedebug import output_file
  with output_file(a.output)as stream:json.dump(data,stream,ensure_ascii=False,indent=2)
  print('Private report:',a.output)
 else:print(json.dumps(data,ensure_ascii=False,indent=2))
def main():
 p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
 for cmd in ('snapshot','status','report'):
  c=s.add_parser(cmd);c.add_argument('world');c.add_argument('--player',default='admin');c.add_argument('--radius',type=int,default=100);c.add_argument('--yes',action='store_true');c.add_argument('--output')
 a=p.parse_args()
 try:run(a)
 except(ValueError,OSError,subprocess.SubprocessError)as e:p.exit(2,'Animals: '+str(e)+'\n')
if __name__=='__main__':main()
