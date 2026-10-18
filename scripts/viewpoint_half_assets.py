#!/usr/bin/env python3
"""Build LOCAL half-resolution PNG sidecars from the owner's current PZ packs.
Never installs, overwrites inputs, copies proprietary code, or invokes the game.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import os
import re

PACKS = ('Tiles2x', 'Tiles2x.floor', 'Overlays2x', 'Overlays2x.floor',
         'JumboTrees2x', 'JumboTreesBigs2x')
MAX_PACK = 1024 * 1024 * 1024
MAX_PNG = 64 * 1024 * 1024
MAX_PIXELS = 8192 * 8192
PNG = b'\x89PNG\r\n\x1a\n'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()


def read_exact(f, count):
    b = f.read(count)
    if len(b) != count: raise ValueError('Truncated pack')
    return b


def integer(f): return struct.unpack('<I', read_exact(f, 4))[0]


def string(f):
    n = integer(f)
    if not 0 < n < 4096: raise ValueError('Unsafe pack string length')
    return read_exact(f, n).decode('utf-8', errors='strict')


def pages(path):
    """Yield metadata and PNG; support PZPK v1 and legacy PNG pack v0."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_PACK:
        raise ValueError('Unsafe source pack')
    with path.open('rb') as f:
        header = read_exact(f, 4)
        modern = header == b'PZPK'
        if modern:
            if integer(f) != 1: raise ValueError('Unsupported PZPK version')
            count = integer(f)
        else: count = struct.unpack('<I', header)[0]
        if not 0 < count < 4096: raise ValueError('Unsafe page count')
        seen = set()
        for _ in range(count):
            name, n, alpha = string(f), integer(f), integer(f)
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or name in seen or not 0 <= n < 100000 or alpha not in (0, 1):
                raise ValueError('Invalid or duplicate page metadata')
            seen.add(name)
            records = []
            for _ in range(n):
                key = string(f)
                fields = struct.unpack('<8i', read_exact(f, 32))
                records.append((key, fields))
            if modern:
                length = integer(f)
                if not 24 <= length <= MAX_PNG: raise ValueError('Unsafe PNG length')
                png = read_exact(f, length)
            else:
                buf = bytearray(read_exact(f, 8))
                if buf != PNG: raise ValueError('Legacy page is not PNG')
                while True:
                    header = read_exact(f, 8)
                    size, kind = struct.unpack('>I4s', header)
                    if size > MAX_PNG or len(buf) + size + 12 > MAX_PNG:
                        raise ValueError('Oversized PNG chunk')
                    buf += header + read_exact(f, size + 4)
                    if kind == b'IEND': break
                if read_exact(f, 4) != b'\xef\xbe\xad\xde':
                    raise ValueError('Invalid legacy PNG terminator')
                png = bytes(buf)
            if not png.startswith(PNG): raise ValueError('Atlas is not PNG')
            w, h = struct.unpack('>II', png[16:24])
            if w < 2 or h < 2 or w*h > MAX_PIXELS:
                raise ValueError(f'Unsupported atlas dimensions {name}: {w}x{h}')
            for _, (x,y,rw,rh,*_) in records:
                if min(x,y,rw,rh) < 0 or x+rw > w or y+rh > h:
                    raise ValueError('Sprite rectangle outside atlas')
            yield name, w, h, records, png
        if f.read(1): raise ValueError('Unexpected trailing pack bytes')


def resize_png(png, w, h):
    from PIL import Image
    # Premultiplied-alpha BOX averaging avoids transparent RGB halos.
    with Image.open(io.BytesIO(png)) as image:
        image.load()
        if image.size != (w,h): raise ValueError('PNG dimensions changed')
        canvas = Image.new('RGBA', (1 << (w-1).bit_length(), 1 << (h-1).bit_length()))
        canvas.paste(image.convert('RGBA'), (0,0))
        small = canvas.convert('RGBa').resize(
            (canvas.width//2,canvas.height//2), getattr(Image, "Resampling", Image).BOX).convert('RGBA')
        target = io.BytesIO(); small.save(target, format='PNG', compress_level=4)
        return target.getvalue()


def build(game, viewpoint, output):
    game, viewpoint, output = Path(game).resolve(), Path(viewpoint).resolve(), Path(output).absolute()
    repo = Path(__file__).resolve().parents[1]
    if output.exists() or output.is_symlink(): raise ValueError('Output must not exist')
    if output.is_relative_to(repo) or output.is_relative_to(game):
        raise ValueError('Assets must stay outside source repository and Steam game')
    if not output.parent.is_dir(): raise ValueError('Output parent must exist')
    report = {'schema':1,'mode':'half-logical-2x','game_sha256':sha(game/'projectzomboid.jar'),
              'viewpoint_sha256':sha(viewpoint),'packs':{},'pages':[]}
    with tempfile.TemporaryDirectory(prefix='.viewpoint-half-',dir=output.parent) as td:
        stage = Path(td)/'assets'; stage.mkdir()
        props = ['schema=1','game.sha256='+report['game_sha256'],
                 'viewpoint.sha256='+report['viewpoint_sha256']]
        for pack in PACKS:
            src=game/'media/texturepacks'/(pack+'.pack')
            digest=sha(src); report['packs'][pack]=digest
            props.append('pack.'+pack+'.sha256='+digest)
            for page,w,h,records,png in pages(src):
                key=pack+'/'+page
                name=hashlib.sha256(key.encode()).hexdigest()+'.png'
                b=resize_png(png,w,h); (stage/name).write_bytes(b)
                dig=hashlib.sha256(b).hexdigest()
                props.append('page.'+key+'='+','.join([name,str(w),str(h),dig]))
                report['pages'].append({'pack':pack,'page':page,'file':name,'sha256':dig,
                    'width':w,'height':h,'physical_width':(1 << (w-1).bit_length())//2,'physical_height':(1 << (h-1).bit_length())//2,
                    'sprites':len(records),'original_png_sha256':hashlib.sha256(png).hexdigest(),
                    'png_bytes':len(b)})
            print('Prepared',pack,flush=True)
            if sha(src)!=digest: raise ValueError('Source pack changed during build')
        report['page_count']=len(report['pages'])
        report['base_rgba_bytes_before']=sum(p['physical_width']*p['physical_height']*16 for p in report['pages'])
        report['base_rgba_bytes_after']=report['base_rgba_bytes_before']//4
        (stage/'assets.properties').write_text('\n'.join(props)+'\n',encoding='ascii')
        (stage/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
        os.rename(stage,output)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game-dir',type=Path,required=True)
    p.add_argument('--viewpoint-jar',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        r=build(a.game_dir,a.viewpoint_jar,a.output)
        print('Prepared pages:',r['page_count'],'base RGBA MiB:',
              round(r['base_rgba_bytes_before']/1048576,1),'->',round(r['base_rgba_bytes_after']/1048576,1))
    except (OSError,ValueError,ImportError) as e:p.exit(2,str(e)+'\n')
if __name__=='__main__':main()
