# 0.2.0
- Hands-free English voice control with wake word, continuous listening and endpointing.
- Selectable modes: Local/offline (Vosk, faster-whisper, optional Ollama), Online free tier (Groq, Gemini), Auto fallback.
- Natural-language normalizer (spoken numbers, seconds/timecode→frames, synonyms, common mishearings) + validated LLM fallback.
- Live editor control via verified-foreground keyboard shortcuts for Kdenlive and Resolve (free & Studio).
- JSON config with validation, rotating logs, `--voice-check`/`--interpret` diagnostics.
- One-click Windows installer (auto-installs Python 3.12, model, Resolve menu, shortcuts) and uninstaller.
- 19 new tests (incl. real Vosk recognition of synthesized speech).
Not verified on Windows / with real editors: see README and report.
