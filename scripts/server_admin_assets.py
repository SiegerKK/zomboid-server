#!/usr/bin/env python3
"""Generate server-only runtime and the minimal, stable client compatibility pack."""
from pathlib import Path
import argparse, json, sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import admin_assets
ROOT=Path(__file__).resolve().parents[1]
MODULES=tuple(sorted((*admin_assets.MODULES,'SiegerRuntimeAudit')))
COMPAT=ROOT/'server/client-compat/SiegerAdmin'
def render():
    result={}
    for name in MODULES:
        body=('if isClient and isClient() then return end\n'+(ROOT/'scripts/runtime-tlou-audit.lua').read_text()
              if name=='SiegerRuntimeAudit' else (ROOT/'story/runtime'/(name+'.lua')).read_text())
        result[ROOT/'server/lua/admin'/(name+'.lua')]=body+'\nSiegerServerLoadedModules["'+name+'"] = true\n'
    for name in admin_assets.AUTHORED:
        result[COMPAT/name]=(ROOT/'mods/SiegerAdmin'/name).read_text()
    result[ROOT/'server/admin-modules.json']=json.dumps(MODULES,indent=2)+'\n'
    return result

def check():
    wanted=render()
    for p,body in wanted.items():
        if p.is_symlink() or not p.is_file() or p.read_text()!=body:raise ValueError('Server asset differs: '+str(p))
    for base in (COMPAT,ROOT/'server/lua/admin'):
        actual={p for p in base.rglob('*') if p.is_file() or p.is_symlink()}
        if actual!={p for p in wanted if p.is_relative_to(base)}:raise ValueError('Unexpected server/compat files')
    print('PASS: server runtime mirrors and five-file client compatibility pack')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('render','check'));a=p.parse_args()
    if a.command=='render':
        for path,body in render().items():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body)
    else:check()
