"""Assemble reviewable local distribution and exact evidence manifest."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

root=Path(__file__).resolve().parents[1]
out=root.parents[1]/'outputs'
release=out/'EditingCopilot-0.1.0-Windows'
exe=release/'EditingCopilot.exe'
assert exe.is_file()
report=json.loads((root/'release-test-results.json').read_text())
assert report['status']=='pass' and report['failed']==0 and report['errors']==0
smoke=release/'PACKAGED_SMOKE_TEST.json'
subprocess.run([str(exe),'--self-test',str(smoke)],timeout=25,check=True)
assert json.loads(smoke.read_text())['status']=='pass'
environment=release/'ENVIRONMENT.json'
subprocess.run([str(exe),'--diagnostics',str(environment)],timeout=25,check=True)
shutil.copy2(root/'README.md',release/'README.md')
shutil.copy2(root/'LICENSE',release/'LICENSE')
shutil.copy2(root/'release-test-results.json',release/'TEST_RESULTS.json')
if (root/'tests'/'live_resolve_result.json').exists():
    shutil.copy2(root/'tests'/'live_resolve_result.json',release/'RESOLVE_LIVE_TEST.json')
shutil.copytree(root/'resources'/'integration',release/'Resolve Integration',dirs_exist_ok=True)
shutil.copy2(root/'resources'/'demo.kdenlive',release/'Demo.kdenlive')
licenses=release/'licenses';licenses.mkdir(exist_ok=True)
site=root/'.venv'/'Lib'/'site-packages'
license_files={
 'Python-3.12.10-LICENSE.txt':Path(sys.base_prefix)/'LICENSE.txt',
 'PyInstaller-6.22.0-COPYING.txt':site/'pyinstaller-6.22.0.dist-info'/'licenses'/'COPYING.txt',
 'pywin32-win32-LICENSE.txt':site/'win32'/'license.txt',
 'pywin32-pythonwin-LICENSE.txt':site/'pythonwin'/'license.txt',
 'Tk-8.6-LICENSE.txt':Path(sys.base_prefix)/'tcl'/'tk8.6'/'license.terms',
 'Tcl-8.6-LICENSE.txt':root/'resources'/'licenses'/'Tcl-8.6-LICENSE.txt',
}
for name,path in license_files.items():
    if not path.is_file():raise RuntimeError('Required license file missing: '+str(path))
    shutil.copy2(path,licenses/name)
(release/'THIRD_PARTY_NOTICES.md').write_text('''# Third-party notices

The executable bundles CPython 3.12.10, Tcl/Tk supplied with that runtime, and pywin32 311. It uses the PyInstaller 6.22.0 bootloader under its distribution exception. Corresponding license texts are in licenses/; the CPython license file includes notices for bundled dependencies. Windows SAPI is used from the installed operating system and is not redistributed.

DaVinci Resolve, Kdenlive, MLT and FFmpeg are NOT bundled. The integration uses the user's installed editor/SDK and tools. No Blackmagic native libraries, proprietary plugins, model weights or client footage are redistributed. The included color-card fixture and adapter code were authored for this release.

Build dependencies are pinned in the source package. Runtime and build-component records appear in MANIFEST.json. This unsigned local candidate does not assert enterprise certification or completion of the production specification.
''',encoding='utf-8')
notes=f'''# Editing Copilot 0.1.0 - release candidate

Built 13 October 2026 on Windows 11 x64. Runnable portable Windows core; no Python installation needed. The complete v2 AI production product is not implemented.

## Executed checks

- {report['passed']} automated tests passed, {report['failed']} failures, {report['errors']} errors, {report['skipped']} skipped.
- Four installed Kdenlive MLT/FFmpeg rendering comparisons passed, including full decoded-frame comparison for guide/split preservation and targeted trim changes.
- {sum(x['test'].startswith('test_ui.') and x['status']=='pass' for x in report['tests'])} real Tk lifecycle/workflow/report-safety tests passed.
- Packaged executable core smoke tests passed.
- Installed offline recognizer detection passed; microphone recognition was not exercised.
- Resolve native loading probes ran, but external scripting access remained unavailable. Live marker acceptance and native menu visual qualification did not run.

## Supported scope

Saved Kdenlive project inspection, guides and restricted simple trim/split in new copies; exact command grammar; preview/apply; conflict-aware previous-copy selection; durable action history; responsive Stop; optional Windows dictation into the command field. Native Resolve menu and documented inspection/owned-marker adapter are included conditionally.

## Remaining production gaps

General LLM reasoning, expert autonomous color matching/grading, masks/restoration/generation, complex linked/ripple edits, Microsoft 365 identity/tenant integration, signed installer/update service, full host-version certification, real-microphone acceptance and long soak tests remain outside this candidate. The 31-page specification defines these future obligations; automated core tests do not certify them.

Kdenlive project output is structurally read back and engine-tested. Actual editor reopen/playback of every user's project is a separate check. The companion labels that status and preserves both project copies. Resolve configuration/edition can prevent connection or UIManager availability; the build changes no security preferences.

## Use

Open EditingCopilot.exe, inspect the demo or a saved project, preview a supported command, and Apply to create a copy. Read README.md before using a client project. Use Tools for optional per-user desktop/menu installation. The build is unsigned; no signing credentials were available.
'''
(release/'RELEASE_NOTES.md').write_text(notes,encoding='utf-8')
digest=hashlib.sha256(exe.read_bytes()).hexdigest()
deps=[]
for name in ('pyinstaller','pywin32','pyinstaller-hooks-contrib','altgraph','packaging','pefile','pywin32-ctypes','setuptools'):
    deps.append({'name':name,'version':importlib.metadata.version(name),'role':'runtime' if name=='pywin32' else 'build'})
manifest={'product':'Editing Copilot','version':'0.1.0','status':'bounded-core-release-candidate',
 'created_utc':datetime.now(timezone.utc).isoformat(),'executable_sha256':digest,'signed':False,
 'tests_passed':report['passed'],'tests_skipped':report['skipped'],'runtime':'CPython 3.12.10 x64',
 'dependencies':deps,'network_service':False,'full_v2_spec_complete':False,
 'resolve_live_qualified':False,'kdenlive_engine_fixtures_qualified':True,
 'files':[]}
for path in sorted(release.rglob('*')):
    if path.is_file() and path.name!='MANIFEST.json':
        manifest['files'].append({'path':path.relative_to(release).as_posix(),'bytes':path.stat().st_size,
                                 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(release/'MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
zip_path=out/'EditingCopilot-0.1.0-Windows.zip'
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for path in sorted(release.rglob('*')):
        if path.is_file():archive.write(path,Path(release.name)/path.relative_to(release))
source_path=out/'EditingCopilot-0.1.0-Source.zip'
with zipfile.ZipFile(source_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for name in ('src','tests','tools','integrations','resources'):
        for path in sorted((root/name).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.mp4','.sqlite3'):
                archive.write(path,Path('EditingCopilot-Source')/path.relative_to(root))
    for name in ('README.md','LICENSE','pyproject.toml','requirements-build.txt','build_release.py','launcher.py','release-test-results.json'):
        archive.write(root/name,Path('EditingCopilot-Source')/name)
summary={'windows_zip':str(zip_path),'source_zip':str(source_path),'exe_sha256':digest,
         'zip_bytes':zip_path.stat().st_size,'tests_passed':report['passed'],'status':manifest['status']}
(out/'EditingCopilot-0.1.0-Delivery.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary))
