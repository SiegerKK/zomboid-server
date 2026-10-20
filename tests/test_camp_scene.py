#!/usr/bin/env python3
"""Bundled scene contracts; no server, inventory, filesystem or game mutation."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'story'))
import constructionsetup as setup


class BundledCampTests(unittest.TestCase):
    def args(self, world='other_world', stage='phase01', *extra):
        parser = argparse.ArgumentParser()
        setup.add_subcommand(parser.add_subparsers(dest='command', required=True))
        return parser.parse_args(['setup', world, '--scene', 'survival_farm', '--stage', stage, *extra])

    def test_all_four_stages_retarget_without_rewriting_scene(self):
        folder = setup.SCENES['survival_farm']
        before = {p: p.read_bytes() for p in folder.glob('*.json')}
        for world in ('fresh_vanilla', 'tlou_save'):
            for n, (builds, stocks) in enumerate(((2, 35), (12, 40), (71, 54), (202, 65)), 1):
                with self.subTest(world=world, stage=n):
                    args = self.args(world, f'phase{n:02d}')
                    plan, supplies, compiled, identity, inputs = setup.prepare(args)
                    self.assertEqual(plan['world'], world)
                    self.assertEqual(supplies['world'], world)
                    self.assertEqual(identity['world'], world)
                    self.assertEqual(identity['source_world'], 'camp_template')
                    self.assertEqual(compiled['actions'], builds)
                    self.assertEqual(len(setup.batch.compile_plan(supplies, world)), stocks)
                    self.assertEqual(compiled['requires'], [] if n == 1 else [f'phase{n-1:02d}'])
                    self.assertEqual(len(inputs), 2 if n == 1 else 3)
                    self.assertIsNone(args.file)
                    self.assertIsNone(args.batch)
                    self.assertEqual(setup.prepare(args)[3], identity)
        self.assertEqual(before, {p: p.read_bytes() for p in folder.glob('*.json')})

    def test_preview_does_not_contact_server_or_write_world_state(self):
        with patch.object(setup.scanctl, 'assert_module_ready', side_effect=AssertionError('contact')), \
             patch.object(setup, 'journal_dir', side_effect=AssertionError('state')), \
             patch.object(setup.livectl, 'atomic_write', side_effect=AssertionError('write')), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            setup.run(self.args())
        self.assertIn('PREVIEW ONLY', out.getvalue())
        self.assertEqual(json.JSONDecoder().raw_decode(out.getvalue())[0]['mode'], 'preview')

    def test_mixed_override_unknown_stage_and_traversal_refused(self):
        for extra in (('--batch', '/tmp/other.json'), ('--source-world', 'other')):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                setup.prepare(self.args('world', 'phase01', *extra))
        with self.assertRaises(ValueError):
            setup.prepare(self.args('world', '../phase01'))
        args = self.args(); args.scene = '../../private'
        with self.assertRaises(ValueError):
            setup.prepare(args)

    def test_builtin_verify_uses_destination_and_refuses_foreign_survey(self):
        args=self.args('new_slot')
        compiled=setup.prepare(args)[2]
        records=[]
        for wire in compiled['rows']:
            r=wire.split('\t');at=dict(zip(('x','y','z'),map(int,r[4:7])))
            records.extend([
                dict(at,kind='square',loaded=True),
                dict(at,kind='object',**{'class':'IsoWindow'},sprite=r[8],face=r[7],room='kitchen')])
            at_out={'x':at['x']-(r[7]=='W'),'y':at['y']-(r[7]=='N'),'z':at['z']}
            records.extend([
                dict(at_out,kind='square',loaded=True),
                dict(at_out,kind='object',**{'class':'IsoBarricade'},
                     construction_tag=f"survival_farm:phase01:{r[1]}",barricade_planks=int(r[10]))])
        snap={'world':'new_slot','summary':{'status':'complete','errors':0,'truncated':False},'records':records}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'post.json';path.write_text(json.dumps(snap))
            verify=argparse.Namespace(world='new_slot',scene='survival_farm',file=None,stage='phase01',survey=str(path),source_world=None)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                setup.build.verify(verify)
            self.assertEqual(json.loads(out.getvalue())['counts']['seen_place'],2)
            snap['world']='foreign';path.write_text(json.dumps(snap))
            with self.assertRaisesRegex(ValueError,'different world'):
                setup.build.verify(verify)

    def test_apply_still_requires_backup_and_current_survey(self):
        args=self.args('new_slot','phase01','--yes')
        with patch.object(setup.os,'geteuid',return_value=0), \
             patch.object(setup,'journal_dir',return_value=Path('/not-created')), \
             patch.object(setup.scanctl,'assert_module_ready',side_effect=AssertionError('contact')), \
             self.assertRaisesRegex(ValueError,'needs --survey'):
            setup.run(args)

    def test_missing_file_batch_still_refused(self):
        args = self.args(); args.scene = None
        with self.assertRaises(ValueError):
            setup.prepare(args)

    def test_all_house_windows_are_exterior_and_new_beds_are_scarce(self):
        folder=setup.SCENES['survival_farm']
        plan=setup.read_json(folder / 'stages_build.json')
        stage={s['id']:s for s in plan['stages']}
        shutters=[a for name in ('phase01','phase02')
                  for a in stage[name]['actions'] if a['op']=='barricade']
        self.assertEqual(len(shutters),12)
        self.assertEqual(len({tuple(a['at']) for a in shutters}),12)
        self.assertTrue(all(a.get('side')=='outside' and a['face'] in ('N','W')
                         and 1<=a['planks']<=2 for a in shutters))
        self.assertEqual([
            sum(a.get('kind')=='bed' for a in stage[f'phase{i:02d}']['actions'])
            for i in range(1,5)],[0,0,2,2])
        for i,expected in ((2,2),(3,1),(4,3)):
            data=setup.read_json(folder / f'phase{i:02d}_bedding_batch.json')
            self.assertEqual(sum(c['count'] for g in data['actions']
                for c in g['changes'] if c['item'].startswith('Base.SleepingBag_')),expected)
        for i in (1,2):
            for path in folder.glob(f'phase{i:02d}*_batch.json'):
                for group in setup.read_json(path)['actions']:
                    self.assertGreater(group['at'][1],7743,
                                       'Stages I and II may not stock distant north sheds')
        for s in plan['stages']:
            for a in s['actions']:
                if a.get('op')=='place':
                    self.assertLess(a['at'][1],7789,
                                    'No new building in the southern depression')

    def test_scene_preserves_verified_quantities_and_has_no_old_world_binding(self):
        folder = setup.SCENES['survival_farm']
        self.assertEqual(len(list(folder.glob('*.json'))), 12)
        counts = []; fluids = {}
        for n in range(1, 5):
            total = 0
            for p in folder.glob(f'phase{n:02d}*_batch.json'):
                doc = setup.read_json(p)
                self.assertEqual(doc['world'], 'camp_template')
                for group in doc['actions']:
                    for c in group['changes']:
                        self.assertEqual(c['op'], 'add')
                        total += c['count']
                        if 'fluid' in c:
                            fluids[c['fluid']] = fluids.get(c['fluid'], 0) + c['count'] * c['amount_l']
            counts.append(total)
        self.assertEqual(counts, [137, 194, 308, 469])
        self.assertEqual(fluids, {'Water': 34, 'Petrol': 20})
        plan = setup.read_json(folder / 'stages_build.json')
        for stage in plan['stages']:
            for a in stage['actions']:
                if a.get('kind') == 'wall':
                    self.assertEqual(a['sprite'], 'carpentry_02_81' if a['face'] == 'N' else 'carpentry_02_80')


if __name__ == '__main__':
    unittest.main()
