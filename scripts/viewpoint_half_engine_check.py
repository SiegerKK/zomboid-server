#!/usr/bin/env python3
"""Run independent JVM acceptance with REAL installed engine/ZombieBuddy jars.
No attachment to a running game and no Steam installation/config changes.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile
import zipfile
from viewpoint_half_assets import pages
ROOT=Path(__file__).resolve().parents[1]

def run(game,buddy,view,package,jdk,work,gpu=False,negative=False,full=False):
    game,buddy,view,package,jdk,work=map(lambda p:Path(p).resolve(),(game,buddy,view,package,jdk,work))
    if work.exists():raise ValueError('Check directory must not exist')
    work.mkdir()
    with zipfile.ZipFile(package) as z:
        for item in z.infolist():
            target=work/'package'/item.filename
            if not target.resolve().is_relative_to(work/'package'):raise ValueError('Unsafe client ZIP')
        z.extractall(work/'package')
    mod=work/'package/SiegerViewpointHalf/42/media'
    bridge=mod/'java/client/SiegerViewpointHalf.jar'
    if negative:
        p=mod/'half-atlases/assets.properties'
        lines=p.read_text().splitlines()
        p.write_text('\n'.join('game.sha256='+'0'*64 if s.startswith('game.sha256=') else s for s in lines)+'\n')
    for page,w,h,records,png in pages(game.parent/'media/texturepacks/Tiles2x.pack'):
        if page=='Tiles2x2':(work/'input.png').write_bytes(png);break
    else:raise ValueError('Expected pinned test page missing')
    if full:
        (work/'cache').mkdir()
        (work/'cache/viewpoint-live.properties').write_text('graphics.halfTextures=false\n')
    classes=work/'classes';classes.mkdir()
    cp=':'.join(map(str,[game,buddy,view,bridge]))
    subprocess.run([str(jdk/'bin/javac'),'--release','17','-cp',cp,'-d',str(classes),str(ROOT/'tests/ViewpointHalfEngineCheck.java')],check=True)
    (work/'agent.mf').write_text('Manifest-Version: 1.0\nPremain-Class: ViewpointHalfEngineCheck\nCan-Retransform-Classes: true\nCan-Redefine-Classes: true\n\n')
    agent=work/'check-agent.jar'
    subprocess.run([str(jdk/'bin/jar'),'--create','--file',str(agent),'--manifest',str(work/'agent.mf'),'-C',str(classes),'.'],check=True)
    args=[str(jdk/'bin/java'),'--enable-native-access=ALL-UNNAMED','-Djava.library.path=.',
          '-Dhalf.check.gl='+str(gpu).lower(),'-Dhalf.check.negative='+str(negative).lower(),'-Dhalf.check.full='+str(full).lower(),'-javaagent:'+str(agent),'-cp',str(agent)+':'+cp,'ViewpointHalfEngineCheck',str(work/'cache'),
          str(mod/'half-atlases/assets.properties'),'Tiles2x/Tiles2x2',str(work/'input.png')]
    result=subprocess.run(args,cwd=game.parent,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    (work/'check.log').write_text(result.stdout);print(result.stdout)
    expected='PASS negative engine gate' if negative else 'PASS full engine restart' if full else 'PASS actual engine'
    if result.returncode or expected not in result.stdout or '[Byte Buddy] ERROR' in result.stdout:
        raise ValueError('Actual engine check failed; inspect '+str(work/'check.log'))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['game-jar','buddy-jar','viewpoint-jar','package','jdk','work-dir']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--gpu',action='store_true',help='Separate hidden GL context; requires display/GPU access')
    p.add_argument('--negative',action='store_true',help='Tamper only the isolated copied manifest; expect safe rejection')
    p.add_argument('--full',action='store_true',help='Start isolated cache with Full selected; assert Full survives restart')
    a=p.parse_args()
    try:run(a.game_jar,a.buddy_jar,a.viewpoint_jar,a.package,a.jdk,a.work_dir,a.gpu,a.negative,a.full)
    except (OSError,ValueError,subprocess.SubprocessError) as e:p.exit(2,str(e)+'\n')
