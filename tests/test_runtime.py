"""Controller safety, durable recovery, and bounded worker orchestration."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from editing_copilot.history import CancelledOperation
from editing_copilot.kdenlive import KdenliveError, KdenliveProject
from editing_copilot.runtime import Controller, InstanceLock, ResolveRPCError, resolve_rpc, worker_main

FIXTURE = Path(__file__).parent / 'fixtures' / 'simple.kdenlive'


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder / 'source.kdenlive'
        self.source.write_bytes(FIXTURE.read_bytes())
        self.data = self.folder / 'data'
        self.controller = Controller(self.data)
        self.addCleanup(self.controller.close)
        self.controller.select('kdenlive', self.source)
        snapshot = self.controller.inspect()
        self.instance = snapshot['sequences'][0]['tracks'][0]['playlists'][0]['instances'][0]['instance_id']
        self.second = snapshot['sequences'][0]['tracks'][0]['playlists'][0]['instances'][1]['instance_id']

    def proposal(self):
        return self.controller.plan('add guide at frame 12 named "Review"')

    def edit(self):
        self.proposal()
        return self.controller.apply(output=self.folder / 'edited.kdenlive')

    def test_inspect_is_readonly_and_snapshot_isolated(self):
        before = self.source.read_bytes()
        result = self.controller.inspect()
        result['sequences'].clear()
        self.assertEqual(len(self.controller.snapshot['sequences']), 1)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(self.controller.history.list_recent(), [])

    def test_selected_trim_uses_nested_instances(self):
        plan = self.controller.plan('trim clip selected end by 10 frames', self.instance)
        self.assertEqual(plan['operation'], 'trim')
        self.assertEqual(plan['args'], {'instance_id': self.instance, 'source_in': 10, 'source_out_exclusive': 50})
        result = self.controller.apply(output=self.folder / 'trim.kdenlive', selected_instance=self.instance)
        self.assertEqual(result['status'], 'completed')

    def test_selected_split_exact_frames(self):
        plan = self.controller.plan('split clip selected at frame 30', self.instance)
        self.assertEqual(plan['args'], {'instance_id': self.instance, 'frame': 30})
        result = self.controller.apply(output=self.folder / 'split.kdenlive')
        self.assertEqual(result['verification'], 'structural_readback_passed')

    def test_kdenlive_explicit_resolve_marker_color_not_silently_ignored(self):
        for color in ('Green', 'Red'):
            with self.subTest(color=color):
                with self.assertRaisesRegex(ValueError, 'categories'):
                    self.controller.plan('add marker at frame 12 named "Review" color ' + color)
        # A quoted label containing the words is still a literal label.
        plan = self.controller.plan('add marker at frame 12 named "Scene color Green"')
        self.assertEqual(plan['args']['comment'], 'Scene color Green')

    def test_plan_required_for_apply(self):
        with self.assertRaisesRegex(ValueError, 'fresh preview'):
            self.controller.apply(output=self.folder / 'no.kdenlive')
        self.assertEqual(self.controller.history.list_recent(), [])

    def test_plan_and_apply_persist_verified_history(self):
        before = self.source.read_bytes()
        result = self.edit()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(self.controller.path, Path(result['output']))
        record = self.controller.history.get(result['journal_id'])
        self.assertEqual(record['status'], 'verified')
        self.assertEqual(record['payload']['generation'], self.controller.supervisor.generation)
        self.assertEqual(record['result']['previous_path'], str(self.source))
        self.assertIsNone(self.controller.preview)
        with self.assertRaises(ValueError):
            self.controller.apply(output=self.folder / 'second.kdenlive')

    def test_copy_undo_selects_saved_source_without_editor_claim(self):
        result = self.edit()
        output = Path(result['output'])
        undone = self.controller.undo()
        self.assertEqual(undone['status'], 'undone')
        self.assertFalse(undone['editor_restored'])
        self.assertEqual(self.controller.path, self.source)
        self.assertTrue(output.is_file())
        self.assertTrue(self.source.is_file())
        self.assertEqual(self.controller.history.get(result['journal_id'])['status'], 'undone')

    def test_undo_output_conflict_rejected(self):
        result = self.edit()
        Path(result['output']).write_bytes(Path(result['output']).read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'later work'):
            self.controller.undo()
        self.assertEqual(self.controller.history.get(result['journal_id'])['status'], 'verified')

    def test_undo_source_conflict_rejected(self):
        result = self.edit()
        self.source.write_bytes(self.source.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'previous saved project changed'):
            self.controller.undo()
        self.assertEqual(self.controller.history.get(result['journal_id'])['status'], 'verified')

    def test_history_survives_restart_and_can_undo_copy(self):
        result = self.edit()
        self.controller.close()
        reopened = Controller(self.data)
        self.addCleanup(reopened.close)
        reopened.select('kdenlive', result['output'])
        self.assertEqual(reopened.history.get(result['journal_id'])['status'], 'verified')
        self.assertEqual(reopened.undo()['path'], str(self.source))

    def test_pending_history_recovers_unknown_and_blocks_same_project(self):
        record = self.controller.history.record('add_guide', project_hash=self.controller._key(), status='pending')
        self.controller.close()
        reopened = Controller(self.data)
        self.addCleanup(reopened.close)
        reopened.select('kdenlive', self.source)
        self.assertEqual(reopened.history.get(record)['status'], 'unknown')
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            reopened.plan('add guide at frame 20 named "New"')

    def test_old_unknown_barrier_does_not_expire_with_recent_rows(self):
        record = self.controller.history.record('old edit', project_hash=self.controller._key(), status='unknown')
        for _ in range(105):
            self.controller.history.record('inspection', project_hash='different-project', status='cancelled')
        self.assertNotIn(record, [r['id'] for r in self.controller.history.list_recent(100)])
        self.assertEqual(self.controller.history.unresolved(self.controller._key())[0]['id'], record)
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            self.proposal()

    def test_old_verified_copy_undo_does_not_expire(self):
        result = self.edit()
        for _ in range(105):
            self.controller.history.record('inspection', project_hash='different-project', status='cancelled')
        self.assertEqual(self.controller.history.find_verified_output(result['output'])['id'], result['journal_id'])
        self.assertEqual(self.controller.undo()['path'], str(self.source))

    def test_stop_revokes_captured_lease_and_preview(self):
        lease = self.controller.supervisor.capture()
        self.proposal()
        self.controller.stop()
        with self.assertRaises(CancelledOperation):
            self.controller.apply(lease, output=self.folder / 'stopped.kdenlive')
        with self.assertRaisesRegex(ValueError, 'fresh preview'):
            self.controller.apply(output=self.folder / 'stopped.kdenlive')
        self.assertFalse((self.folder / 'stopped.kdenlive').exists())
        self.assertIsNone(self.controller.preview)

    def test_stop_during_adapter_dispatch_leaves_cancelled_no_output(self):
        self.proposal()
        original = KdenliveProject.apply
        def interrupted(adapter, plan, output, cancel):
            self.controller.stop()
            return original(adapter, plan, output, cancel)
        with patch('editing_copilot.runtime.KdenliveProject.apply', interrupted):
            with self.assertRaisesRegex(KdenliveError, 'cancelled'):
                self.controller.apply(output=self.folder / 'stopped.kdenlive')
        self.assertEqual(self.controller.history.list_recent()[0]['status'], 'cancelled')
        self.assertFalse((self.folder / 'stopped.kdenlive').exists())

    def test_stop_after_publication_records_known_success(self):
        self.proposal()
        original = KdenliveProject.apply
        def stopped_after(adapter, plan, output, cancel):
            result = original(adapter, plan, output, cancel)
            self.controller.stop()
            return result
        with patch('editing_copilot.runtime.KdenliveProject.apply', stopped_after):
            result = self.controller.apply(output=self.folder / 'completed.kdenlive')
        self.assertTrue(result['stopped_after_apply'])
        self.assertEqual(self.controller.history.get(result['journal_id'])['status'], 'verified')

    def test_stop_is_nonblocking_while_adapter_holds_controller_mutex(self):
        self.proposal()
        entered, release = threading.Event(), threading.Event()
        errors = []
        def blocked(adapter, plan, output, cancel):
            entered.set()
            release.wait(2)
            if cancel.is_set():
                raise KdenliveError('Operation cancelled before publication.')
            raise AssertionError('Stop event was not signalled.')
        def run():
            try:
                self.controller.apply(output=self.folder / 'no.kdenlive')
            except Exception as exc:
                errors.append(exc)
        with patch('editing_copilot.runtime.KdenliveProject.apply', blocked):
            worker = threading.Thread(target=run)
            worker.start()
            self.assertTrue(entered.wait(1))
            self.controller.stop()
            self.assertFalse(release.is_set())
            release.set()
            worker.join(2)
            self.assertFalse(worker.is_alive())
        self.assertIsInstance(errors[0], KdenliveError)

    def test_tampered_internal_preview_rejected(self):
        self.proposal()
        self.controller.preview['plan']['args']['frame'] = 20
        with self.assertRaisesRegex(ValueError, 'modified'):
            self.controller.apply(output=self.folder / 'no.kdenlive')
        self.assertEqual(self.controller.history.list_recent(), [])

    def test_returned_plan_is_isolated_from_active_preview(self):
        plan = self.proposal()
        plan['args']['frame'] = 20
        self.assertEqual(self.controller.preview['plan']['args']['frame'], 12)

    def test_changed_command_or_target_requires_new_preview(self):
        self.controller.plan('split clip selected at frame 30', self.instance)
        with self.assertRaisesRegex(ValueError, 'Command changed'):
            self.controller.apply(output=self.folder / 'no.kdenlive', expected_text='split clip selected at frame 35')
        with self.assertRaisesRegex(ValueError, 'selection changed'):
            self.controller.apply(output=self.folder / 'no.kdenlive', selected_instance=self.second)
        self.assertEqual(self.controller.history.list_recent(), [])

    def test_new_invalid_command_clears_previous_preview(self):
        self.proposal()
        with self.assertRaises(ValueError):
            self.controller.plan('make it dramatic')
        self.assertIsNone(self.controller.preview)
        with self.assertRaises(ValueError):
            self.controller.apply(output=self.folder / 'no.kdenlive')

    def test_project_selection_invalidates_preview(self):
        self.proposal()
        self.controller.select('kdenlive', self.source)
        with self.assertRaisesRegex(ValueError, 'fresh preview'):
            self.controller.apply(output=self.folder / 'no.kdenlive')

    def test_changed_source_is_cancelled_without_publication(self):
        self.proposal()
        self.source.write_bytes(self.source.read_bytes() + b'\n')
        with self.assertRaises(KdenliveError):
            self.controller.apply(output=self.folder / 'conflict.kdenlive')
        self.assertEqual(self.controller.history.list_recent()[0]['status'], 'cancelled')
        self.assertFalse((self.folder / 'conflict.kdenlive').exists())

    def test_unverified_adapter_result_is_unknown(self):
        self.proposal()
        with patch('editing_copilot.runtime.KdenliveProject.apply', return_value={'status': 'completed'}):
            with self.assertRaisesRegex(RuntimeError, 'verified'):
                self.controller.apply(output=self.folder / 'unknown.kdenlive')
        self.assertEqual(self.controller.history.list_recent()[0]['status'], 'unknown')

    def test_existing_output_not_overwritten_and_not_unknown(self):
        self.proposal()
        output = self.folder / 'existing.kdenlive'
        output.write_bytes(b'existing data')
        with self.assertRaises(KdenliveError):
            self.controller.apply(output=output)
        self.assertEqual(output.read_bytes(), b'existing data')
        self.assertEqual(self.controller.history.list_recent()[0]['status'], 'cancelled')

    def test_instance_lock_rejects_duplicate_data_directory(self):
        with self.assertRaisesRegex(RuntimeError, 'already open'):
            Controller(self.data)
        independent = Controller(self.folder / 'different-data')
        self.addCleanup(independent.close)
        self.assertNotEqual(independent.directory, self.controller.directory)

    def test_instance_lock_rejects_other_process(self):
        code = 'from editing_copilot.runtime import InstanceLock; import sys; lock=InstanceLock(sys.argv[1])'
        result = subprocess.run([sys.executable, '-c', code, str(self.data)], capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'already open', result.stderr)

    def test_lock_released_after_close(self):
        self.controller.close()
        self.controller.close()
        lock = InstanceLock(self.data)
        lock.close()

    def resolve_setup(self):
        self.controller.select('resolve')
        identity = {'project_id': 'project-A', 'timeline_id': 'timeline-A', 'project_name': 'Project',
                    'timeline_name': 'Timeline', 'start_frame': 0, 'end_frame': 100}
        marker = {'name': 'Review', 'note': '', 'color': 'Green', 'duration': 1, 'customData': 'owned'}
        plan = {'editor': 'resolve', 'operation': 'add_marker', 'identity': identity,
                'frame': 12, 'marker': marker, 'summary': 'Add review marker'}
        def rpc(operation, payload=None, **kwargs):
            if operation == 'inspect':
                return {'editor': 'resolve', 'identity': copy.deepcopy(identity)}
            if operation == 'plan':
                return copy.deepcopy(plan)
            if operation == 'apply':
                return {'status': 'applied', **copy.deepcopy(plan)}
            if operation == 'undo':
                return {'status': 'undone', 'editor': 'resolve'}
            raise AssertionError(operation)
        return identity, plan, rpc

    def test_resolve_verified_apply_and_undo(self):
        _, _, rpc = self.resolve_setup()
        with patch('editing_copilot.runtime.resolve_rpc', rpc):
            self.controller.plan('add marker at frame 12 named "Review"')
            result = self.controller.apply()
            self.assertEqual(self.controller.history.get(result['journal_id'])['status'], 'verified')
            self.assertEqual(self.controller.undo()['status'], 'undone')
            self.assertEqual(self.controller.history.get(result['journal_id'])['status'], 'undone')

    def test_resolve_timeout_stays_unknown_and_names_cannot_bypass_barrier(self):
        identity, _, rpc = self.resolve_setup()
        def interrupted(operation, payload=None, **kwargs):
            if operation == 'apply':
                raise ResolveRPCError('timed out', 'outcome_unknown')
            return rpc(operation, payload, **kwargs)
        with patch('editing_copilot.runtime.resolve_rpc', interrupted):
            self.controller.plan('add marker at frame 12 named "Review"')
            with self.assertRaises(ResolveRPCError):
                self.controller.apply()
            self.assertEqual(self.controller.history.list_recent()[0]['status'], 'unknown')
            identity['timeline_name'] = 'Renamed'
            identity['end_frame'] = 200
            with self.assertRaisesRegex(ValueError, 'unresolved'):
                self.controller.plan('add marker at frame 20 named "Other"')

    def test_resolve_known_rejection_is_cancelled(self):
        _, _, rpc = self.resolve_setup()
        def rejected(operation, payload=None, **kwargs):
            if operation == 'apply':
                raise ResolveRPCError('Marker changed', 'stale_plan')
            return rpc(operation, payload, **kwargs)
        with patch('editing_copilot.runtime.resolve_rpc', rejected):
            self.controller.plan('add marker at frame 12 named "Review"')
            with self.assertRaises(ResolveRPCError):
                self.controller.apply()
            self.assertEqual(self.controller.history.list_recent()[0]['status'], 'cancelled')

    def test_resolve_wrong_success_transaction_is_unknown(self):
        _, plan, rpc = self.resolve_setup()
        def wrong(operation, payload=None, **kwargs):
            if operation == 'apply':
                return {'status': 'applied', **copy.deepcopy(plan), 'frame': 13}
            return rpc(operation, payload, **kwargs)
        with patch('editing_copilot.runtime.resolve_rpc', wrong):
            self.controller.plan('add marker at frame 12 named "Review"')
            with self.assertRaisesRegex(RuntimeError, 'different marker'):
                self.controller.apply()
            self.assertEqual(self.controller.history.list_recent()[0]['status'], 'unknown')

    def test_resolve_undo_timeout_is_unknown_without_retry(self):
        _, _, rpc = self.resolve_setup()
        def timeout(operation, payload=None, **kwargs):
            if operation == 'undo':
                raise ResolveRPCError('timed out after dispatch', 'outcome_unknown')
            return rpc(operation, payload, **kwargs)
        with patch('editing_copilot.runtime.resolve_rpc', timeout):
            self.controller.plan('add marker at frame 12 named "Review"')
            result = self.controller.apply()
            with self.assertRaises(ResolveRPCError):
                self.controller.undo()
            self.assertEqual(self.controller.history.get(result['journal_id'])['status'], 'unknown')
            with self.assertRaises(ValueError):
                self.controller.undo()


class WorkerOrchestrationTests(unittest.TestCase):
    def test_cancel_before_launch_does_not_spawn(self):
        cancel = threading.Event()
        cancel.set()
        with patch('editing_copilot.runtime.subprocess.Popen') as spawn:
            with self.assertRaises(ResolveRPCError) as caught:
                resolve_rpc('apply', {}, cancel=cancel)
        self.assertEqual(caught.exception.code, 'cancelled')
        spawn.assert_not_called()

    def test_hung_worker_is_terminated_and_unknown(self):
        class Child:
            killed = False
            def poll(self):
                return -1 if self.killed else None
            def kill(self):
                self.killed = True
            def wait(self, timeout):
                return -1
        child = Child()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'EDITING_COPILOT_DATA_DIR': folder}), patch('editing_copilot.runtime.subprocess.Popen', return_value=child):
            with self.assertRaises(ResolveRPCError) as caught:
                resolve_rpc('apply', {}, timeout=0)
        self.assertTrue(child.killed)
        self.assertEqual(caught.exception.code, 'outcome_unknown')

    def test_worker_error_preserves_code_and_details(self):
        class Child:
            def poll(self):
                return 0
        def spawn(command, **kwargs):
            Path(command[-1]).write_text(json.dumps({'ok': False, 'error': 'readback failed', 'code': 'verification_failed',
                                                   'details': {'transaction': {'frame': 12}}}), encoding='utf-8')
            return Child()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'EDITING_COPILOT_DATA_DIR': folder}), patch('editing_copilot.runtime.subprocess.Popen', side_effect=spawn):
            with self.assertRaises(ResolveRPCError) as caught:
                resolve_rpc('apply', {})
        self.assertEqual(caught.exception.code, 'verification_failed')
        self.assertEqual(caught.exception.details['transaction']['frame'], 12)

    def test_worker_main_isolates_native_adapter_and_writes_response(self):
        with tempfile.TemporaryDirectory() as folder:
            request, response = Path(folder) / 'request.json', Path(folder) / 'response.json'
            request.write_text(json.dumps({'operation': 'inspect', 'payload': None}), encoding='utf-8')
            with patch('editing_copilot.resolve.ResolveAdapter') as adapter:
                adapter.return_value.describe.return_value = {'editor': 'resolve', 'connected': True}
                worker_main(request, response)
            envelope = json.loads(response.read_text(encoding='utf-8'))
            self.assertTrue(envelope['ok'])
            self.assertTrue(envelope['result']['connected'])
            self.assertFalse(response.with_suffix('.tmp').exists())


if __name__ == '__main__':
    unittest.main()
