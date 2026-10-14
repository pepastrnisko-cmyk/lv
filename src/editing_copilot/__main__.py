import argparse
import json
from pathlib import Path
import sys
import traceback


def resource_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'resources'
    import os
    candidates = [os.environ.get('EDITING_COPILOT_RESOURCES'),
                  Path(__file__).resolve().parents[2] / 'resources',  # source checkout
                  Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'EditingCopilot' / 'resources']  # setup.ps1
    for candidate in candidates:
        if candidate and (Path(candidate) / 'integration').is_dir():
            return Path(candidate)
    return Path(candidates[1])


def main():
    parser = argparse.ArgumentParser(description='Editing Copilot local core')
    parser.add_argument('--resolve-worker', nargs=2, metavar=('REQUEST', 'RESPONSE'))
    parser.add_argument('--self-test', metavar='RESULT_JSON')
    parser.add_argument('--diagnostics', metavar='RESULT_JSON')
    parser.add_argument('--install-resolve', action='store_true')
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--voice-check', action='store_true', help='print the voice/AI backend that would be used')
    parser.add_argument('--interpret', metavar='TEXT', help='show how an English utterance is understood (no edit)')
    parser.add_argument('--list-controls', metavar='EDITOR', choices=('kdenlive', 'resolve'),
                        help='read-only: enumerate UI Automation (and with --ocr, OCR) labels of the editor window')
    parser.add_argument('--ocr', action='store_true')
    parser.add_argument('--minimized', action='store_true', help='start minimised (used by start-with-Windows)')
    parser.add_argument('--version', action='version', version='Editing Copilot ' + __import__('editing_copilot').__version__)
    parser.add_argument('--focus', action='store_true', help='bring the editor window to the front first')
    args = parser.parse_args()
    if args.list_controls:
        from .uiauto import WindowsBackend
        import time as _t
        backend = WindowsBackend()
        if args.focus:
            backend.focus_editor(args.list_controls)
        from . import live as _live
        hwnd = backend.editor_window(args.list_controls) or _live._find_window(_live.PROCESSES[args.list_controls])
        if not hwnd:
            print(json.dumps({'error': f'{args.list_controls} window not found'})); return 1
        t0 = _t.monotonic(); uia = backend.uia_controls(hwnd); t1 = _t.monotonic()
        out = {'window_rect': backend.window_rect(hwnd), 'uia_count': len(uia), 'uia_seconds': round(t1 - t0, 2),
               'uia_sample': [{'name': c.name, 'role': c.role} for c in uia[:80]]}
        if args.ocr:
            ocr = backend.ocr_controls(hwnd)
            out.update(ocr_count=len(ocr), ocr_seconds=round(_t.monotonic() - t1, 2), ocr_sample=[c.name for c in ocr[:80]])
        print(json.dumps(out, indent=1, ensure_ascii=False)); return 0
    if args.voice_check or args.interpret:
        from .runtime import data_directory
        from .config import load_config, write_default_config
        from .voice import voice_status
        from .assistant import understand, online_available
        directory = data_directory(); directory.mkdir(parents=True, exist_ok=True)
        write_default_config(directory)
        cfg, warnings = load_config(directory)
        if args.interpret:
            intent = understand(args.interpret, cfg)
            out = dict(intent.__dict__)
            if intent.kind == 'ui':
                out['data'] = [a.to_dict() for a in intent.data]
                out['needs_confirmation'] = any(a.destructive() for a in intent.data)
            elif intent.kind == 'workflow':
                actions, destructive = intent.data
                out['data'] = [a.to_dict() for a in actions]
                out['needs_confirmation'] = bool(destructive or any(a.destructive() for a in actions))
            print(json.dumps(out, ensure_ascii=False, default=str))
            return 0
        ok, message = voice_status(cfg, directory)
        print(json.dumps({'mode': cfg['mode'], 'online_key_present': online_available(cfg), 'voice_ok': ok,
                          'voice': message, 'config': str(directory / 'config.json'), 'warnings': warnings}, indent=2))
        return 0 if ok else 1
    if args.resolve_worker:
        from .runtime import worker_main
        worker_main(*args.resolve_worker)
        return 0
    if args.self_test or args.diagnostics:
        from .diagnostics import self_test, environment
        result = self_test(resource_dir()) if args.self_test else environment()
        Path(args.self_test or args.diagnostics).write_text(json.dumps(result,indent=2),encoding='utf-8')
        return 0 if result.get('status','pass')=='pass' else 1
    if args.install_resolve or args.install:
        from .install import install_resolve_menu, install_companion
        result = install_resolve_menu(resource_dir()) if args.install_resolve else install_companion(resource_dir())
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk();root.withdraw()
        messagebox.showinfo('Editing Copilot', result['message'])
        root.destroy()
        return 0
    from .ui import run_ui
    run_ui(resource_dir=resource_dir(), minimized=args.minimized)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        if any(flag in sys.argv for flag in ('--resolve-worker', '--self-test', '--diagnostics')):
            if sys.stderr is not None:
                traceback.print_exc()
            raise SystemExit(1)
        if sys.stderr is not None:
            traceback.print_exc()
        else:
            import tkinter as tk
            from tkinter import messagebox
            root=tk.Tk();root.withdraw()
            messagebox.showerror('Editing Copilot could not start',str(exc))
            root.destroy()
        raise SystemExit(1)
