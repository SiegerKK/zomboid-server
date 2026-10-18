#!/usr/bin/env python3
"""Offline safety contract for PR #27; no game or proprietary audio required."""
import json
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAVA=ROOT/"mods/SiegerRadio/42/media/java/src/siegerradio/bridge/SiegerRadioBridge.java"
CLIENT=ROOT/"mods/SiegerRadio/42/media/lua/client/SiegerRadioClient.lua"
STATION=ROOT/"mods/SiegerRadio/42/media/lua/server/SiegerRadioStation.lua"
STORY=ROOT/"story/runtime/SiegerStoryRadio.lua"
MIRROR=ROOT/"mods/SiegerRadio/42/media/lua/server/SiegerStoryRadio.lua"
CATALOG=ROOT/"story/radio/catalog.json"


class VolumePanContract(unittest.TestCase):
    def test_client_server_bridge_build_handshake(self):
        java=JAVA.read_text()
        scripts=[path.read_text() for path in [CLIENT,STATION,STORY,MIRROR]]
        bridge=re.search(r'BRIDGE_BUILD\s*=\s*"([^"]+)"',java)
        self.assertIsNotNone(bridge)
        self.assertEqual(bridge.group(1),"radio-char15")
        for content in scripts:
            match=re.search(r'local CLIENT_BUILD="([^"]+)"',content)
            self.assertIsNotNone(match)
            self.assertEqual(match.group(1),bridge.group(1))
        self.assertEqual(STORY.read_text(),MIRROR.read_text())
        catalog=json.loads(CATALOG.read_text())
        self.assertEqual(catalog["runtime_revision"],10)
        self.assertEqual(len(catalog["playlist"]),41)

    def test_fmod_and_lua_distance_parity(self):
        java=JAVA.read_text()
        lua=CLIENT.read_text()
        values={}
        for name,number in re.findall(
            r'\b([A-Z]+_(?:MIN_NEAR|NEAR_SPAN|MIN_FAR|FAR_SPAN))\s*=\s*([0-9.]+)f',java):
            values[name]=float(number)
        self.assertEqual(len(values),8)
        self.assertIn('return 6+24*volume*(occupied and 1 or EXTERIOR_GAIN)',lua)
        self.assertIn('dist<audibleRadius("furniture",v,mode,false)^2',lua)
        self.assertIn('sqDistance(player,ax,ay,az)<audibleRadius("vehicle",vol,mode,false)^2',lua)
        self.assertIn('sqDistance(player,x,y,z)>=audibleRadius("vehicle",volume,"music",seated)^2',lua)
        self.assertIn('if(spatial) applyMusicDistances(vehicle,gain)',java)
        self.assertIn('MUSIC_GAIN_AT_FULL_VOLUME=.65',lua)
        self.assertIn('EXTERIOR_GAIN=.50',lua)
        self.assertIn('vehicleMusicPosition(car)',lua)
        self.assertIn('car:getWorldPos(0,offset:y(),localZ,dashScratch)',lua)
        self.assertIn('return spatial,source.x,source.y,source.z',lua)
        self.assertIn('if mode~="cue" then ax,ay,az=vehicleMusicPosition(car) end',lua)
        self.assertIn('radioSource(p,freq,"cue")',lua)
        self.assertIn('GAIN_AT_FULL_DEVICE_VOLUME=0.65f',java)
        for volume in (0.01,0.10,0.5,1.0):
            self.assertAlmostEqual(6+24*volume*0.5,6+12*volume)
            self.assertLess(6+24*volume*0.5,6+24*volume)
            for kind,base,step in (("FURNITURE",3,9),("VEHICLE",6,24)):
                near=values[kind+"_MIN_NEAR"]+values[kind+"_NEAR_SPAN"]*volume
                far=values[kind+"_MIN_FAR"]+values[kind+"_FAR_SPAN"]*volume
                self.assertGreater(far,near)
                self.assertAlmostEqual(far,base+step*volume)
                if volume==1.0:
                    self.assertAlmostEqual(far,12 if kind=="FURNITURE" else 30)
                    self.assertAlmostEqual(near,4 if kind=="FURNITURE" else 4.8)

    def test_no_new_zombie_music_sound(self):
        for path in [JAVA,CLIENT,STATION,STORY,MIRROR]:
            source=path.read_text()
            self.assertNotIn("WorldSoundManager",source,
                             "No new server/world zombie sound should be emitted in "+str(path))
            self.assertNotIn("addSoundRepeating",source)
        bridge=JAVA.read_text()
        self.assertIn('CABIN_3D_LEVEL=0.25f',bridge)
        self.assertIn('CABIN_SPREAD=20f',bridge)
        self.assertIn('if(inside&&!vehicleSource)return false;',bridge)
        self.assertIn('applyCabinPan(inside?CABIN_3D_LEVEL:1f)',bridge)
        self.assertIn('FMOD_3D',bridge)
        self.assertIn('level3d==null',bridge)


if __name__=="__main__":
    unittest.main(verbosity=2)
