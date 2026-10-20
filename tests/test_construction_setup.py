#!/usr/bin/env python3
"""Existing file protocols in a temporary world, not actual PZ gameplay."""
from __future__ import annotations
import argparse
import contextlib
import copy
import hashlib
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

PLAN = {'schema': 1, 'world': 'origin', 'settlement': 'refuge', 'stages': [
    {'id': 'one', 'actions': [{'id': 'crate', 'op': 'place', 'kind': 'storage',
        'at': [100, 200, 0], 'sprite': 'carpentry_02_15', 'capacity': 60}]},
    {'id': 'two', 'requires': ['one'], 'actions': [{'id': 'crate', 'op': 'place',
        'kind': 'storage', 'at': [101, 200, 0], 'sprite': 'carpentry_02_15', 'capacity': 60}]}]}


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.world = self.root / 'worlds' / 'copy'
        self.lua = self.world / 'data' / 'Lua'
        self.lua.mkdir(parents=True)
        (self.world / 'profile').write_text('test')
        self.plan = self.root / 'plan.json'
        self.plan.write_text(json.dumps(PLAN))
        self.batches = []
        for stage, x in [('one', 100), ('two', 101)]:
            files = []
            for item, count in [('Base.Plank', 2), ('Base.WaterBottleEmpty', 1)]:
                doc = {'schema': 1, 'world': 'origin', 'actions': [{
                    'target': 'container', 'at': [x, 200, 0],
                    'construction_tag': f'refuge:{stage}:crate',
                    'container_index': 0, 'container_type': 'crate',
                    'changes': [{'op': 'add', 'item': item, 'count': count}]}]}
                if item == 'Base.WaterBottleEmpty':
                    doc['actions'][0]['changes'][0].update(fluid='Water', amount_l=0.5)
                filename = self.root / f'{stage}-{item}.json'
                filename.write_text(json.dumps(doc))
                files.append(str(filename))
            self.batches.append(files)
        self.survey = self.root / 'pre.json'
        self.snapshot = {'world': 'copy', 'summary': {'status': 'complete', 'errors': 0,
            'truncated': False}, 'records': [
            {'kind': 'square', 'x': 100, 'y': 200, 'z': 0, 'loaded': True},
            {'kind': 'square', 'x': 101, 'y': 200, 'z': 0, 'loaded': True}]}
        self.survey.write_text(json.dumps(self.snapshot))
        backup_dir = self.root / 'backups' / 'worlds' / 'copy'
        backup_dir.mkdir(parents=True)
        self.backup = backup_dir / 'world-baseline.tar.gz'
        self.backup.write_bytes(b'fake backup for checksum test only')
        sha = hashlib.sha256(self.backup.read_bytes()).hexdigest()
        Path(str(self.backup) + '.sha256').write_text(f'{sha}  {self.backup.name}\n')
        for module in (setup.scanctl, setup.livectl):
            self.enterContext(patch.object(module, 'STORE', self.root))
        self.ready = self.enterContext(patch.object(setup.scanctl, 'assert_module_ready'))
        self.enterContext(patch.object(setup.os, 'geteuid', return_value=0))
        self.clock, self.events, self.ids = 0.0, [], set()
        self.delay, self.error, self.bad_counts = set(), set(), set()
        self.enterContext(patch.object(setup.time, 'monotonic', side_effect=lambda: self.clock))
        self.enterContext(patch.object(setup.time, 'sleep', side_effect=self.server_tick))

    def args(self, *, yes=False, stage='one', **kwargs):
        args = argparse.Namespace(command='setup', world='copy', source_world='origin',
            file=str(self.plan), stage=stage, batch=self.batches[0 if stage == 'one' else 1],
            survey=str(self.survey), backup=str(self.backup), yes=yes, status=False,
            resume=False, timeout=1, allow_existing=False)
        for name, value in kwargs.items():
            setattr(args, name, value)
        return args

    def run_setup(self, args):
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            setup.run(args)
        return stream.getvalue()

    def state_file(self, stage='one'):
        return self.world / 'story' / 'setup' / 'refuge' / stage / 'receipt.json'

    def state(self, stage='one'):
        return json.loads(self.state_file(stage).read_text())

    def server_tick(self, seconds):
        self.clock += seconds
        for kind, module in [('build', setup.build), ('stock', setup.batch)]:
            wanted = module.previous('copy')
            if not wanted or wanted['id'] in self.ids or kind in self.delay:
                continue
            self.ids.add(wanted['id'])
            self.events.append(kind)
            count = wanted['count']
            status = 'error' if kind in self.error else 'complete'
            applied = 0 if status == 'error' or kind in self.bad_counts else count
            reason = 'preflight_failed' if status == 'error' else 'server_applied'
            if kind == 'build':
                row = ['v1', wanted['id'], 'copy', wanted['settlement'], wanted['stage'],
                       wanted['digest'], status, str(applied), str(count), reason]
                if status == 'complete' and applied == count:
                    with (self.lua / 'SiegerAdminConstructionStages.txt').open('a') as f:
                        f.write(f'{wanted["settlement"]}\t{wanted["stage"]}\t{wanted["digest"]}\n')
            else:
                row = ['v1', wanted['id'], 'copy', wanted['hash'], status,
                       str(applied), str(count), reason]
            module.paths('copy')[1].write_text('\t'.join(row) + '\n')

    def test_preview_no_world_docker_journal_or_request_writes(self):
        before = sorted(p.relative_to(self.root) for p in self.root.rglob('*'))
        out = self.run_setup(self.args())
        self.assertIn('PREVIEW ONLY', out)
        self.assertIn('"supply_actions": 2', out)
        self.ready.assert_not_called()
        self.assertEqual(before, sorted(p.relative_to(self.root) for p in self.root.rglob('*')))

    def test_apply_combines_supplies_orders_receipts_and_preserves_source_world(self):
        self.run_setup(self.args(yes=True))
        self.assertEqual(self.events, ['build', 'stock'])
        state = self.state()
        self.assertEqual(state['status'], 'server_applied')
        self.assertFalse(state['native_gameplay_accepted'])
        supply = json.loads((self.state_file().parent / 'stock.json').read_text())
        self.assertEqual(len(supply['actions']), 2)
        self.assertEqual(supply['world'], 'copy')
        self.assertEqual(json.loads(self.plan.read_text())['world'], 'origin')
        self.assertEqual(self.state_file().stat().st_mode & 0o777, 0o600)
        before = set(self.ids)
        self.assertIn('ALREADY APPLIED', self.run_setup(self.args(yes=True)))
        self.assertEqual(self.ids, before)

    def test_second_stage_requires_both_first_build_and_stock(self):
        with self.assertRaisesRegex(ValueError, 'prerequisite'):
            self.run_setup(self.args(yes=True, stage='two'))
        self.assertFalse(setup.build.paths('copy')[0].exists())
        self.run_setup(self.args(yes=True))
        self.run_setup(self.args(yes=True, stage='two'))
        self.assertEqual(self.events, ['build', 'stock', 'build', 'stock'])
        self.assertEqual(self.state('two')['status'], 'server_applied')

    def test_supply_error_does_not_repeat_finished_build_or_supplies(self):
        self.error.add('stock')
        with self.assertRaisesRegex(ValueError, 'Native request failed'):
            self.run_setup(self.args(yes=True))
        self.assertEqual(self.state()['steps']['build']['status'], 'complete')
        before = setup.batch.paths('copy')[0].read_text()
        with self.assertRaisesRegex(ValueError, 'Native request failed'):
            self.run_setup(self.args(yes=True, resume=True))
        self.assertEqual(setup.batch.paths('copy')[0].read_text(), before)
        self.assertEqual(self.events, ['build', 'stock'])

    def test_timeout_resume_waits_for_same_request(self):
        self.delay.add('stock')
        with self.assertRaisesRegex(ValueError, 'timeout'):
            self.run_setup(self.args(yes=True))
        before = setup.batch.paths('copy')[0].read_text()
        self.delay.clear()
        self.run_setup(self.args(yes=True, resume=True))
        self.assertEqual(before, setup.batch.paths('copy')[0].read_text())
        self.assertEqual(self.events, ['build', 'stock'])

    def test_interrupted_queue_unknown_id_is_not_reissued(self):
        original = setup.build.preview
        def crashed(args):
            original(args)
            raise OSError('simulated crash after enqueue')
        with patch.object(setup.build, 'preview', side_effect=crashed):
            with self.assertRaises(OSError):
                self.run_setup(self.args(yes=True))
        before = setup.build.paths('copy')[0].read_text()
        with self.assertRaisesRegex(ValueError, 'unknown request ID'):
            self.run_setup(self.args(yes=True, resume=True))
        self.assertEqual(before, setup.build.paths('copy')[0].read_text())
        self.assertFalse(setup.batch.paths('copy')[0].exists())

    def test_preexisting_pending_supply_stops_before_construction(self):
        native = argparse.Namespace(world='copy', file=str(self.root / 'copybatch.json'),
                                    yes=True, acknowledge_failed=False)
        doc = json.loads(Path(self.batches[0][0]).read_text()); doc['world'] = 'copy'
        Path(native.file).write_text(json.dumps(doc))
        with contextlib.redirect_stdout(io.StringIO()):
            setup.batch.execute(native)
        with self.assertRaisesRegex(ValueError, 'pending/failed'):
            self.run_setup(self.args(yes=True))
        self.assertFalse(setup.build.paths('copy')[0].exists())

    def test_failures_are_blocking_and_never_report_full_completion(self):
        self.bad_counts.add('build')
        with self.assertRaisesRegex(ValueError, 'Incomplete counters'):
            self.run_setup(self.args(yes=True))
        self.assertFalse(setup.batch.paths('copy')[0].exists())
        self.assertEqual(self.state()['status'], 'running')

    def test_current_world_and_full_coverage_required(self):
        for mutation in [lambda d: d.update(world='origin'),
                         lambda d: d['records'].pop(0),
                         lambda d: d['records'][0].update(loaded=False),
                         lambda d: d['summary'].update(errors=1)]:
            bad = copy.deepcopy(self.snapshot); mutation(bad)
            self.survey.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                self.run_setup(self.args(yes=True))
            self.assertFalse(setup.build.paths('copy')[0].exists())

    def test_backup_checksum_checked_before_requests(self):
        self.backup.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.run_setup(self.args(yes=True))
        self.assertFalse(setup.build.paths('copy')[0].exists())

    def test_changed_plan_or_corrupt_receipt_cannot_mark_step_done(self):
        self.run_setup(self.args(yes=True))
        state = self.state(); state['steps']['stock']['receipt']['applied'] = 0
        self.state_file().write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, 'Corrupt completed'):
            self.run_setup(self.args(yes=True))
        doc = json.loads(Path(self.batches[0][0]).read_text())
        doc['actions'][0]['changes'][0]['count'] += 1
        Path(self.batches[0][0]).write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            self.run_setup(self.args(yes=True))
        self.assertEqual(self.events, ['build', 'stock'])

    def test_duplicate_inputs_mixed_worlds_and_player_edits_refused(self):
        with self.assertRaisesRegex(ValueError, 'Repeated supply'):
            setup.prepare(self.args(batch=self.batches[0] * 2))
        doc = json.loads(Path(self.batches[0][0]).read_text()); doc['world'] = 'wrong'
        Path(self.batches[0][0]).write_text(json.dumps(doc))
        with self.assertRaises(ValueError):
            setup.prepare(self.args())
        doc = {'schema': 1, 'world': 'origin', 'actions': [{
            'target': 'player', 'username': 'admin',
            'changes': [{'op': 'add', 'item': 'Base.Plank', 'count': 1}]}]}
        Path(self.batches[0][0]).write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, 'additions only'):
            setup.prepare(self.args())

    def test_existing_window_indices_and_barricade_flag_must_be_current(self):
        doc = copy.deepcopy(PLAN)
        doc['stages'][0]['actions'].append({'id': 'window', 'op': 'barricade',
            'kind': 'IsoWindow', 'at': [100, 200, 0], 'index': 2, 'face': 'N',
            'sprite': 'fixtures_windows_01_25', 'planks': 2})
        self.plan.write_text(json.dumps(doc))
        row = {'kind': 'object', 'x': 100, 'y': 200, 'z': 0, 'object_index': 2,
            'class': 'IsoWindow', 'sprite': 'fixtures_windows_01_25', 'face': 'N',
            'window_barricaded_same': False}
        self.snapshot['records'].append(row)
        for update in [{'object_index': 3}, {'window_barricaded_same': True},
                       {'window_barricaded_same': None}]:
            bad = copy.deepcopy(self.snapshot); bad['records'][-1].update(update)
            self.survey.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                self.run_setup(self.args(yes=True, allow_existing=True))
        self.survey.write_text(json.dumps(self.snapshot))
        with self.assertRaisesRegex(ValueError, 'allow-existing'):
            self.run_setup(self.args(yes=True))
        self.run_setup(self.args(yes=True, allow_existing=True))
        self.assertEqual(self.events, ['build', 'stock'])

    def test_missing_survey_backup_resume_and_no_attempt_refused(self):
        for kwargs in [{'survey': None}, {'backup': None}, {'resume': True}]:
            with self.assertRaises(ValueError):
                self.run_setup(self.args(yes=True, **kwargs))
        with self.assertRaisesRegex(ValueError, 'requires --yes'):
            self.run_setup(self.args(resume=True))
        self.assertFalse(setup.build.paths('copy')[0].exists())

    def test_completed_build_ack_without_native_ledger_does_not_ship(self):
        tick = self.server_tick
        def missing_ledger(seconds):
            tick(seconds)
            ledger = self.lua / 'SiegerAdminConstructionStages.txt'
            if ledger.exists():
                ledger.unlink()
        with patch.object(setup.time, 'sleep', side_effect=missing_ledger):
            with self.assertRaisesRegex(ValueError, 'matching native stage ledger'):
                self.run_setup(self.args(yes=True))
        self.assertFalse(setup.batch.paths('copy')[0].exists())

    def test_previous_world_setup_cannot_be_used_as_prerequisite(self):
        self.run_setup(self.args(yes=True))
        state = self.state(); state['identity']['world'] = 'different_world'
        self.state_file().write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, 'Prerequisite setup'):
            self.run_setup(self.args(yes=True, stage='two'))
        self.assertEqual(self.events, ['build', 'stock'])

    def test_native_channel_replacement_is_not_accepted(self):
        self.delay.add('stock')
        with self.assertRaisesRegex(ValueError, 'timeout'):
            self.run_setup(self.args(yes=True))
        req = setup.batch.paths('copy')[0]
        text = req.read_text().split('\t'); text[1] = 'f' * 32
        req.write_text('\t'.join(text))
        with self.assertRaisesRegex(ValueError, 'channel was replaced'):
            self.run_setup(self.args(yes=True, resume=True))
        self.assertEqual(self.events, ['build'])

    def test_leaf_symlink_input_and_journal_are_refused(self):
        alias = self.root / 'alias.json'; alias.symlink_to(self.plan)
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            self.run_setup(self.args(file=str(alias)))
        folder = self.state_file().parent
        folder.mkdir(parents=True)
        self.state_file().symlink_to(self.plan)
        with self.assertRaises(ValueError):
            self.run_setup(self.args(yes=True))
        self.assertFalse(setup.build.paths('copy')[0].exists())

    def test_read_status_does_not_send_or_claim_gameplay(self):
        self.run_setup(self.args(yes=True))
        before = len(self.events)
        output = self.run_setup(self.args(status=True))
        self.assertEqual(json.loads(output)['status'], 'server_applied')
        self.assertFalse(json.loads(output)['native_gameplay_accepted'])
        self.assertEqual(len(self.events), before)

    def test_native_ledger_restore_does_not_allow_silent_repeat(self):
        self.run_setup(self.args(yes=True))
        (self.lua / 'SiegerAdminConstructionStages.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'restored'):
            self.run_setup(self.args(yes=True))
        self.assertEqual(self.events, ['build', 'stock'])


if __name__ == '__main__':
    unittest.main()
