#!/usr/bin/env python3
"""External music packaging checks without shipping music to Git/CI."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import radio_assets
import radio_pack
sys.path.insert(0,str(ROOT/"story"))
import radioctl

class PackTests(unittest.TestCase):
    def test_owner_manifest_has_exact_41_unique_sources_and_registered_ids(self):
        tracks=json.loads((ROOT/'story/radio/owner-tracklist.json').read_text())['tracks']
        catalog=radio_assets.load()
        self.assertEqual(len(tracks),41)
        self.assertEqual(len({x['id'] for x in tracks}),41)
        self.assertEqual({x['id'] for x in tracks},set(catalog['playlist']))
        self.assertEqual(len({x['source_sha256'] for x in tracks}),41)
        for t in tracks:
            self.assertTrue(catalog['clips'][t['id']]['external_asset'])
            self.assertTrue(5<=t['duration_seconds']<=720)

    def test_missing_external_requires_explicit_ci_flag_and_builtin_is_required(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            folder.joinpath('test_tone.wav').write_bytes((radio_assets.AUDIO_DIR/'test_tone.wav').read_bytes())
            with patch.object(radio_assets,'AUDIO_DIR',folder):
                with self.assertRaisesRegex(ValueError,'missing'):
                    radio_assets.check()
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    radio_assets.check(allow_missing_external=True)
                self.assertIn('41 external assets NOT checked',out.getvalue())
                folder.joinpath('test_tone.wav').unlink()
                with self.assertRaisesRegex(ValueError,'missing'):
                    radio_assets.check(allow_missing_external=True)

    def test_runtime_revision_changes_both_handshakes(self):
        data=radio_assets.load()
        self.assertEqual(radio_assets.catalog_version(data),radioctl.catalog_version(data))
        old=dict(data);old['runtime_revision']=0
        self.assertNotEqual(radio_assets.catalog_version(old),radio_assets.catalog_version(data))
        for revision in (-1,1000,True,'1'):
            bad=dict(data);bad['runtime_revision']=revision
            with tempfile.TemporaryDirectory() as d:
                path=Path(d)/'catalog.json';path.write_text(json.dumps(bad))
                with patch.object(radio_assets,'CATALOG',path),self.assertRaises(ValueError):radio_assets.load()
                with patch.object(radioctl,'CATALOG',path),self.assertRaises(ValueError):radioctl.catalog()

    def test_pack_hash_and_path_checks_precede_destination_creation(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d); archive=folder/'pack.zip';destination=folder/'installed'
            wanted={'SiegerRadio/42/mod.info':hashlib.sha256(b'ok').hexdigest()}
            with patch.object(radio_pack,'expected',return_value=wanted):
                for name,data in [('SiegerRadio/42/mod.info',b'wrong'),('../escape',b'ok')]:
                    with zipfile.ZipFile(archive,'w') as z:z.writestr(name,data)
                    with self.assertRaises(ValueError):radio_pack.install(archive,destination,False)
                    self.assertFalse(destination.exists())
                with zipfile.ZipFile(archive,'w') as z:z.writestr('SiegerRadio/42/mod.info',b'ok')
                radio_pack.install(archive,destination,False)
                self.assertEqual((destination/'42/mod.info').read_bytes(),b'ok')
                with self.assertRaisesRegex(ValueError,'new'):
                    radio_pack.install(archive,destination,False)

if __name__=='__main__':unittest.main(verbosity=2)
