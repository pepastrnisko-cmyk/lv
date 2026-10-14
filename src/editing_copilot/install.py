"""Explicit per-user integration installation; no admin or editor settings."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _publish(source, destination, records):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or destination.is_symlink():
            raise RuntimeError('Installation target is not a regular file: ' + str(destination))
        if _digest(source) == _digest(destination):
            records.append({'path': str(destination), 'sha256': _digest(destination)})
            return
        backup = destination.with_name(destination.name + '.previous-' + uuid.uuid4().hex[:8])
        shutil.copy2(destination, backup)
    temporary = destination.with_name(destination.name + '.tmp-' + uuid.uuid4().hex)
    try:
        shutil.copy2(source, temporary)
        if _digest(source) != _digest(temporary):
            raise RuntimeError('Installation integrity check failed.')
        os.replace(temporary, destination)
        records.append({'path': str(destination), 'sha256': _digest(destination)})
    finally:
        if temporary.exists():
            temporary.unlink()


def install_resolve_menu(resources, local_base=None, roaming_base=None):
    """Only install the two reviewed modules needed by the in-editor script."""
    resources = Path(resources)
    local = Path(local_base or os.environ['LOCALAPPDATA']) / 'EditingCopilot'
    roaming = Path(roaming_base or os.environ['APPDATA'])
    utility = roaming / 'Blackmagic Design' / 'DaVinci Resolve' / 'Support' / 'Fusion' / 'Scripts' / 'Utility'
    package = local / 'integration' / 'editing_copilot'
    records = []
    for name in ('__init__.py', 'resolve.py'):
        _publish(resources / 'integration' / 'editing_copilot' / name, package / name, records)
    _publish(resources / 'integration' / 'Editing Copilot.py', utility / 'Editing Copilot.py', records)
    manifest = local / 'integration-manifest.json'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({'version': '1.0.0', 'files': records,
                                    'source_projects_modified': False,
                                    'editor_settings_modified': False}, indent=2), encoding='utf-8')
    return {'script': str(utility / 'Editing Copilot.py'), 'manifest': str(manifest),
            'message': 'Resolve menu installed for your account. Restart Resolve, then Workspace > Scripts > Utility > Editing Copilot. No scripting/security preferences were changed.'}


def install_companion(resources, local_base=None):
    if not getattr(sys, 'frozen', False):
        raise RuntimeError('Use the packaged application for desktop installation.')
    base = Path(local_base or os.environ['LOCALAPPDATA'])
    target = base / 'Programs' / 'EditingCopilot' / 'EditingCopilot.exe'
    records = []
    _publish(Path(sys.executable), target, records)
    # Shortcuts are a convenience; failure must not hide a valid installation.
    shortcut = None
    com_initialized = False
    try:
        import pythoncom
        import win32com.client
        # Installation runs on the UI worker, which has no COM apartment yet.
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        com_initialized = True
        folder = Path(os.environ['APPDATA']) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs'
        folder.mkdir(parents=True, exist_ok=True)
        link = folder / 'Editing Copilot.lnk'
        shell = win32com.client.Dispatch('WScript.Shell')
        item = shell.CreateShortcut(str(link))
        item.TargetPath = str(target)
        item.WorkingDirectory = str(target.parent)
        item.Description = 'Local editing commands for Kdenlive and DaVinci Resolve'
        item.Save()
        shortcut = str(link)
    except Exception:
        pass
    finally:
        if com_initialized:
            pythoncom.CoUninitialize()
    return {'executable': str(target), 'shortcut': shortcut,
            'message': 'Companion installed for your account. Projects, media and editor settings were not changed.'}
