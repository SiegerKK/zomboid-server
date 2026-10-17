#!/usr/bin/env python3
"""Guarded station CLI and deterministic registered music-pack tests."""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout
import copy
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"story"))
sys.path.insert(0,str(ROOT/"scripts"))
import radioctl
import radio_assets

class StationTests(unittest.TestCase):
    def test_must_add_two_real_music_tracks_before_broadcast(self):
        opts=argparse.Namespace(world="story_test",station_command="start",yes=False)
        with self.assertRaisesRegex(ValueError,"at least two"):
            radioctl.station_control(opts)
        opts.station_command="stop"
        with redirect_stdout(io.StringIO()) as output:
            radioctl.station_control(opts)
        self.assertIn("READ-ONLY",output.getvalue())
        self.assertEqual(len(radioctl.catalog()["playlist"]),0)

    def test_generator_catalog_version_and_checked_music_manifest(self):
        data=radio_assets.load()
        rendered=radio_assets.render(data)
        self.assertIn(radio_assets.STATION,rendered)
        self.assertEqual(rendered[radio_assets.STATION],
            radio_assets.STATION.read_text(encoding="utf-8"))
        self.assertTrue(radio_assets.catalog_version(data).startswith("sr17-v1-"))
        radio_assets.check()
        with tempfile.TemporaryDirectory() as directory:
            fake=Path(directory)/"catalog.json"
            contents=copy.deepcopy(data)
            contents["playlist"]=["song_not_registered"]
            fake.write_text(json.dumps(contents),encoding="utf-8")
            with patch.object(radioctl,"CATALOG",fake):
                with self.assertRaisesRegex(ValueError,"registered"):
                    radioctl.catalog()
            contents["clips"]["song_01"]={
                "sound":"SiegerRadio_Song01","duration_ms":230000,"enabled":True,
                "purpose":"A registered fictitious music clip for manifest test",
                "sha256":"a"*64}
            contents["clips"]["song_02"]={
                "sound":"SiegerRadio_Song02","duration_ms":190000,"enabled":True,
                "purpose":"A second distinct fictitious music clip for manifest test",
                "sha256":"b"*64}
            contents["playlist"]=["song_01","song_02"]
            fake.write_text(json.dumps(contents),encoding="utf-8")
            with patch.object(radioctl,"CATALOG",fake):
                self.assertEqual(radioctl.catalog()["playlist"],["song_01","song_02"])
                with redirect_stdout(io.StringIO()) as out:
                    radioctl.station_control(argparse.Namespace(
                        world="story_test",station_command="start",yes=False))
                self.assertIn("songs: 2",out.getvalue())
            expected=radio_assets.render(contents)
            self.assertIn('{id="song_01",duration=230000}',expected[radio_assets.STATION])
            self.assertIn('{id="song_02",duration=190000}',expected[radio_assets.STATION])
            self.assertNotEqual(radio_assets.catalog_version(contents),
                                radio_assets.catalog_version(data))

if __name__=="__main__":
    unittest.main(verbosity=2)
