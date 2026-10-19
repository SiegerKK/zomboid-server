#!/usr/bin/env python3
"""Build a code-only SiegerAdmin client ZIP with exact manifest verification."""
import argparse
import hashlib
from pathlib import Path
import zipfile
import admin_assets
ROOT=Path(__file__).resolve().parents[1]

def expected():
    admin_assets.check()
    base=ROOT/'mods/SiegerAdmin'
    result={}
    for path in base.rglob('*'):
        if path.is_symlink():raise ValueError('Symlink in admin pack')
        if path.is_file():
            if path.suffix not in ('.lua','.info','.txt'):raise ValueError('Unexpected admin asset')
            result['SiegerAdmin/'+path.relative_to(base).as_posix()]=path.read_bytes()
    if sum(map(len,result.values()))>4*1024*1024:raise ValueError('Admin pack exceeds 4 MiB')
    return result

def build(output):
    wanted=expected()
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(wanted.items()):archive.writestr(name,data)
    with zipfile.ZipFile(output) as archive:
        if set(archive.namelist())!=set(wanted) or any(archive.read(n)!=b for n,b in wanted.items()):raise ValueError('Admin pack verification failed')
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    Path(str(output)+'.sha256').write_text(digest+'  '+output.name+'\n')
    print(output,digest)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args();build(args.output)
