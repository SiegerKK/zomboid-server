#!/usr/bin/env python3
"""Build the tiny own-code bootstrap JAR; no game or third-party dependencies."""
import argparse,subprocess,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def build(output):
 with tempfile.TemporaryDirectory() as tmp:
  classes=Path(tmp)/'classes';classes.mkdir()
  subprocess.run(['javac','--release','8','-g:none','-d',str(classes),
    *map(str,sorted((ROOT/'server/src').rglob('*.java')))],check=True)
  files={'META-INF/MANIFEST.MF':b'Manifest-Version: 1.0\r\nPremain-Class: sieger.server.Bootstrap\r\n\r\n'}
  files.update({p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class')})
  with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_STORED)as z:
   for name,data in sorted(files.items()):
    info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_STORED;info.external_attr=0o644<<16;z.writestr(info,data)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.output)
