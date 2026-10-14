# Editing Copilot 1.0.0 — voice-controlled assistant for Kdenlive and DaVinci Resolve (Windows)

Say **"Copilot, add a marker at ten seconds named Intro"**, **"Copilot, cut"**, **"Copilot, play"**, then **"Copilot, apply"**.
Everything is free. Voice is **English only**.

## 1. Install (Windows 10/11, no admin, no Python needed)

1. Extract `plugin-final.zip` to a folder you own, e.g. `C:\Users\<you>\EditingCopilot-src`.
2. Double-click **`Install.cmd`**. It will automatically:
   - install Python 3.12 for your user (winget, or python.org silent installer as fallback),
   - create a private environment in `%LOCALAPPDATA%\EditingCopilot\app`,
   - install Vosk + microphone support and download the free English model (~40 MB),
   - install the DaVinci Resolve menu script, create Start-menu and Desktop shortcuts, run a self-check.
   Log: `%LOCALAPPDATA%\EditingCopilot\install.log`.
3. Optional flags (run in PowerShell from the extracted folder):
   ```
   .\Install.cmd -GroqKey gsk_xxx          # enable free online mode (Groq)
   .\Install.cmd -GeminiKey AIza_xxx       # or Google Gemini free tier
   .\Install.cmd -Whisper                  # also install faster-whisper (better local accuracy, ~150 MB+)
   .\Install.cmd -Mode local               # force offline-only
   ```
4. Start **Editing Copilot** from the Start menu. Click **Hands-free voice**. Windows asks for microphone permission the first time (Settings › Privacy › Microphone › allow desktop apps).

Uninstall: `Uninstall.cmd` (keeps your history/project copies; add `-RemoveData` to delete them). Your media is never touched.

## 2. Voice / AI modes (selector next to the command box, or `"mode"` in config)

| Mode | Speech-to-text | Understanding | Needs |
|---|---|---|---|
| **Local / offline** | Vosk small en-us (default) or faster-whisper `base.en` | Built-in rules; optional Ollama local LLM | nothing (Ollama optional) |
| **Online (free tier)** | Groq `whisper-large-v3-turbo` or Gemini | Built-in rules first, then Groq Llama 3.1 8B or Gemini Flash | free API key |
| **Auto** (default) | Online if a key is set and reachable, otherwise local; switches to local after an online failure | same chain | — |

**Why this choice:** Microsoft 365 Copilot is paid and has no API to drive a video editor; ChatGPT/Claude APIs are not free. Vosk is free, offline, fast on any CPU and private; faster-whisper is free and more accurate; Groq and Gemini have genuine free tiers with good English Whisper/LLM quality. The deterministic rule parser handles all supported commands without any LLM, so an LLM is only a fallback for unusual phrasing — and its answer must still match the fixed command grammar and go through Preview, so a model can never invent or directly execute an edit.

Free keys: Groq → https://console.groq.com/keys ; Gemini → https://aistudio.google.com/apikey . Keys are stored as user environment variables (`GROQ_API_KEY`, `GEMINI_API_KEY`), never in the config file. Online mode sends only the short utterance audio/text to that provider; free tiers have rate limits and may use data per their terms — use Local mode for confidential projects.

Ollama (optional local LLM): install from https://ollama.com, run `ollama pull llama3.2:3b`, then set `"local": {"llm": "ollama"}` in the config.

## 3. What you can say

Wake word: **"copilot"** (configurable / can be disabled). Numbers can be spoken ("two hundred and five"); "N seconds" and `hh:mm:ss:ff` are converted using the project FPS (25 if unknown).

| Say | Effect |
|---|---|
| "add a marker at 10 seconds named Intro colour red" | Resolve marker preview (Kdenlive: use "guide") |
| "add a guide at frame 250 named Review" | Kdenlive guide preview (in a project copy) |
| "cut the selected clip at frame 300" / "shorten the selected clip by 5" | Kdenlive split / trim preview of the clip selected in the companion list |
| "apply" / "confirm" · "cancel" · "undo" · "inspect" · "stop" | control the previewed plan |
| "play", "pause", "cut", "marker here"/"guide here", "set in point", "set out point", "go to start/end", "next/previous frame", "save", "redo", "delete clip", "zoom in/out", "render" | **Live**: sends the editor's keyboard shortcut to the Kdenlive/Resolve window |

Edit commands are always previewed first; "apply" applies only that unchanged preview (disable with `"allow_voice_apply": false`). Ctrl+Shift+Space or Esc = Stop.

## 3c. Kdenlive project-copy edits and checks

These work on the saved `.kdenlive` file. Each one is previewed first, written to a **new copy** in `Copilot Copies`, read back and verified, and can be undone (the previous file is selected again). The original project is never changed.

| Say or type | Effect |
|---|---|
| "add effect sepia to clip selected" | adds an allowlisted effect: greyscale, sepia, gaussian blur, box blur, brightness, mirror, invert |
| "lock track Video 1" / "unlock …" · "mute track Audio 1" / "unmute …" · "hide track Video 1" / "show …" | track state (mute is for audio tracks, hide for video tracks) |
| "move clip selected to frame 100" (or "move the selected clip to 4 seconds") | moves the clip on the same track into free space |
| "delete clip selected" | removes the clip and leaves a gap (no ripple). By voice, "apply" is not enough: say **"confirm"** |
| "inspect project details" · "check media" | read-only: tracks, clips and effects; missing media files and frame-rate mismatches (uses ffprobe when installed) |

"add effect X" without "to clip …", and "delete clip" on its own, still use the on-screen workflows and shortcuts from 3a.

## 3a. Expert workflows (built on the click/type engine)

| Kdenlive | Resolve |
|---|---|
| "add effect Gaussian blur" (Effects tab → search → double-click applies to the selected clip) | "go to media/cut/edit/fusion/color/fairlight/deliver page" (Shift+2…8) |
| "add transition Dissolve" (Compositions tab) | "add serial / parallel / layer / outside node" (Color page, Alt+S/P/L/O) |
| "switch to logging/editing/audio/effects/color workspace" | "show scopes" (Ctrl+Shift+W), "grab still", "bypass grades" |
| "open waveform / vectorscope / histogram / RGB parade" (View menu) | "reset grade" (confirm) |
| "open effects / compositions / project bin / effect stack / audio mixer / subtitles … panel" | "project settings" (confirm), "render with preset YouTube" (Deliver page + preset click, confirm; never presses Render/Add to Queue) |
| "open render dialog [with preset X]" (confirm; never presses Render), "project settings" (confirm) | "blade tool", "selection tool" |
| "add title", "insert track", "razor tool", "selection tool", "select all", "which version" (Help › About) | |

Each step looks the label up on screen first and stops without guessing if a name differs on your build (the reference's "confirm on screen" rule). **Not automated** (by design or because no reliable path exists): actual grading decisions (lift/gamma/gain amounts, skin matching, look design — use "how do I …" for the reference guidance), shot matching, loudness measurement, starting a render, LUT selection from files, proxy/archive settings changes, and anything inside Resolve's node graph beyond adding nodes.

## 3b. Full on-screen control (click / drag / type / menus) — like a person

The app finds controls by name with **Windows UI Automation** (pywinauto) and, when an editor exposes no accessible name (common in Resolve), by **OCR** of the editor window (rapidocr, free, local; screenshots stay in memory). Then it moves the real mouse/keyboard.

| Say | Does |
|---|---|
| "click Render", "click the Edit tab", "click the Color page", "select the Project Bin panel" | left-click the best-matching visible label (UIA Invoke when possible) |
| "open File menu", then "click Save As" | menus and their pop-ups (pop-up windows of the editor are searched too) |
| "double click Intro", "right click the Intro clip", "shift click Outro", "control click the second Interview" | mouse buttons, modifiers, Nth match (top-to-bottom, left-to-right) |
| "drag Intro to Video 2", "drag the Intro clip right 120 pixels", "drag from 400 600 to 900 600" | real press-move-release drags (timeline clips, sliders, panels, bin → timeline) |
| "move mouse to Effects" / "hover over 300 400" | hover (tooltips) |
| "type Final cut v2", "press enter", "press control shift z", "press F5", "close dialog" | keyboard, dialogs |
| "scroll up", "scroll down 5" | wheel at the current mouse position |
| "click at 640 480" | absolute screen pixel |

Safety: acts only when Kdenlive/Resolve is (or can be brought) in front; anything matching *delete, remove, quit, close project, overwrite, replace, discard, reset, render, project settings, lift, extract …* or keys Delete / Ctrl+Q / Alt+F4 / Ctrl+Return waits for a spoken **"confirm"** ("cancel" drops it). Stop button / Esc / **Ctrl+Shift+Space** / "stop" abort between steps. Every action is logged. Results are "sent – not verified": look at the editor. Tools › *List controls of the editor window* shows what UIA can see; from a terminal: `python -m editing_copilot --list-controls kdenlive --focus --ocr`.

## 3c. Voice macros (your own named sequences)

- **By voice:** "record macro my export" → perform the actions by voice → "stop recording". Run it with "run macro my export" or just "my export".
- **In the app:** Tools › *Voice macros…* — name + JSON steps, per editor.
- **File:** `%LOCALAPPDATA%\EditingCopilot\data\macros.json`, sections `kdenlive`, `resolve`, `any`. Step kinds: `click` (label, role, button, double, modifiers, index), `click_at` (x, y), `drag` (label/x,y → to_label / x2,y2 / dx,dy), `move`, `key` (text), `type` (text), `scroll` (notches), `wait` (seconds ≤ 30), `live` (text = action from section 3).
  ```json
  {"kdenlive": {"my export": [{"kind":"click","label":"Project","role":"menu"},{"kind":"click","label":"Render"},{"kind":"wait","seconds":1}]}}
  ```
  A macro containing a destructive step is confirmed once, before it starts. Invalid steps are rejected when loading (shown in the editor dialog).

## 3d. Editing & grading knowledge ("how do I …")

Your *Kdenlive and Color Grading Master Reference* is bundled (`resources/knowledge/`). Ask "how do I match skin tones between shots", "explain ripple trim", "how do I set up proxies". The app routes the question by the reference's own "load by task" rules (grading → Part 1 + K7, trims → K2, render → K9 …) and shows the matching sections; with Ollama/Groq/Gemini configured it also gives a short answer restricted to that text. The reference's rules are enforced in automation: confirm before deleting/overwriting/rendering/changing project settings, verify names on screen (label matching), undo is a separate checked step.

## 4. Kdenlive

Kdenlive has no plugin API on Windows (its D-Bus interface is Linux-only). So:
- **Project edits** (guide/split/trim) are made on the saved `.kdenlive` XML in a **new copy** in `Copilot Copies`, verified, recorded and undoable. Save in Kdenlive first, then Open the copy (button "Open current copy"). Unsaved editor changes are invisible to the companion.
- **Live commands** are Kdenlive default shortcuts (Space, Shift+R cut, G guide, Ctrl+Z …). If you changed shortcuts in Kdenlive, edit `live_control.kdenlive_shortcuts` in the config. Keys are sent only when the foreground window is `kdenlive.exe`.

## 5. DaVinci Resolve (free and Studio)

- **Live voice commands work in both free and Studio** (keyboard shortcuts to `Resolve.exe`; Edit page: Ctrl+B blade, M marker).
- **In-editor menu**: Workspace › Scripts › Utility › Editing Copilot (installed by setup, restart Resolve). Internal scripts run in free and Studio; it supports inspect, marker preview/apply, owned-marker undo.
- **External scripting from the companion** (Resolve mode "Inspect" in the app) needs Resolve **Studio** with Preferences › System › General › *External scripting using* = **Local**. On free Resolve use the menu script or live commands instead.

## 5b. Setup wizard, overlay, feedback, start-up

First start opens a wizard (editor, Local/Online/Auto, microphone test, optional free key saved as a Windows user variable, beeps / spoken replies via the free Windows voice, start with Windows, overlay). Re-open via Tools › Setup wizard. The always-on-top overlay (bottom right) shows Listening / Heard / Result; click it to show the main window, right-click to hide. Tools › What can I say? shows the cheat sheet. Crashes are logged to `data\logs\crash.log`.

## 6. Configuration, logs, data

`%LOCALAPPDATA%\EditingCopilot\data\config.json` (created on first run; invalid values fall back to defaults with a log warning). Logs: `data\logs\editing-copilot.log` (rotating). History: `data\history.sqlite3`. Diagnostics: `%LOCALAPPDATA%\EditingCopilot\app\Scripts\python.exe -m editing_copilot --voice-check` and `--interpret "add marker at 3 seconds named A"`.

## 6b. Live-test results on the target PC (Kdenlive 26.08.1, Resolve 21.1.1)

Worked on screen: Kdenlive welcome › New Project (UIA), menu opening (View), Effects tab, effect search field (found by OCR) + typing, Gaussian/Blur results listed, Render toolbar button behind voice confirm → render dialog opened and closed with Escape (no render started), hover, scroll, keyboard shortcuts, Ctrl+O file dialog + typing a path, graceful close. Resolve: Project Manager read by OCR (UIA exposes ~8 elements); no project was opened, so page switching/nodes were not exercised live.

Known: the bundled *demo.kdenlive* (minimal hand-written MLT) crashes Kdenlive 26.08.1 when opened in the editor — use your own saved projects for project edits; the companion's demo remains for trying the command preview only. Workspace tabs (Logging/Editing/Color…) were not found when the window was not maximised; maximise the editor. Windows does not let any app take focus from an elevated (administrator) window — close/minimise such windows before speaking commands. OCR takes ~8 s per full-window read on this PC (UIA is ~0.4 s), so OCR-only labels are slower.

## 7. Troubleshooting

- *"No local recognizer"* → re-run Install.cmd (model download) or check the `vosk_model_path`.
- *"Microphone unavailable"* → Windows microphone privacy setting; set `voice.device` to your mic index.
- Hands-free never reacts → say the wake word first, speak in a quiet room; disable `require_wake_word` to test.
- Live keys do nothing → click the editor window once; editors running *as administrator* cannot receive keys from a normal app.
- Online fails → check key, internet, free-tier rate limit; Auto mode falls back to local automatically.

## 8. Developers

`pip install -e .[dev,whisper]`, `python -m pytest`, `python build_release.py` (PyInstaller one-file exe; Windows only). Original 0.1 core documentation: `docs/README-core-v0.1.md`.
