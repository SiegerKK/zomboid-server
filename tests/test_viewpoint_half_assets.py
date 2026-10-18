#!/usr/bin/env python3
import io
import struct
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import viewpoint_half_assets as a
from PIL import Image

class HalfAssets(unittest.TestCase):
    def png(self,w=5,h=3):
        b=io.BytesIO();im=Image.new('RGBA',(w,h),(255,0,0,255));im.save(b,format='PNG');return b.getvalue()
    def pack(self,legacy=False):
        def n(i):return struct.pack('<I',i)
        def s(v):return n(len(v))+v.encode()
        png=self.png()
        return (n(1) if legacy else b'PZPK'+n(1)+n(1))+s('page')+n(1)+n(1)+s('sprite')+struct.pack('<8i',0,0,5,3,0,0,5,3)+(png+b'\xef\xbe\xad\xde' if legacy else n(len(png))+png)
    def test_both_pack_formats_and_no_trailing_bytes(self):
        for legacy in [True,False]:
            with tempfile.TemporaryDirectory() as td:
                p=Path(td)/'atlas.pack';p.write_bytes(self.pack(legacy));rows=list(a.pages(p))
                self.assertEqual(len(rows),1);self.assertEqual(rows[0][1:3],(5,3))
                p.write_bytes(self.pack(legacy)+b'!')
                with self.assertRaisesRegex(ValueError,'trailing'):list(a.pages(p))
    def test_odd_dimensions_padded_before_halving(self):
        reduced=a.resize_png(self.png(),5,3)
        with Image.open(io.BytesIO(reduced)) as im:
            self.assertEqual(im.size,(4,2));self.assertEqual(im.getpixel((0,0)),(255,0,0,255))
            self.assertEqual(im.getpixel((3,0))[3],0)
    def test_transparent_pixels_do_not_make_dark_halos(self):
        im=Image.new('RGBA',(2,2),(0,0,0,0));im.putpixel((0,0),(255,0,0,255))
        b=io.BytesIO();im.save(b,format='PNG')
        with Image.open(io.BytesIO(a.resize_png(b.getvalue(),2,2))) as small:
            r,g,bl,alpha=small.getpixel((0,0));self.assertEqual((r,g,bl),(255,0,0));self.assertTrue(60<=alpha<=65)
    def test_invalid_bounds_and_truncation_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bad.pack';data=self.pack();p.write_bytes(data[:-8])
            with self.assertRaises((ValueError,struct.error)):list(a.pages(p))
            p.unlink();p.symlink_to('/dev/null')
            with self.assertRaisesRegex(ValueError,'Unsafe'):list(a.pages(p))
    def test_refuses_overwriting_existing_output(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'must not exist'):a.build(td,td,td)

if __name__=='__main__':unittest.main(verbosity=2)
