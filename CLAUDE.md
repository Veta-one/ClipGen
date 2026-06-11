# CLAUDE.md

This file is the current developer guide for agents working in this repository.

## Project Overview

ClipGen is a Windows desktop automation utility. It lets users run AI actions through global hotkeys without switching applications:

• selected text is copied, processed by an AI provider, and pasted back;
• clipboard images can be sent to multimodal models;
• voice hotkeys can run push-to-talk transcription through faster-whisper.

Current app version: `2.4.1`.

## Main Capabilities

• Google Gemini native API.
• OpenAI-compatible API providers: OpenAI, OpenRouter, DeepSeek, local endpoints.
• Per-hotkey prompt, color, provider and model override.
• Learning mode with explanation popup.
• Whisper voice transcription with model download/install from Settings.
• RU/EN runtime language switching.
• HTTP/SOCKS5 proxy support.
• API key rotation and model/key testing.
• Windows tray status and top-right transcription overlay.

## Development Commands

```bash
pip install -r requirements.txt
python -m clipgen.main
python tools/check_i18n.py
python -m compileall clipgen tools/check_i18n.py
py -m PyInstaller --clean ClipGen.spec
```

For verbose exe builds:

```bat
build_verbose.bat
```

Do not use build flows that recreate `ClipGen.spec` unless you also preserve the current spec logic. The spec contains required hidden imports, ML exclusions, and VC runtime filtering.

## Architecture

```text
clipgen/
  main.py                 entry point
  app.py                  ClipGenApp composition root and queue worker
  core/
    config.py             ConfigManager, migrations, DEFAULT_CONFIG merge
    constants.py          DEFAULT_CONFIG, __version__, paths
  api/
    gemini.py             Gemini provider
    openai_compat.py      OpenAI-compatible provider
    processor.py          clipboard AI processing
  hotkeys/
    listener.py           pynput global hotkey listener
    manager.py            hotkey CRUD and migration helpers
  transcription/
    audio_recorder.py     microphone capture
    deps.py               optional Whisper dependency install/check
    diagnostics.py        runtime diagnostics report
    download_worker.py    external HuggingFace file downloader
    filters.py            hallucination filters
    model_manager.py      load/download/unload/transcribe state machine
    transcriber.py        push-to-talk orchestration
    worker_client.py      isolated Whisper worker process client
  ui/
    main_window.py        main PyQt window, signals, transcription handlers
    overlay.py            transcription status overlay
    tray.py               tray icon states
    widgets.py            shared widgets, including non-scroll combo box
    tabs/
      log_tab.py
      settings_tab.py
      prompts_tab.py
      help_tab.py
  utils/
    i18n.py
    proxy.py
    autostart.py
    updates.py
    clipboard.py
    process_guard.py      kill-on-close job object + orphan helper sweep
```

## Threading Model

• Qt main thread owns UI objects and `QTimer` instances.
• `HotkeyListener` runs in a daemon thread via `pynput`.
• `ClipGenApp.queue_worker` consumes hotkey events.
• Text/image AI calls run in worker threads with cancellation.
• Whisper model load/download can run asynchronously.
• Whisper inference is isolated by default through `WhisperWorkerClient` when `transcription.isolate_inference_process` is true.
• Cross-thread UI updates must go through Qt signals.

Never mutate Qt widgets directly from background threads.

## Transcription Design

Voice transcription is optional and lazy-loaded.

Important config keys:

```json
{
  "transcription": {
    "enabled": false,
    "model": "large-v3",
    "device": "auto",
    "compute_type": "float16",
    "default_language": "auto",
    "preload_on_start": false,
    "isolate_inference_process": true,
    "auto_unload_minutes": 5,
    "beam_size": 1,
    "vad_filter": true,
    "filter_hallucinations": true,
    "feedback_sounds": true,
    "audio": {
      "input_device": null,
      "max_record_seconds": 120
    }
  }
}
```

Key rules:

• Heavy Whisper dependencies are not bundled into `ClipGen.exe`.
• The in-app **Install / Download** button installs optional packages and downloads the selected model.
• Download cancellation is supported.
• Diagnostics are written to `transcription_diagnostics.txt` on relevant failures.
• The exe build filters PyQt5 VC runtime DLLs and adds current System32 VC runtime DLLs to avoid CTranslate2 crashes.

## Configuration

`settings.json` is created beside the app and migrated on load. `ConfigManager` deep-merges user config with `DEFAULT_CONFIG`, including the nested `transcription` section.

Hotkeys support:

• `type`: `text_action` or `transcription`;
• `combination`;
• `name`;
• `prompt`;
• `log_color`;
• custom provider/model override;
• learning mode fields;
• transcription language and initial prompt overrides.

## Localization Rules

All user-visible text must come from:

• `lang/en.json`;
• `lang/ru.json`.

This includes labels, buttons, tooltips, placeholders, dialogs, error messages and logs.

When adding text:

1. Add the key to both language files.
2. Use an English fallback in code.
3. Make sure the relevant `update_language()` updates already-created widgets.
4. Run:

```bash
python tools/check_i18n.py
```

`SettingsTab` has a translation registry for static labels/tooltips. Transcription combo/toggle rows are registered in `_tr_rows`; keep that registration correct when adding rows.

## UI Rules

• Keep visual changes consistent with `clipgen/ui/styles.py`.
• Reuse `StyledComboBox`; it intentionally ignores mouse wheel changes while closed.
• Do not add user-visible text directly in Python unless it is a technical fallback and the real string exists in both language files.
• Do not trigger heavy actions from default/focus button behavior; transcription install/load buttons are guarded against startup Enter/click leakage.
• Keep cards and controls compact; this is a utility app, not a landing page.

## Build Notes

Use:

```bash
py -m PyInstaller --clean ClipGen.spec
```

or:

```bat
build_verbose.bat
```

`ClipGen.spec` intentionally:

• includes language files and icon;
• includes transcription modules as hidden imports;
• excludes heavy ML packages from the main exe;
• excludes NumPy/OpenBLAS from the main exe where possible;
• removes conflicting PyQt5 VC runtime DLLs;
• adds VC runtime DLLs from `C:\Windows\System32`.

If `dist\ClipGen.exe` is locked, close all running `ClipGen.exe` processes before rebuilding.

## Pre-Release Checklist

```bash
python tools/check_i18n.py
python -m compileall clipgen tools/check_i18n.py
py -m PyInstaller --clean ClipGen.spec
```

Manual checks:

• dev launch works;
• exe launch works;
• RU/EN switching updates Settings and transcription controls;
• closed combo boxes do not change on mouse wheel;
• text hotkey processes and pastes output;
• image clipboard path still works;
• voice hotkey records, transcribes and pastes;
• model unload and auto-unload work;
• diagnostics file is generated on transcription failures.

GitHub release notes are bilingual: wrap each language in
`<!-- lang:ru -->...<!-- /lang -->` and `<!-- lang:en -->...<!-- /lang -->`
blocks. The in-app update dialog picks the block matching the UI language
(`extract_localized_notes` in `clipgen/utils/updates.py`); text outside the
blocks appears only on the GitHub release page.

## Versioning

Version is stored in:

• `clipgen/__init__.py`;
• `clipgen/core/constants.py`.

Update both when changing the app version.
