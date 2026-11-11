#!/usr/bin/env python3
"""Disable Extraction runtime without deleting saves, assets or player progress."""
import argparse,datetime,json,re,shutil,sqlite3,subprocess
from pathlib import Path
import scanctl,livectl,npclootctl

def set_block(source,name,values):
    matches=list(re.finditer(r'(?ms)^([ \t]*)'+re.escape(name)+r'[ \t]*=[ \t]*\{(.*?)^\1\}',source))
    if len(matches)!=1:raise ValueError('Expected one '+name+' block')
    m=matches[0];body=m.group(2)
    for key,value in values.items():
        pattern=r'(?m)^([ \t]*)'+key+r'[ \t]*=[ \t]*[^,\n]+,'
        if len(re.findall(pattern,body))>1:raise ValueError('Duplicate '+key)
        body,n=re.subn(pattern,lambda v:v.group(1)+key+' = '+value+',',body)
        if not n:body='\n'+m.group(1)+'    '+key+' = '+value+','+body
    return source[:m.start(2)]+body+source[m.end(2):]

def players_in_hideout(slot):
    root=npclootctl.snapshot('walking_dead')/'3785397275'
    cells=set()
    for p in root.rglob('*.lotheader'):
        m=re.fullmatch(r'(-?\d+)_(-?\d+)\.lotheader',p.name)
        if m:cells.add(tuple(map(int,m.groups())))
    if not cells:raise ValueError('No authoritative Extraction map footprint')
    checked=0;inside=0;inspected=0
    databases=list((slot/'data/Saves/Multiplayer').glob('*/players.db'))
    for p in databases:
        if p.is_symlink():raise ValueError('Unsafe player database')
        with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)as db:
            tables={r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ('networkPlayers','localPlayers'):
                if table not in tables:continue
                columns={r[1]for r in db.execute('PRAGMA table_info('+table+')')}
                if not {'x','y'}<=columns:raise ValueError('Player position schema differs')
                inspected+=1
                condition=' WHERE isDead=0'if'isDead'in columns else''
                for x,y in db.execute('SELECT x,y FROM '+table+condition):
                    if x is None or y is None:raise ValueError('Unknown saved player position')
                    checked+=1
                    if any((int(x)//size,int(y)//size)in cells for size in (256,300)):inside+=1
    if not inspected:raise ValueError('No saved character position schema verified; manual review required')
    return {'characters_checked':checked,'inside_extraction_map':inside}

def run(yes):
    slot=scanctl.slot('walking_dead')
    if scanctl.active_world()!='walking_dead':raise ValueError('Wrong active world')
    positions=players_in_hideout(slot)
    print(json.dumps(positions))
    if not yes:return
    if positions['inside_extraction_map']:raise ValueError('Move saved characters out of the Extraction map first')
    info=json.loads(subprocess.run(['docker','inspect','zomboid-server'],capture_output=True,text=True,check=True,timeout=15).stdout)[0]
    if info['State']['Running']or info['State']['ExitCode']!=0:raise ValueError('Clean stopped game required')
    ended=datetime.datetime.fromisoformat(info['State']['FinishedAt'].replace('Z','+00:00')).timestamp()
    backups=list((scanctl.STORE/'backups/worlds/walking_dead').glob('world-*.tar.gz'))
    if not backups:raise ValueError('Cold backup required')
    backup=max(backups,key=lambda p:p.stat().st_mtime)
    if backup.is_symlink()or backup.stat().st_mtime<ended or datetime.datetime.now(datetime.timezone.utc).timestamp()-backup.stat().st_mtime>1800:raise ValueError('Fresh backup after stop required')
    livectl.checksum_backup('walking_dead',backup)
    sandbox=slot/'data/Server/SiegerZomboid_SandboxVars.lua';mods=slot/'mods.env'
    if sandbox.is_symlink()or mods.is_symlink():raise ValueError('Unsafe world config')
    updated=set_block(sandbox.read_text(),'TarkovTraders',{'TraderAccess':'3','TaskSource':'2','RadioHideoutOnly':'false'})
    target=(scanctl.REPO/'config/mods.walkingdead.env').read_text()
    if 'ExtractionMode'in next(l.split('=',1)[1]for l in target.splitlines()if l.startswith('MODS=')).split(';'):raise ValueError('Extraction remains active in target')
    history=slot/'profile-history'/('extraction-off-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));history.mkdir(parents=True,mode=0o700)
    for p in (sandbox,mods):shutil.copy2(p,history/p.name)
    scanctl.atomic_request(sandbox,updated);scanctl.atomic_request(mods,target)
    print('Extraction runtime disabled; radio-only traders and standalone tasks configured. No saves removed. Start walking_dead.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('world',choices=['walking_dead']);p.add_argument('--yes',action='store_true');a=p.parse_args()
    try:run(a.yes)
    except(ValueError,OSError,sqlite3.Error,subprocess.SubprocessError)as e:p.exit(2,'Extraction OFF: '+str(e)+'\n')
