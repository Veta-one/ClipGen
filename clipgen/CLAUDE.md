# CLAUDE.md — ClipGen Developer Guide

This is the package-level developer guide. The root `CLAUDE.md` contains the same current project rules in shorter form; keep both files consistent when architecture or build rules change.

## Current State

ClipGen `2.4.2` is a Windows PyQt5 utility for AI actions through global hotkeys:

• text/image clipboard processing through Gemini or OpenAI-compatible providers;
• configurable hotkeys and prompts;
• per-hotkey model/provider overrides;
• learning mode explanation popup;
• optional push-to-talk Whisper transcription;
• RU/EN runtime localization.

## Commands

```bash
pip install -r requirements.txt
python -m clipgen.main
python tools/check_i18n.py
python -m compileall clipgen tools/check_i18n.py
py -m PyInstaller --clean ClipGen.spec
```

Verbose exe build:

```bat
build_verbose.bat
```

Use `ClipGen.spec` as the source of truth for PyInstaller. Do not regenerate it with a generic PyInstaller command unless you reapply the current hidden imports, exclusions and VC runtime filtering.

## Module Map

```text
clipgen/
  main.py                  application entry
  app.py                   composition root, queue worker, lifecycle
  core/
    config.py              settings load/save/migration
    constants.py           DEFAULT_CONFIG, version, app paths
  api/
    base.py
    gemini.py
    openai_compat.py
    processor.py           text/image clipboard AI processing
  hotkeys/
    listener.py            pynput global hotkey listener
    manager.py             CRUD for hotkeys
  testing/
    tester.py              API key/model tests
  transcription/
    __init__.py            lazy-import package boundary
    audio_recorder.py      microphone capture and stream status
    cuda_setup.py          CUDA DLL path helpers
    deps.py                optional dependency install/check
    diagnostics.py         diagnostics report writer
    download_worker.py     external HF file download helper
    filters.py             hallucination filtering
    model_manager.py       model/download/inference state machine
    transcriber.py         push-to-talk workflow
    worker_client.py       isolated Whisper worker process client
  ui/
    main_window.py         main window, Qt signals, transcription handlers
    overlay.py             top-right transcription overlay
    styles.py              shared style constants
    tray.py                tray states
    widgets.py             shared widgets
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
    process_guard.py       child-process lifetime guard (job object, orphan sweep)
```

## Runtime Flow

Text/image hotkey:

1. `HotkeyListener` detects a configured combination.
2. Event goes into `ClipGenApp.hotkey_queue`.
3. `queue_worker` dispatches text action.
4. `TextProcessor` copies clipboard, calls provider, pastes result.
5. UI and tray are updated through Qt signals.

Voice hotkey:

1. `HotkeyListener` emits `transcription_start` on press.
2. `Transcriber` ensures model readiness, opens microphone and starts recording.
3. Releasing any key in the active combo emits `transcription_stop`.
4. Audio is preprocessed, transcribed and pasted.
5. Overlay/tray/logs receive status updates through signals.

## Threading Rules

• Qt widgets and `QTimer` must be owned and controlled on the Qt main thread.
• Background threads communicate through Qt signals or thread-safe queues.
• Whisper inference is isolated by default using `WhisperWorkerClient`.
• `WhisperModelManager` uses generation tokens to ignore obsolete loads/downloads.
• Download cancellation uses `threading.Event`.

Do not call UI methods directly from worker threads.

## Transcription Notes

The speech stack is optional. It is intentionally not bundled into the main exe.

Default config:

```json
{
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
  "feedback_sounds": true
}
```

Operational behavior:

• dependencies install through Settings;
• models download into `Models/`;
• download can be cancelled;
• model load can fall back from CUDA to CPU;
• diagnostics are written to `transcription_diagnostics.txt`;
• recording has a max duration from config;
• common hallucination phrases are filtered;
• model can auto-unload after idle time.

## Localization

All user-visible text must live in `lang/en.json` and `lang/ru.json`.

This includes:

• labels;
• buttons;
• tooltips;
• placeholders;
• dialogs;
• error text;
• logs;
• overlay/tray text.

Rules:

• add every key to both language files;
• use English fallbacks in Python;
• ensure `update_language()` updates existing widgets;
• for `SettingsTab`, register static labels/tooltips through the translation registry;
• for transcription rows, register `_tr_rows` with a stable row id and translation key;
• run `python tools/check_i18n.py`.

## UI/UX Rules

• Use `Styles` and existing widget patterns.
• Use `StyledComboBox` for combo boxes; closed combos must ignore wheel events.
• Avoid accidental heavy actions on startup; transcription load/install buttons are guarded.
• Do not introduce large visual redesigns without a product reason.
• The app is a compact desktop utility; dense, readable controls are preferred.

## Build Rules

`ClipGen.spec` is required because it:

• adds all current hidden imports;
• includes `lang/` and `ClipGen.ico`;
• excludes heavy ML modules from the core exe;
• includes transcription worker/download/diagnostics modules;
• removes conflicting PyQt5 VC runtime DLLs;
• adds current VC runtime DLLs from `System32`.

If a build fails with `PermissionError`, check for running `ClipGen.exe` processes and close them before rebuilding.

## Checks

Before handing off a release build:

```bash
python tools/check_i18n.py
python -m compileall clipgen tools/check_i18n.py
py -m PyInstaller --clean ClipGen.spec
```

Manual smoke test:

• launch dev mode;
• launch exe;
• switch RU/EN and inspect Settings, Prompts and transcription controls;
• verify combo wheel protection;
• run a text hotkey;
• run a voice hotkey;
• load/unload Whisper model;
• check diagnostics on failure.

Release notes on GitHub use bilingual blocks
(`<!-- lang:ru -->...<!-- /lang -->`, `<!-- lang:en -->...<!-- /lang -->`);
the update dialog shows only the block matching the UI language.

## Version

Update both:

• `clipgen/__init__.py`;
• `clipgen/core/constants.py`.
