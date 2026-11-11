#!/usr/bin/python3 -I
"""Install one exact CI-passed commit only after a verified cold backup.

No stop/start, rollback, secret edits, Workshop downloads or archive restore.
The caller must first use pz save/stop in the authorized maintenance window.
"""
import datetime
import fcntl
import hashlib
import json
import os
import syslog
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

REPO=Path('/opt/zomboid-server')
REMOTE='https://github.com/SiegerKK/zomboid-server.git'
ENV={'HOME':'/root','USER':'root','LOGNAME':'root','PATH':'/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8'}

def run(argv):
    return subprocess.run(argv,cwd=REPO,env=ENV,check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout.strip()

def git(*args):
    return run(['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','-C',str(REPO),*args])

def main():
    if os.geteuid()!=0 or os.environ.get('SUDO_USER') not in (None,'codex-pz'):raise ValueError('Unauthorized caller')
    a=sys.argv[1:]
    manual=len(a)==3 and a[1:]==['--yes','--manual-reviewed']
    if (len(a) not in (1,2,3) or not re.fullmatch('[0-9a-f]{40}',a[0])
        or (len(a)==2 and a[1]!='--yes') or (len(a)==3 and not manual)):
        raise ValueError('Usage: pz-deploy EXACT_COMMIT [--yes [--manual-reviewed]]')
    sha=a[0]
    if len(a)==1:
        print('PREVIEW ONLY: would install exact commit '+sha+' after CI, stopped-game and cold-backup checks. No changes.')
        return
    # Shared lock with pz. Updates cannot race save/start or another deployment.
    with open('/run/lock/pz-operation.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if run(['/usr/bin/docker','inspect','-f','{{.State.Running}}','zomboid-server'])!='false':
            raise ValueError('Game is running: stop through pz in an authorized window first')
        if run(['/usr/bin/docker','inspect','-f','{{.State.ExitCode}}','zomboid-server'])!='0':
            raise ValueError('Last game exit was not clean')
        world=Path('/srv/zomboid/manager/active-world').read_text().strip()
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,47}',world):raise ValueError('Invalid active world')
        backups=sorted(Path('/srv/zomboid/backups/worlds',world).glob('world-*.tar.gz'),key=lambda p:p.stat().st_mtime)
        if not backups:raise ValueError('Cold backup required')
        backup=backups[-1]
        finished=run(['/usr/bin/docker','inspect','-f','{{.State.FinishedAt}}','zomboid-server'])
        stopped=datetime.datetime.fromisoformat(finished.replace('Z','+00:00')).timestamp()
        now=datetime.datetime.now(datetime.timezone.utc).timestamp()
        if backup.is_symlink() or now-backup.stat().st_mtime>1800 or backup.stat().st_mtime<stopped:
            raise ValueError('Fresh cold backup after the latest game stop required (<=30 min)')
        checksum=Path(str(backup)+'.sha256')
        if checksum.is_symlink():raise ValueError('Unsafe checksum file')
        fields=checksum.read_text().strip().split()
        if len(fields)!=2 or fields[1]!=backup.name or not re.fullmatch('[0-9a-f]{64}',fields[0]):raise ValueError('Invalid backup checksum')
        digest=hashlib.sha256()
        with backup.open('rb') as stream:
            while block:=stream.read(8*1024*1024):digest.update(block)
        if digest.hexdigest()!=fields[0]:raise ValueError('Backup checksum mismatch')
        if not manual:
            request=urllib.request.Request('https://api.github.com/repos/SiegerKK/zomboid-server/actions/runs?head_sha='+sha+'&per_page=30',headers={'Accept':'application/vnd.github+json','User-Agent':'pz-codex-deploy'})
            with urllib.request.urlopen(request,timeout=20) as response:data=json.load(response)
            runs=[r for r in data.get('workflow_runs',[]) if r.get('head_sha')==sha and r.get('name')=='Check Docker configuration']
            if not runs or max(runs,key=lambda r:r['id']).get('conclusion')!='success':raise ValueError('Latest validation CI for exact commit must be successful')
        else:
            # Explicit operator mode, not an automatic fallback after CI failure.
            syslog.openlog('pz-codex-deploy')
            syslog.syslog(syslog.LOG_AUTHPRIV|syslog.LOG_NOTICE,'validation=manual-reviewed commit='+sha+' backup='+backup.name)
        if git('status','--porcelain','--untracked-files=no'):raise ValueError('Tracked deployment files have local changes; refusing overwrite')
        old=git('rev-parse','HEAD')
        # Root executes only its protected repository Git config, never caller checkout.
        git('fetch','--no-tags',REMOTE,sha)
        if git('rev-parse','FETCH_HEAD')!=sha:raise ValueError('Fetched commit mismatch')
        # A modified .env must remain VPS-only, even if an upstream commit tries to add it.
        names=git('ls-tree','-r','--name-only',sha).splitlines()
        if any(n in ('.env','DEPLOYED_COMMIT','DEPLOYED_VALIDATION.json') or n.startswith(('.ssh/','data/','saves/')) for n in names):raise ValueError('Commit includes protected paths')
        git('-c','submodule.recurse=false','checkout','--detach',sha)
        if manual:
            run(['/bin/bash','-n',str(REPO/'pz')])
            run(['/bin/bash',str(REPO/'tests/smoke.sh')])
            for test in ('test_walkingdead.py','test_alife_install.py','test_game_update.py'):
                run(['/usr/bin/python3',str(REPO/'tests'/test)])
            print('PASS manual local validation: Bash syntax, offline smoke, Walking Dead, A-Life and image regressions')
        Path('/opt/zomboid-server/DEPLOYED_COMMIT').write_text(sha+'\n')
        (REPO/'DEPLOYED_VALIDATION.json').write_text(json.dumps({'commit':sha,'validation':'manual-reviewed' if manual else 'github-actions','backup':backup.name,'backup_sha256':fields[0],'installed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2)+'\n')
        print('Installed '+sha+'; previous '+old+'. Game remains STOPPED. Validate client parity before pz start. Secrets and worlds preserved.')

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.SubprocessError) as e:
        print('pz deploy: '+str(e),file=sys.stderr);sys.exit(2)
