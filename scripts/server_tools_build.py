#!/usr/bin/env python3
"""Reproducible own-code agent JAR; game/ZombieBuddy binaries never packaged."""
import argparse,subprocess,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def build(asm_jar,output):
 with tempfile.TemporaryDirectory() as tmp:
  classes=Path(tmp)/'classes';classes.mkdir()
  subprocess.run(['javac','--release','17','-cp',str(asm_jar),'-d',str(classes),
    *map(str,sorted((ROOT/'server/src').rglob('*.java')))],check=True)
  files={'META-INF/MANIFEST.MF':b'Manifest-Version: 1.0\r\nPremain-Class: sieger.server.Agent\r\nClass-Path: file:/bootstrap/ZombieBuddy.jar\r\n\r\n'}
  files.update({p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class')})
  with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED)as z:
   for name,data in sorted(files.items()):
    info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16;z.writestr(info,data)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--asm-jar',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.asm_jar,a.output)
