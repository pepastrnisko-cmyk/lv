"""Application orchestration; native Resolve calls live in a separate process."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from .commands import parse_command
from .history import History, CancellationSupervisor
from .kdenlive import KdenliveError, KdenliveProject


def data_directory():
    override = os.environ.get('EDITING_COPILOT_DATA_DIR')
    return Path(override) if override else Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'EditingCopilot' / 'data'


class InstanceLock:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.stream = (directory / 'instance.lock').open('a+b')
        self.stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self.stream.close()
                raise RuntimeError('Editing Copilot is already open. Use the existing window.')
        else:
            import fcntl
            try:
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.stream.close()
                raise RuntimeError('Editing Copilot is already open.')

    def close(self):
        self.stream.close()


class ResolveRPCError(RuntimeError):
    """Preserve worker errors and uncertainty instead of claiming success."""
    def __init__(self, message, code='request_failed', details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _worker_command():
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--resolve-worker']
    return [sys.executable, '-m', 'editing_copilot', '--resolve-worker']


def resolve_rpc(operation, payload=None, cancel=None, timeout=15):
    """A native hang cannot block the Tk window or Stop handler.

    Killing a timed-out worker does not reverse a host mutation. Callers must
    journal unknown outcomes and must not retry them automatically.
    """
    if cancel is not None and cancel.is_set():
        raise ResolveRPCError('Resolve request cancelled before dispatch.', 'cancelled')
    directory = data_directory() / 'rpc'
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='request-', dir=directory) as folder:
        request = Path(folder) / 'request.json'
        response = Path(folder) / 'response.json'
        request.write_text(json.dumps({'operation': operation, 'payload': payload}, allow_nan=False), encoding='utf-8')
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        if cancel is not None and cancel.is_set():
            raise ResolveRPCError('Resolve request cancelled before dispatch.', 'cancelled')
        child = subprocess.Popen(_worker_command() + [str(request), str(response)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=flags)
        started = time.monotonic()
        try:
            while child.poll() is None:
                if (cancel is not None and cancel.is_set()) or time.monotonic() - started > timeout:
                    child.kill()
                    child.wait(timeout=5)
                    raise ResolveRPCError('Resolve request interrupted or timed out. A dispatched edit may have completed; outcome is unknown. Inspect before retrying.', 'outcome_unknown')
                time.sleep(.02)
            if not response.is_file():
                raise ResolveRPCError('Resolve worker did not return a result. The editor may be unavailable; no success is claimed.', 'outcome_unknown')
            if response.stat().st_size > 16 * 1024 * 1024:
                raise ResolveRPCError('Resolve response exceeds the inspection limit.', 'outcome_unknown')
            result = json.loads(response.read_text(encoding='utf-8'))
            if not result.get('ok'):
                raise ResolveRPCError(result.get('error', 'Resolve request failed.'), result.get('code', 'request_failed'), result.get('details'))
            return result['result']
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


def worker_main(request_path, response_path):
    from .resolve import ResolveAdapter
    request_path, response_path = Path(request_path), Path(response_path)
    if request_path.stat().st_size > 1024 * 1024:
        raise ValueError('Request too large.')
    try:
        request = json.loads(request_path.read_text(encoding='utf-8'))
        adapter = ResolveAdapter()
        op, payload = request.get('operation'), request.get('payload')
        if op == 'inspect':
            result = adapter.describe()
        elif op == 'plan':
            result = adapter.plan(payload['operation'], payload['args'])
        elif op == 'apply':
            result = adapter.apply(payload)
        elif op == 'undo':
            result = adapter.undo(payload)
        else:
            raise ValueError('Unsupported worker request.')
        envelope = {'ok': True, 'result': result}
    except Exception as exc:
        envelope = {'ok': False, 'error': str(exc), 'code': getattr(exc, 'code', 'request_failed'),
                    'details': getattr(exc, 'details', {})}
    temporary = response_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(envelope, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    os.replace(temporary, response_path)


class Controller:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else data_directory()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.instance_lock = InstanceLock(self.directory)
        try:
            self.history = History(self.directory / 'history.sqlite3')
        except Exception:
            self.instance_lock.close()
            raise
        self.supervisor = CancellationSupervisor()
        self.editor = 'kdenlive'
        self.path = None
        self.snapshot = None
        self.preview = None
        self._preview_fingerprint = None
        self._mutex = threading.RLock()
        self._closed = False

    def select(self, editor, path=None):
        with self._mutex:
            self.supervisor.stop()
            if editor not in ('kdenlive', 'resolve'):
                raise ValueError('Select Kdenlive or DaVinci Resolve.')
            self.editor = editor
            self.path = Path(path).resolve() if path else None
            self.snapshot = self.preview = None
            self._preview_fingerprint = None

    def inspect(self, lease=None):
        with self._mutex:
            lease = lease or self.supervisor.acquire()
            lease.assert_active()
            if self.editor == 'kdenlive':
                if self.path is None:
                    raise ValueError('Open a saved .kdenlive project first.')
                result = KdenliveProject(self.path).describe()
            else:
                result = resolve_rpc('inspect', cancel=lease.event)
            lease.assert_active()
            self.snapshot = copy.deepcopy(result)
            return copy.deepcopy(result)

    def _key(self):
        if self.editor == 'kdenlive':
            return 'kdenlive:' + os.path.normcase(str(self.path))
        identity = (self.snapshot or {}).get('identity', {})
        return 'resolve:' + json.dumps({'project_id': identity.get('project_id'),
                                       'timeline_id': identity.get('timeline_id')}, sort_keys=True)

    def _unresolved(self, project_key):
        return self.history.unresolved(project_key)

    def plan(self, text, selected_instance=None, lease=None):
        with self._mutex:
            lease = lease or self.supervisor.acquire()
            lease.assert_active()
            self.preview = None
            self._preview_fingerprint = None
            command = parse_command(text)
            if command.operation == 'stop':
                self.stop()
                return {'operation': 'stop', 'summary': 'Further work stopped.'}
            if command.operation in ('inspect', 'list_clips', 'export_report'):
                return {'operation': command.operation, 'snapshot': self.inspect(lease), 'summary': 'Read-only project inspection.'}
            if command.operation == 'undo':
                return {'operation': 'undo', 'summary': 'Undo the last verified assistant edit, after checking for later changes.'}
            self.inspect(lease)
            if self._unresolved(self._key()):
                raise ValueError('This project has an unresolved previous edit. Inspect its recorded plan before further mutations. No automatic retry is allowed.')
            args = dict(command.args)
            if self.editor == 'kdenlive':
                adapter = KdenliveProject(self.path)
                if command.operation in ('add_guide', 'add_marker'):
                    if command.operation == 'add_marker' and re.search(r'\s+color\s+[^\s"]+\s*$', text, re.I):
                        raise ValueError('Kdenlive uses project guide categories. Use add guide; requested Resolve marker colors are unsupported here.')
                    plan = adapter.plan('add_guide', {'frame': args['frame'], 'comment': args['name']})
                elif command.operation in ('split_clip', 'trim_clip'):
                    instance_id = args['clip_id']
                    if instance_id.lower() == 'selected':
                        if not selected_instance:
                            raise ValueError('Select one timeline row in the companion first.')
                        instance_id = selected_instance
                    if command.operation == 'split_clip':
                        plan = adapter.plan('split', {'instance_id': instance_id, 'frame': args['frame']})
                    else:
                        instances = [i for sequence in self.snapshot['sequences'] for track in sequence['tracks']
                                     for playlist in track['playlists'] for i in playlist['instances']]
                        item = next((i for i in instances if i['instance_id'] == instance_id), None)
                        if item is None:
                            raise ValueError('Timeline instance not found; inspect and select its row.')
                        plan = adapter.plan('trim', {'instance_id': instance_id, 'source_in': item['source_in'],
                                                    'source_out_exclusive': item['source_out_exclusive'] + args['delta_frames']})
                else:
                    raise ValueError('This operation is not available for Kdenlive.')
            else:
                if command.operation not in ('add_marker', 'add_guide'):
                    raise ValueError('Resolve core supports inspection and timeline markers. Clip edits and grading are not enabled.')
                plan = resolve_rpc('plan', {'operation': 'add_marker', 'args': args}, cancel=lease.event)
            lease.assert_active()
            preview = {'plan': copy.deepcopy(plan), 'text': text, 'selected_instance': selected_instance,
                       'editor': self.editor, 'path': str(self.path) if self.path else None,
                       'project_key': self._key(), 'generation': lease.generation}
            self._preview_fingerprint = _fingerprint(preview)
            self.preview = preview
            return copy.deepcopy(plan)

    def apply(self, lease=None, output=None, expected_text=None, selected_instance=None):
        with self._mutex:
            lease = lease or self.supervisor.acquire()
            lease.assert_active()
            preview = copy.deepcopy(self.preview)
            if preview is None or preview['editor'] != self.editor or preview['generation'] != lease.generation:
                raise ValueError('Generate a fresh preview after Stop or a project change.')
            if _fingerprint(preview) != self._preview_fingerprint:
                raise ValueError('The preview was modified. Generate a fresh preview before applying.')
            if expected_text is not None and preview['text'] != expected_text:
                raise ValueError('Command changed after preview. Generate a fresh preview.')
            if selected_instance is not None and preview['selected_instance'] != selected_instance:
                raise ValueError('Timeline selection changed after preview. Generate a fresh preview.')
            if preview['path'] != (str(self.path) if self.path else None):
                raise ValueError('Project changed after preview.')
            if self._unresolved(preview['project_key']):
                raise ValueError('This project has an unresolved edit. Inspect its recorded outcome before further mutations.')
            journal_id = self.history.record(preview['plan']['operation'], project_hash=preview['project_key'], payload=preview)
            self.history.mark(journal_id, 'pending')
            dispatched = False
            output_path = None
            output_preexisting = False
            try:
                lease.assert_active()
                if self.editor == 'kdenlive':
                    if output is None:
                        folder = self.path.parent / 'Copilot Copies'
                        lease.assert_active()
                        folder.mkdir(exist_ok=True)
                        output = folder / (self.path.stem + '-copilot-' + uuid.uuid4().hex[:10] + '.kdenlive')
                    output_path = Path(output).expanduser().resolve()
                    output_preexisting = output_path.exists()
                    adapter = KdenliveProject(self.path)
                    lease.assert_active()
                    dispatched = True
                    result = adapter.apply(preview['plan'], output_path, lease.event)
                    if not isinstance(result, dict) or result.get('status') != 'completed' or result.get('verification') != 'structural_readback_passed':
                        raise RuntimeError('Kdenlive did not return a verified completed project copy.')
                    if (Path(result.get('output', '')).resolve() != output_path
                            or result.get('source_sha256') != preview['plan'].get('source_sha256')
                            or not output_path.is_file()
                            or hashlib.sha256(output_path.read_bytes()).hexdigest() != result.get('output_sha256')):
                        raise RuntimeError('Kdenlive project-copy identity or fingerprint readback failed; outcome is unknown.')
                    result['previous_path'] = str(self.path)
                    self.path = Path(result['output'])
                else:
                    lease.assert_active()
                    dispatched = True
                    result = resolve_rpc('apply', preview['plan'], cancel=lease.event)
                    if not isinstance(result, dict) or result.get('status') != 'applied' or result.get('editor') != 'resolve':
                        raise RuntimeError('Resolve did not return a verified marker transaction; outcome is unknown.')
                    if any(result.get(field) != preview['plan'].get(field) for field in ('identity', 'frame', 'marker')):
                        raise RuntimeError('Resolve returned a different marker transaction; outcome is unknown.')
                if lease.event.is_set():
                    result['stopped_after_apply'] = True
                self.history.mark(journal_id, 'applied', result)
                self.history.mark(journal_id, 'verified', result)
                self.preview = None
                self._preview_fingerprint = None
                self.snapshot = None
                return {'journal_id': journal_id, **result}
            except Exception as exc:
                # An offline adapter error with no newly published file is
                # proven safe to abandon. Resolve timeouts remain uncertain.
                no_publication = (self.editor == 'kdenlive' and isinstance(exc, KdenliveError)
                                  and output_path is not None and (output_preexisting or not output_path.exists()))
                known_resolve_rejection = (self.editor == 'resolve' and isinstance(exc, ResolveRPCError)
                                           and exc.code in {'cancelled', 'not_installed', 'connection_unavailable',
                                                           'no_project', 'no_timeline', 'invalid_argument', 'invalid_plan',
                                                           'identity_unavailable', 'stale_plan', 'editor_busy',
                                                           'state_unavailable', 'out_of_range', 'marker_conflict'})
                status = 'cancelled' if not dispatched or no_publication or known_resolve_rejection else 'unknown'
                self.history.mark(journal_id, status, {'error': str(exc), 'plan': preview['plan'],
                                                      'output': str(output_path) if output_path else None,
                                                      'code': getattr(exc, 'code', None)})
                self.preview = None
                self._preview_fingerprint = None
                raise

    def undo(self, lease=None):
        with self._mutex:
            lease = lease or self.supervisor.acquire()
            lease.assert_active()
            if self.editor == 'kdenlive' and self._unresolved(self._key()):
                raise ValueError('This project has an unresolved edit. Inspect its outcome before selecting an earlier saved project.')
            # Kdenlive copy records bind to their source; current path is output.
            if self.editor == 'kdenlive':
                item = self.history.find_verified_output(str(self.path))
            else:
                self.inspect(lease)
                item = self.history.last_verified(self._key())
            if not item:
                raise ValueError('No matching verified assistant edit to undo.')
            if self.editor == 'kdenlive':
                result = item['result']
                if hashlib.sha256(self.path.read_bytes()).hexdigest() != result['output_sha256']:
                    raise ValueError('The project copy was changed after the edit. Undo would conflict with later work.')
                previous = Path(result['previous_path'])
                if hashlib.sha256(previous.read_bytes()).hexdigest() != result['source_sha256']:
                    raise ValueError('The previous saved project changed; automatic restoration is blocked.')
                lease.assert_active()
                self.path = previous
                undone = {'status': 'undone', 'path': str(previous), 'editor_restored': False,
                          'summary': 'Previous saved project selected in the companion. Open it in Kdenlive to restore. Both copies are retained.'}
            else:
                lease.assert_active()
                try:
                    undone = resolve_rpc('undo', item['result'], cancel=lease.event)
                    if not isinstance(undone, dict) or undone.get('status') != 'undone' or undone.get('editor') != 'resolve':
                        raise RuntimeError('Resolve did not verify marker removal; outcome is unknown.')
                except Exception as exc:
                    # The undo may have removed the marker before a timeout.
                    # Never leave its original record eligible for blind undo.
                    if not isinstance(exc, ResolveRPCError) or exc.code not in {'cancelled', 'undo_conflict', 'stale_plan', 'editor_busy', 'no_project', 'no_timeline'}:
                        self.history.mark(item['id'], 'unknown', {'error': str(exc), 'undo_attempt': True,
                                                                'previous_result': item['result']})
                    raise
            self.history.mark(item['id'], 'undone', item['result'])
            self.preview = self.snapshot = None
            self._preview_fingerprint = None
            return undone

    def stop(self):
        # Deliberately no controller mutex: Stop must not wait for a host call.
        self.supervisor.stop()
        self.preview = None
        self._preview_fingerprint = None

    def close(self):
        self.stop()
        with self._mutex:
            if not self._closed:
                self.history.close()
                self.instance_lock.close()
                self._closed = True
