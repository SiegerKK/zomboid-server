#!/usr/bin/env python3
"""Compile against owner's real jars and package a LOCAL client test ZIP."""
import argparse
import json
from pathlib import Path
import os
import subprocess
import tempfile
import zipfile
from viewpoint_half_assets import sha

ROOT=Path(__file__).resolve().parents[1]
MOD=ROOT/'mods/SiegerViewpointHalf'

def build(game, buddy, view, assets, output, jdk):
    game,buddy,view,assets=map(lambda p:Path(p).resolve(),(game,buddy,view,assets))
    output=Path(output).absolute();jdk=Path(jdk).resolve()
    if output.exists() or output.is_symlink() or output.is_relative_to(ROOT):
        raise ValueError('Output must be new and outside repository')
    report=json.loads((assets/'manifest.json').read_text())
    if sha(game)!=report['game_sha256'] or sha(view)!=report['viewpoint_sha256']:
        raise ValueError('Game/Viewpoint hashes differ from assets')
    for item in report['pages']:
        p=assets/item['file']
        if p.is_symlink() or not p.resolve().is_relative_to(assets) or sha(p)!=item['sha256']:
            raise ValueError('Asset hash/path mismatch')
    with tempfile.TemporaryDirectory(prefix='half-build-',dir=output.parent) as td:
        stage=Path(td);cls=stage/'classes';cls.mkdir()
        src=sorted((MOD/'42/media/java/src').rglob('*.java'))
        subprocess.run([str(jdk/'bin/javac'),'--release','17','-cp',str(game)+':'+str(buddy),'-d',str(cls),*map(str,src)],check=True)
        (cls/'half-build.properties').write_text('game.sha256='+sha(game)+'\nviewpoint.sha256='+sha(view)+'\n')
        jar=stage/'SiegerViewpointHalf.jar'
        subprocess.run([str(jdk/'bin/jar'),'--create','--no-manifest','--file',str(jar),'-C',str(cls),'.'],check=True)
        staged_zip=stage/'client.zip'
        with zipfile.ZipFile(staged_zip,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=4) as z:
            for p in [MOD/'42/mod.info',MOD/'common/mod.info']:
                z.write(p,'SiegerViewpointHalf/'+str(p.relative_to(MOD)))
            z.write(jar,'SiegerViewpointHalf/42/media/java/client/SiegerViewpointHalf.jar')
            for p in sorted(assets.iterdir()):
                if p.is_symlink() or not p.is_file():raise ValueError('Unexpected asset entry')
                z.write(p,'SiegerViewpointHalf/42/media/half-atlases/'+p.name)
            z.writestr('INSTALL-RU.txt',INSTALL)
        # Atomic exclusive publication: no partial final ZIP and no overwrite race.
        os.link(staged_zip,output)
    checksum=sha(output)
    output.with_suffix(output.suffix+'.sha256').write_text(checksum+'  '+output.name+'\n')
    output.with_suffix('.install.txt').write_text(INSTALL)
    print('ZIP:',output,'SHA-256:',checksum)

INSTALL='''SiegerViewpointHalf 0.1.0 — экспериментальная клиентская сборка
Проверка в реальной игре обязательна; выигрыш VRAM ещё не измерен.
1. Полностью закройте клиент игры. Сервер не менять.
2. Распакуйте папку SiegerViewpointHalf в ~/Zomboid/mods/.
3. Включите Viewpoint, ZombieBuddy и SiegerViewpointHalf для тестового запуска.
   При запросе ZombieBuddy проверьте разрешение нашего Java-пакета.
4. Сначала проверьте одиночный мир. MP и LuaChecksum требуют отдельной проверки.
5. Half включён по умолчанию. Галка Viewpoint Half-resolution textures выбирает
   режим следующего запуска; полностью перезапускайте клиент после изменения.
6. Не меняется Core.tileScale и не включаются старые неполные Tiles1x.
7. Ищите [SiegerViewpointHalf] ready/session/pages в console.txt.
   DISABLED или FULL fallback означает, что оптимизация не применилась полностью.
8. Проверяйте размер предметов, полы, деревья, прозрачность, выбор мышью,
   Vivid/Default и вид от третьего лица. Не объявляйте успех по одной галке.
9. Для отключения уберите мод из списка и полностью перезапустите клиент.
   Режим также хранится в ~/Zomboid/sieger-viewpoint-half.properties: enabled=false.
Игровые текстуры только для локального использования. Не публиковать ZIP/PNG.
'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['game-jar','buddy-jar','viewpoint-jar','assets','output','jdk']:
        p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args()
    try:build(a.game_jar,a.buddy_jar,a.viewpoint_jar,a.assets,a.output,a.jdk)
    except (OSError,ValueError,subprocess.SubprocessError) as e:p.exit(2,str(e)+'\n')
if __name__=='__main__':main()
