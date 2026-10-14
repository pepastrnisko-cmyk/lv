"""Redacted environment and a bounded portable release smoke test."""
from pathlib import Path
import hashlib
import platform
import tempfile
import time
from . import __version__
from .commands import parse_command, UnsupportedCommand
from .history import History, CancellationSupervisor
from .kdenlive import KdenliveProject


def environment():
    from .windows import voice_available
    voice_ok, voice_message = voice_available()
    return {'version': __version__, 'os': platform.platform(), 'architecture': platform.machine(),
            'kdenlive_installed': Path(r'C:\Program Files\Kdenlive\bin\kdenlive.exe').is_file(),
            'resolve_installed': Path(r'C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe').is_file(),
            'offline_dictation_available': voice_ok, 'dictation_status': voice_message,
            'network_services': False, 'cloud_models': False,
            'enabled_scope': ['saved Kdenlive inspection/copies/guides/simple trim/split',
                              'Resolve inspection/owned markers when scripting available'],
            'unsupported': ['autonomous grading', 'AI masks/restoration', 'Microsoft 365 bridge',
                            'arbitrary UI control', 'general LLM commands'],
            'signing': 'unsigned local build'}


def self_test(resources):
    checks = []
    started = time.monotonic()
    def check(name, fn):
        try:
            fn()
            checks.append({'name': name, 'status': 'pass'})
        except Exception as exc:
            checks.append({'name': name, 'status': 'fail', 'error': str(exc)})
    def command_test():
        assert parse_command('add marker at frame 12 named "Scene A"').args['name'] == 'Scene A'
        try:
            parse_command('delete all source media')
        except UnsupportedCommand:
            pass
        else:
            raise AssertionError('Unsafe command accepted.')
    def cancellation_test():
        supervisor = CancellationSupervisor()
        queued = supervisor.acquire()
        supervisor.stop()
        assert not queued.is_active() and supervisor.acquire().is_active()
    check('command interpretation and rejection', command_test)
    check('cancellation invalidates queued work', cancellation_test)
    with tempfile.TemporaryDirectory(prefix='editing-copilot-selftest-') as folder:
        folder = Path(folder)
        def journal_test():
            history = History(folder/'journal.sqlite3')
            row = history.record('test', project_hash='sample')
            history.mark(row, 'pending')
            history.close()
            history = History(folder/'journal.sqlite3')
            assert history.get(row)['status'] == 'unknown'
            history.close()
        def project_test():
            source = Path(resources)/'demo.kdenlive'
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            adapter = KdenliveProject(source)
            plan = adapter.plan('add_guide', {'frame': 25, 'comment': 'Self-test'})
            result = adapter.apply(plan, folder/'derived.kdenlive')
            assert result['source_unchanged']
            assert hashlib.sha256(source.read_bytes()).hexdigest() == before
            assert Path(result['output']).is_file()
        check('durable interrupted-operation recovery', journal_test)
        check('project-copy guide and source preservation', project_test)
    return {'version': __version__, 'status': 'pass' if all(x['status']=='pass' for x in checks) else 'fail',
            'elapsed_seconds': round(time.monotonic()-started,3), 'checks': checks,
            'scope': 'Portable core smoke test; not a replacement for real-editor qualification.'}
