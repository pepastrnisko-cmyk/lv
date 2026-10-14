# Editing Copilot 0.1.0 - Windows local core

This package runs without installing Python. It is a bounded editing companion and an optional native Resolve menu script. It is **not the complete v2 production specification**. Advanced grading, neural models, general language-model reasoning, arbitrary UI control and Microsoft 365 are not implemented or advertised here.

## Start

1. Extract the entire release ZIP to a folder you own.
2. Open `EditingCopilot.exe`. The generated demo contains only color cards; it does not need your media.
3. Choose Kdenlive, open a **saved** `.kdenlive` project, and press Inspect. Unsaved changes in the editor are not visible.
4. Type `add guide at frame 25 named "Review here"`, then Preview and Apply. A new project appears in `Copilot Copies`; the source stays untouched.
5. Use Open current copy to open the result in Kdenlive. The companion reports structural verification separately from editor reopening or creative approval.

Windows may show a notice because this local build is unsigned. No signing certificate or publisher identity was supplied. The package does not disable security software or change Windows/editor security settings.

## Supported commands

| Command | Behavior |
| --- | --- |
| `inspect` / `list clips` | Read the saved Kdenlive project or active Resolve timeline |
| `add guide at frame 25 named "Review"` | Add Kdenlive timeline guide in a new copy, default project category |
| `split clip selected at frame 30` | Split a selected simple Kdenlive instance at absolute timeline frame |
| `trim clip selected end by 5 frames` | Remove 5 frames from its source end, leaving a gap to preserve surrounding positions |
| `add marker at frame 25 named "Review" color Blue` | Resolve timeline marker at zero-based offset from timeline start |
| `undo` | Conflict-checked previous-copy selection for Kdenlive; owned-marker undo for Resolve |
| `stop` | Revoke queued/running work; does not automatically undo a completed edit |

Select the clip **in the companion's timeline list**, not only in the editor. Explicit UUID/playlist/entry instance IDs are accepted. Parameters are frames, not seconds or timecode. Source/compound identity checks prevent name-only targeting.

Kdenlive trim/split are deliberately restricted to simple ungrouped, effect-free, unretimed clips without linked A/V or mixes. Unsupported structures are rejected before writing. There is no ripple edit. Project document version 1.1 mutations are enabled; unknown versions are inspection-only. RGB/HDR/color semantics are not changed.

Kdenlive Undo selects the previous saved project in the companion. Open that file in Kdenlive to restore; both copies remain available. It does not claim to invoke the editor's live undo stack. Later file changes block automatic restoration.

## Resolve menu integration

Use Tools > Install Resolve menu. Restart Resolve and open Workspace > Scripts > Utility > Editing Copilot. The script uses the installed editor API and supports inspection, marker preview, Apply and owned-marker Undo when the edition exposes UIManager/scripting.

The menu installer copies only the script and reviewed adapter into your user folders. It does not open ports, create a cloud account, change external scripting settings, or install third-party effects. Where UIManager is unavailable, the script falls back to read-only console diagnostics.

The desktop Resolve mode connects externally only if your edition and configuration allow it. It may require the user to configure Local external scripting in Resolve Studio. This build does not change that setting. On the development machine Resolve 21.1.1 was installed, but external access was unavailable, so native marker placement is **not live-qualified**. The 41 adapter/menu contract tests do not replace that acceptance test.

## Dictation and Stop

Dictate uses an installed Windows offline speech recognizer only after you press the button. Recognition fills the command field; it never applies an edit automatically. No recorded audio is uploaded or retained by this application. Language and availability depend on Windows; typed commands always work. Installed recognizer detection passed here; actual microphone recognition was not validated.

Stop is available as a button, Escape in the app, and Ctrl+Shift+Space when that global hotkey can be registered. A busy external native call is isolated in a worker process. Interrupting it may leave an unknown host outcome, which is journaled and blocks automatic retry. Stop cannot undo input or a host operation already dispatched.

## Data and recovery

The companion stores history, generated examples and request files in `%LOCALAPPDATA%\EditingCopilot\data`. Resolve menu history is `%LOCALAPPDATA%\EditingCopilot\resolve-menu-history.json`. The native helper package is `%LOCALAPPDATA%\EditingCopilot\integration`; the user menu script is in `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility`.

History is local SQLite. It is not separately encrypted; use your normal disk-protection policy. No network service or cloud bridge is included. Pending/applied records after a crash become unknown instead of being replayed. Preserve history and all project copies when investigating unknown results. Unresolved operations block further mutation for that project.

Export inspection reports deliberately, after checking whether filenames/paths contain client information. Reports stay at the chosen destination. No telemetry, screenshots or media are transmitted.

## Installation and removal

The ZIP is portable. Tools > Install desktop app optionally copies the executable to `%LOCALAPPDATA%\Programs\EditingCopilot` and creates a Start menu shortcut. Tools > Install Resolve menu installs only that integration. Existing managed files are backed up before replacement.

To remove the portable build, close it and remove its extracted folder. For installed copies, remove the managed executable/shortcut and the menu script listed above. Keep or separately archive your history, generated projects and outputs; the application never deletes original media. The integration manifest records the installed script/module paths and hashes. Do not remove unrelated Resolve scripts.

## Test evidence and release status

Read `TEST_RESULTS.json` and `RELEASE_NOTES.md` in the release. All completed automated checks are listed individually; unavailable integrations are reported separately. Kdenlive's installed MLT/FFmpeg were used to render/compare sample sequences; real-editor visual acceptance remains separately reported. This is a runnable core release candidate, not a claim that every requirement in the 31-page v2 specification is complete.

## Developer build

Install Python 3.12 x64, create a virtual environment, install `requirements-build.txt`, then install this source package in editable mode. Run `python tools/run_release_tests.py`, `python -m editing_copilot --self-test smoke.json`, and build with PyInstaller using `build_release.py`. Tests requiring installed Kdenlive tools are skipped on machines without them. Dependencies and bundled license notices are supplied with the release.
