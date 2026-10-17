#!/usr/bin/env python3
"""Offline root-radio protocol, audio asset, and forbidden-operation tests."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'story'))
import radioctl
import scanctl


class StoryRadioTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.store = self.folder / 'store'
        world = self.store / 'worlds' / 'story_test'
        (world / 'data' / 'Lua').mkdir(parents=True)
        (world / 'profile').write_text('test')
        old = scanctl.STORE
        scanctl.STORE = self.store
        self.addCleanup(lambda: setattr(scanctl, 'STORE', old))
        self.request, self.response = radioctl.paths('story_test')

    def command(self, kind='text', **overrides):
        data = dict(world='story_test', command=kind, frequency='101.3',
                    source='10622,9221', signal_strength=100000,
                    text='Проверка NORTHBOUND', clip='test_tone',
                    allow_audio=False, allow_global=False,
                    scope='tuned', yes=False, acknowledge_failed=False)
        data.update(overrides)
        return argparse.Namespace(**data)

    def test_frequency_and_cli_validation(self):
        self.assertEqual(radioctl.freq_khz('101.3'), 101300)
        self.assertEqual(radioctl.freq_khz('88.0'), 88000)
        self.assertEqual(radioctl.freq_khz('108.0'), 108000)
        for v in ('101', '101.35', '87.9', '108.1', 'nan', '1e2', '101,3'):
            with self.subTest(v=v), self.assertRaises(ValueError):
                radioctl.freq_khz(v)
        self.assertEqual(radioctl.position('10622,9221'), (10622, 9221))
        with self.assertRaises(ValueError):
            radioctl.position('10622;9221')
        with self.assertRaises(ValueError):
            radioctl.action_packet(self.command(text='X'*481))
        with self.assertRaises(ValueError):
            radioctl.action_packet(self.command(text='bad\nnew line'))

    def test_readonly_text_and_one_queued_utf8_packet(self):
        a = self.command()
        with redirect_stdout(io.StringIO()) as out:
            radioctl.transmit(a)
        self.assertIn('READ-ONLY', out.getvalue())
        self.assertFalse(self.request.exists())
        a.yes = True
        with patch.object(radioctl, 'assert_ready'):
            with redirect_stdout(io.StringIO()):
                radioctl.transmit(a)
        previous = radioctl.read_request('story_test')
        self.assertRegex(previous['id'], r'^[0-9a-f]{32}$')
        self.assertEqual(previous['frequency'], 101300)
        fields = self.request.read_text('ascii').strip().split('\t')
        self.assertEqual(fields[:1]+fields[2:5], ['v1', 'story_test', 'text', '101300'])
        self.assertEqual(bytes.fromhex(fields[9]).decode('utf-8'), a.text)
        self.assertEqual(self.request.stat().st_mode & 0o777, 0o600)
        self.assertEqual(radioctl.read_response('story_test', previous['id']), {'status': 'pending'})
        with patch.object(radioctl, 'assert_ready'), self.assertRaisesRegex(ValueError, 'pending'):
            radioctl.transmit(a)
        self.response.write_text(f"v1\t{previous['id']}\tstory_test\ttext\tcomplete\t101300\t0\tradio_api_called\n")
        self.assertEqual(radioctl.read_response('story_test', previous['id'])['status'], 'complete')
        with patch.object(radioctl, 'assert_ready'):
            with redirect_stdout(io.StringIO()):
                radioctl.transmit(a)
        self.assertNotEqual(radioctl.read_request('story_test')['id'], previous['id'])

    def test_audio_gates_and_catalog(self):
        with self.assertRaisesRegex(ValueError, '--allow-audio'):
            radioctl.action_packet(self.command('audio'))
        a = self.command('audio', allow_audio=True)
        packet, preview = radioctl.action_packet(a)
        self.assertIn('\ttuned\ttest_tone\t750\n', packet)
        self.assertIsNone(preview['text'])
        self.assertTrue(preview['client_pack_required'])
        a.scope = 'global'
        with self.assertRaisesRegex(ValueError, '--allow-global'):
            radioctl.action_packet(a)
        a.allow_global = True
        self.assertEqual(radioctl.action_packet(a)[1]['scope'], 'global')
        a.clip = '../bad.ogg'
        with self.assertRaisesRegex(ValueError, 'Unregistered'):
            radioctl.action_packet(a)
        with self.assertRaisesRegex(ValueError, 'story_test'):
            radioctl.assert_ready('road_home')
        catalog = radioctl.catalog()
        self.assertEqual(catalog['station']['frequency_khz'], 101300)
        self.assertEqual(catalog['clips']['test_tone']['sound'], 'SiegerRadio_TestTone')
        self.assertRegex(catalog['clips']['test_tone']['sha256'], r'^[0-9a-f]{64}$')

    def test_binary_clip_pack_is_valid_wave_and_registered(self):
        sample = ROOT / 'mods/SiegerRadio/42/media/sound/SiegerRadio/test_tone.wav'
        self.assertEqual(hashlib.sha256(sample.read_bytes()).hexdigest(),
                         radioctl.catalog()['clips']['test_tone']['sha256'])
        with wave.open(str(sample), 'rb') as src:
            self.assertEqual(src.getnchannels(), 1)
            self.assertEqual(src.getsampwidth(), 2)
            self.assertGreater(src.getframerate(), 16000)
            self.assertEqual(round(src.getnframes()/src.getframerate()*1000), 750)
        scripts = (ROOT/'mods/SiegerRadio/42/media/scripts/SiegerRadio_Sounds.txt').read_text()
        client = (ROOT/'mods/SiegerRadio/42/media/lua/client/SiegerRadioClient.lua').read_text()
        server = (ROOT/'story/runtime/SiegerStoryRadio.lua').read_text()
        self.assertIn('sound SiegerRadio_TestTone', scripts)
        self.assertIn('test_tone.wav', scripts)
        self.assertIn('SiegerRadio_TestTone', client)
        self.assertIn('test_tone={sound="SiegerRadio_TestTone",duration=750}', server)
        self.assertNotIn('Bandits2', client)


if __name__ == '__main__':
    unittest.main(verbosity=2)
