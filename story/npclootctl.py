#!/usr/bin/env python3
"""Bounded NPC weapon condition setting and reviewed trader addition for walking_dead."""
import argparse,datetime,json,re,shutil,subprocess
from pathlib import Path
import scanctl,livectl,workshopctl

def patch_condition(source):
    blocks=list(re.finditer(r'(?ms)^([ \t]*)ALife[ \t]*=[ \t]*\{(.*?)^\1\}',source))
    if len(blocks)!=1:raise ValueError('Expected exactly one ALife Sandbox block')
    block=blocks[0];body=block.group(2)
    pattern=r'(?m)^([ \t]*)Drops_WeaponCondition[ \t]*=[ \t]*([0-9]+)[ \t]*,'
    found=list(re.finditer(pattern,body))
    if len(found)>1:raise ValueError('Duplicate weapon condition')
    old=int(found[0].group(2)) if found else None
    if old is not None and not 1<=old<=12:raise ValueError('Unexpected old weapon condition enum')
    if found:
        body=re.sub(pattern,lambda m:m.group(1)+'Drops_WeaponCondition = 8,',body,count=1)
    else:body='\n'+block.group(1)+'    Drops_WeaponCondition = 8,'+body
    return source[:block.start(2)]+body+source[block.end(2):],old

def snapshot(world):
    marker=(scanctl.slot(world)/'workshop-snapshot').read_text().strip()
    if not re.fullmatch(r'workshop-[0-9]{8}T[0-9]{6}Z',marker):raise ValueError('Invalid snapshot')
    root=scanctl.STORE/'mod-snapshots'/marker
    if root.is_symlink()or not (root/'verified.json').is_file():raise ValueError('Unverified snapshot')
    return root/'workshop/content/108600'

def audit(world):
    root=snapshot(world)/'3811018258'
    if not root.is_dir()or root.is_symlink():raise ValueError('Trader payload absent')
    files={};size=0
    for p in root.rglob('*'):
        if p.is_symlink():raise ValueError('Symlink in payload')
        if not p.is_file()or not(p.name=='mod.info'or p.suffix=='.lua'or p.name=='sandbox-options.txt'):continue
        data=p.read_text(errors='strict');size+=len(data.encode())
        if len(files)>=2000 or size>8*1024*1024:raise ValueError('Source audit budget exceeded')
        files[str(p.relative_to(root))]=data
    print(json.dumps({'workshop_id':'3811018258','files':files},ensure_ascii=False))

def apply(world):
    slot=scanctl.slot(world)
    if scanctl.active_world()!=world:raise ValueError('Wrong active world')
    info=json.loads(subprocess.run(['docker','inspect','zomboid-server'],capture_output=True,text=True,check=True,timeout=15).stdout)[0]
    if info['State']['Running']or info['State']['ExitCode']!=0:raise ValueError('Clean stopped game required')
    mounts={m['Destination']:Path(m['Source']).resolve()for m in info['Mounts']}
    if mounts.get('/root/Zomboid')!=(slot/'data').resolve():raise ValueError('Wrong world mount')
    ended=datetime.datetime.fromisoformat(info['State']['FinishedAt'].replace('Z','+00:00')).timestamp()
    backups=list((scanctl.STORE/'backups/worlds'/world).glob('world-*.tar.gz'))
    if not backups:raise ValueError('Cold backup required')
    backup=max(backups,key=lambda p:p.stat().st_mtime)
    if backup.is_symlink()or backup.stat().st_mtime<ended or datetime.datetime.now(datetime.timezone.utc).timestamp()-backup.stat().st_mtime>1800:raise ValueError('Fresh cold backup after stop required')
    livectl.checksum_backup(world,backup)
    target=slot/'data/Server/SiegerZomboid_SandboxVars.lua'
    if target.is_symlink()or target.stat().st_size>1024*1024:raise ValueError('Unsafe Sandbox')
    source=target.read_text();new,old=patch_condition(source)
    mods=slot/'mods.env';desired=scanctl.REPO/'config/mods.walkingdead.env'
    if mods.is_symlink():raise ValueError('Unsafe mod profile')
    def fields(p):return dict(l.split('=',1)for l in p.read_text().splitlines()if l and not l.startswith('#'))
    before,after=fields(mods),fields(desired)
    if set(after['MODS'].split(';'))-set(before['MODS'].split(';'))not in (set(),{'TarkovTraders'}):raise ValueError('Unexpected mod addition')
    if set(before['MODS'].split(';'))-set(after['MODS'].split(';')):raise ValueError('Mod removal refused')
    if set(after['WORKSHOP_ITEMS'].split(';'))-set(before['WORKSHOP_ITEMS'].split(';'))not in (set(),{'3811018258'}):raise ValueError('Unexpected Workshop addition')
    history=slot/'profile-history'/('npc-loot-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));history.mkdir(parents=True,mode=0o700)
    shutil.copy2(target,history/target.name);shutil.copy2(mods,history/'mods.env')
    scanctl.atomic_request(target,new);scanctl.atomic_request(mods,desired.read_text())
    workshopctl.run(argparse.Namespace(world=world,yes=True))
    root=snapshot(world)/'3811018258'
    infos=[dict(l.split('=',1)for l in p.read_text().splitlines()if '='in l)for p in root.rglob('mod.info')]
    if not any(i.get('id')=='TarkovTraders'for i in infos):raise ValueError('Wrong downloaded Mod ID')
    for i in (row for row in infos if row.get('id')=='TarkovTraders'):
        if i.get('javaJarFile'):raise ValueError('Unexpected Java needs review')
        deps=set(filter(None,i.get('require','').replace('\\','').replace(',',';').split(';')))
        if deps-set(after['MODS'].split(';')):raise ValueError('Unreviewed dependency')
    print('Set ALife.Drops_WeaponCondition: '+str(old)+' -> 8 (6/10). Trader snapshot staged. Game remains stopped for source review.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('world',choices=['walking_dead']);p.add_argument('--audit-traders',action='store_true');p.add_argument('--yes',action='store_true');a=p.parse_args()
    try:
        if a.audit_traders:audit(a.world)
        elif a.yes:apply(a.world)
        else:p.exit(2,'Explicit --yes required; no changes\n')
    except(ValueError,OSError,subprocess.SubprocessError)as e:p.exit(2,'NPC loot: '+str(e)+'\n')
