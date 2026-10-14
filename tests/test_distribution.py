import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from editing_copilot.install import install_resolve_menu, _publish
from editing_copilot.diagnostics import self_test
from editing_copilot.runtime import worker_main

ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    def test_packaged_resources_smoke(self):
        result = self_test(ROOT/'resources')
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(len(result['checks']), 4)

    def test_menu_install_is_user_scoped_and_exact(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            result = install_resolve_menu(ROOT/'resources', folder/'local', folder/'roaming')
            manifest = json.loads(Path(result['manifest']).read_text())
            self.assertEqual(len(manifest['files']), 3)
            self.assertFalse(manifest['source_projects_modified'])
            self.assertFalse(manifest['editor_settings_modified'])
            self.assertTrue(all(Path(x['path']).is_file() for x in manifest['files']))
            self.assertEqual(Path(result['script']).name, 'Editing Copilot.py')

    def test_menu_install_preserves_previous_version(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            first=install_resolve_menu(ROOT/'resources',folder/'local',folder/'roaming')
            script=Path(first['script'])
            script.write_text('previous reviewed version',encoding='utf-8')
            install_resolve_menu(ROOT/'resources',folder/'local',folder/'roaming')
            backups=list(script.parent.glob('Editing Copilot.py.previous-*'))
            self.assertEqual(len(backups),1)
            self.assertEqual(backups[0].read_text(),'previous reviewed version')

    def test_idempotent_install_does_not_create_backups(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            first=install_resolve_menu(ROOT/'resources',folder/'local',folder/'roaming')
            install_resolve_menu(ROOT/'resources',folder/'local',folder/'roaming')
            self.assertFalse(list(Path(first['script']).parent.glob('*.previous-*')))

    def test_invalid_install_target_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            source=folder/'source.py';source.write_text('safe')
            dest=folder/'target.py';dest.mkdir()
            with self.assertRaises(RuntimeError): _publish(source,dest,[])
            self.assertTrue(dest.is_dir())

    def test_rpc_never_runs_unknown_operations(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            request=folder/'request.json';response=folder/'response.json'
            request.write_text(json.dumps({'operation':'execute_code','payload':'print(1)'}))
            with patch('editing_copilot.resolve.ResolveAdapter') as adapter:
                worker_main(request,response)
                adapter.return_value.apply.assert_not_called()
            result=json.loads(response.read_text())
            self.assertFalse(result['ok'])
            self.assertIn('Unsupported',result['error'])

    def test_rpc_errors_are_serialized_without_success(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            request=folder/'request.json';response=folder/'response.json'
            request.write_text(json.dumps({'operation':'inspect'}))
            with patch('editing_copilot.resolve.ResolveAdapter',side_effect=RuntimeError('Unavailable')):
                worker_main(request,response)
            result=json.loads(response.read_text())
            self.assertFalse(result['ok'])
            self.assertEqual(result['error'],'Unavailable')
            self.assertFalse(response.with_suffix('.tmp').exists())

    def test_rpc_request_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);request=folder/'request.json';response=folder/'response.json'
            request.write_bytes(b' '*(1024*1024+1))
            with self.assertRaises(ValueError): worker_main(request,response)
            self.assertFalse(response.exists())


if __name__=='__main__': unittest.main()
