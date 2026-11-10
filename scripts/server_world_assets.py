#!/usr/bin/env python3
"""Mirror only the restricted DATA loader outside mod/checksum directories."""
from pathlib import Path
import argparse
ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'server/lua/SiegerServerWorld.lua'
def render():
 return ('-- Trusted dedicated-server bootstrap only; no scene execution.\n'
  'assert(not SiegerStoryScenes,"world context already initialized")\n'+
  (ROOT/'story/runtime/ZZ_SiegerStoryScenes.lua').read_text()+
  '\nassert(SiegerStoryScenes.world==SiegerServerWorldBootstrapWorld,"wrong world context")\n'
  'SiegerServerWorldContextRevision="world-v1"\nSiegerServerWorldBootstrapWorld=nil\n')
def check():
 if TARGET.is_symlink()or not TARGET.is_file()or TARGET.read_text()!=render():raise ValueError('Server world DATA loader differs')
 print('PASS: standalone restricted world DATA loader')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('command',choices=('check','render'));a=p.parse_args()
 if a.command=='render':TARGET.write_text(render())
 else:check()
