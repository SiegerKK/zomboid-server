#!/usr/bin/env python3
"""Container-only anonymous Steam download; no game execution or world mount."""
import json,re,subprocess
from pathlib import Path
ids=json.loads(Path('/bootstrap/workshop-request.json').read_text())
assert isinstance(ids,list)and 1<=len(ids)<=20 and len(ids)==len(set(ids))
assert all(isinstance(i,str)and re.fullmatch('[0-9]{5,12}',i)for i in ids)
subprocess.run(['steamcmd','+login','anonymous','+quit'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=180,check=True)
for wid in ids:
 command=['steamcmd','+force_install_dir','/root/.local/share/Steam','+login','anonymous','+workshop_download_item','108600',wid,'+quit']
 p=subprocess.run(command,capture_output=True,text=True,timeout=600)
 ok=p.returncode==0 and re.search(r'Success\. Downloaded item '+wid+r'\b',p.stdout,re.I)
 print(('DOWNLOADED 'if ok else 'FAILED ')+wid,flush=True)
 if not ok:
  # Anonymous session has no account credentials; report only bounded Steam errors.
  print('\n'.join(l[:250]for l in (p.stdout+p.stderr).splitlines()if re.search('ERROR|Failure',l,re.I))[-1500:],flush=True)
  raise SystemExit(2)
