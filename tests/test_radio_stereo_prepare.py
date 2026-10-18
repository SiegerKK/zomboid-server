#!/usr/bin/env python3
"""Standalone safe-stage tests; no original artist recordings in the CI runner."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import wave
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import radio_assets
import radio_stereo_prepare as stereo

class StereoPrepareTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.base=Path(self.folder.name)
        self.file=self.base/'radiomusic.zip'
        self.payload=b'this is a fake source stream, not artist audio'
        with zipfile.ZipFile(self.file,'w') as z:
            z.writestr('artists/sample.mp3',self.payload)
        self.owner_sha=hashlib.sha256(self.payload).hexdigest()
        tracks=[]
        for i in range(1,42):
            ident=f'north_track_{i:02d}'
            sha=self.owner_sha if i==38 else hashlib.sha256(str(i).encode()).hexdigest()
            tracks.append({'id':ident,'source_sha256':sha,'duration_seconds':1.5})
        self.manifest=self.base/'owner.json'
        self.manifest.write_text(json.dumps({
            'archive_sha256':stereo.digest(self.file),'tracks':tracks}))
        self.catalog={
            'schema':1,'pack_version':'sr17-v1','runtime_revision':5,
            'clips':{'north_track_38':{
                'sound':'SiegerRadio_NorthTrack38','duration_ms':1500,
                'sha256':'0'*64,'enabled':True,'external_asset':True}},
            'playlist':['north_track_38']}
        self.target=self.base/'output'
        self.original_hash=stereo.digest(radio_assets.CATALOG)
    @staticmethod
    def fake_ffmpeg(args,**kwargs):
        destination=Path(args[-1])
        with wave.open(str(destination),'wb') as out:
            out.setnchannels(2);out.setsampwidth(2);out.setframerate(22050)
            out.writeframes(b'\1\0\2\0' * 33075)  # distinct synthetic L/R, 1.5 sec
        return types.SimpleNamespace(returncode=0,stdout='',stderr='')
    def test_only_stages_original_stereo_and_updates_catalog_digest(self):
        with patch.object(stereo,'MANIFEST',self.manifest),\
             patch.object(radio_assets,'load',return_value=self.catalog),\
             patch.object(stereo,'source_channels',return_value=2),\
             patch.object(stereo.subprocess,'run',side_effect=self.fake_ffmpeg):
            stereo.prepare(self.file,self.target,['north_track_38'],apply=False)
            self.assertFalse(self.target.exists(),'Dry run must not write')
            stereo.prepare(self.file,self.target,['north_track_38'],apply=True)
        candidate=json.loads((self.target/'catalog.candidate.json').read_text())
        pcm=self.target/'pcm/north_track_38.wav'
        self.assertEqual(candidate['clips']['north_track_38']['channels'],2)
        self.assertEqual(candidate['clips']['north_track_38']['sha256'],stereo.digest(pcm))
        self.assertEqual(len(list((self.target/'pcm').glob('*.wav'))),1)
        self.assertNotEqual(candidate['clips']['north_track_38']['sha256'],'0'*64)
        self.assertEqual(self.original_hash,stereo.digest(radio_assets.CATALOG),
                         'Preparation must never modify original catalog')
        self.assertTrue((self.target/'generated/story/runtime/SiegerRadioStation.lua').exists())
    def test_rejects_mono_original_and_does_not_leave_partial_stage(self):
        with patch.object(stereo,'MANIFEST',self.manifest),\
             patch.object(radio_assets,'load',return_value=self.catalog),\
             patch.object(stereo,'source_channels',return_value=1):
            with self.assertRaisesRegex(ValueError,'no independent stereo'):
                stereo.prepare(self.file,self.target,['north_track_38'],apply=True)
        self.assertFalse(self.target.exists())
    def test_rejects_dual_mono_and_silent_channel(self):
        p=self.base/'false-stereo.wav'
        for frame in (b'\1\0\1\0',b'\1\0\0\0'):
            with wave.open(str(p),'wb') as out:
                out.setnchannels(2);out.setsampwidth(2);out.setframerate(22050)
                out.writeframes(frame*100)
            with self.assertRaisesRegex(ValueError,'independent stereo'):
                stereo.stereo_evidence(p)

    def test_rejects_wrong_owner_archive(self):
        with zipfile.ZipFile(self.file,'a') as z:
            z.writestr('extra.mp3',b'not in approved archive')
        with patch.object(stereo,'MANIFEST',self.manifest),\
             patch.object(radio_assets,'load',return_value=self.catalog):
            with self.assertRaisesRegex(ValueError,'pinned owner SHA'):
                stereo.prepare(self.file,self.target,['north_track_38'],apply=True)
        self.assertFalse(self.target.exists())

if __name__=='__main__':unittest.main(verbosity=2)
