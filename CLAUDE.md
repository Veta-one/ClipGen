# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ClipGen is a Windows desktop automation utility that processes text and images via AI APIs (Google Gemini, OpenAI-compatible) through global hotkeys. Users select text, press a hotkey, and the selection is replaced with AI-processed output without context switching.

## Style Guidelines

• **No emojis** — never use emojis in code, documentation, UI, or release notes unless explicitly requested
• **Bullet points** — use `•` character for lists, not `-` or `*`
• **Language** — code comments and git commits in English, user-facing text from language files

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run application
python -m clipgen.main

# Build standalone executable
build_clipgen.bat
```

The build script uses PyInstaller to create a single-file .exe with bundled resources (language files, icon).

## Architecture

### Two-Layer Design

```
ClipGenView (ClipGen_view.py)  →  UI Layer: PyQt5 tabs, tray icon, dialogs
     ↓ inherits
ClipGen (ClipGen.py)           →  Logic Layer: hotkeys, API calls, settings
```

### Threading Model

- **Main thread**: Qt event loop for UI
- **hotkey_listener()**: Background thread using pynput for global keyboard interception
- **queue_worker()**: Processes hotkey events from queue
- **Worker threads**: API calls with cancellation support via `threading.Event`

Thread-safe communication via Qt signals: `log_signal`, `update_model_list_signal`, `start_working_signal`, `success_signal`, `error_signal`.

### Core Workflow

1. `hotkey_listener()` detects key combination via pynput
2. Event pushed to queue, `queue_worker()` retrieves it
3. `handle_text_operation()` simulates Ctrl+C, captures clipboard
4. `process_text_with_gemini()` or OpenAI equivalent makes API call
5. On quota error (429), auto-switches to next API key
6. Result pasted via simulated Ctrl+V

### Key Implementation Details

- **Clipboard handling**: Uses `is_pasting` flag to prevent recursion during Ctrl+C/V simulation
- **API key rotation**: Tracks usage timestamps, auto-switches on 429 errors
- **Image support**: PIL ImageGrab → base64 encoding for multimodal prompts
- **Proxy**: HTTP/SOCKS5 via PySocks integration
- **Settings merge**: Recursive merge of user config with `DEFAULT_CONFIG` for backward compatibility

## Configuration

`settings.json` (auto-generated on first run):
- `provider`: "gemini" or "openai"
- `api_keys` / `openai_api_keys`: List with key, name, active status, usage timestamps
- `hotkeys`: Array of {combination, name, log_color, prompt}
- `language`: "en" or "ru"
- `ui_scale`: 0.8 to 3.0
- `proxy_enabled/proxy_type/proxy_string`: Proxy configuration

Language strings in `lang/ru.json` and `lang/en.json`.

## ⛔ КРИТИЧЕСКОЕ ПРАВИЛО: Локализация UI

> **ВСЕ текстовые элементы интерфейса должны браться ТОЛЬКО из языковых файлов!**

Программа поддерживает русский и английский языки. Пользователь выбирает язык в настройках — интерфейс ДОЛЖЕН полностью переключаться.

**АБСОЛЮТНО ВСЕ** тексты UI должны быть в `lang/en.json` и `lang/ru.json`:
- Надписи, кнопки, заголовки, tooltips, диалоги, placeholder'ы, ошибки, логи

```python
# ✅ ПРАВИЛЬНО
label = QLabel(self.lang.get("settings", {}).get("title", "Settings"))

# ❌ НЕПРАВИЛЬНО — захардкоженный текст
label = QLabel("Настройки")  # НЕТ!
label = QLabel("Settings")   # тоже НЕТ!
```

**При добавлении нового текста:**
1. Добавить ключ в `lang/en.json`
2. Добавить ключ в `lang/ru.json`
3. В коде использовать `self.lang.get("section", {}).get("key", "English fallback")`

## Windows-Specific APIs

- **pywin32**: Keyboard event simulation, registry access (autostart)
- **Win32 DPI**: `SetCurrentProcessExplicitAppUserModelID` for taskbar icon
- **Dark titlebar**: Windows 11 styling via win32api

## Release Process

GitHub Actions (`.github/workflows/release.yml`) auto-builds on version tags (v*). Tags trigger PyInstaller build and .exe upload to Releases.

### Versioning

- **Мелкие изменения** (баги, мелкие правки): `0.0.1` → `0.0.2` — просто пуш в main
- **Крупные изменения** (новые фичи, значимые изменения): `0.0.1` → `0.1.0` — пуш + релиз через GitHub CLI

Версия хранится в `clipgen/__init__.py` и `clipgen/core/constants.py` — обновлять нужно в **обоих** файлах!

## UI Style Guide

### Цветовая палитра

| Назначение | Цвет |
|------------|------|
| Фон окна | `#1e1e1e` |
| Фон карточек | `#252525` |
| Фон кнопок | `#333333` |
| Hover кнопок | `#404040` / `#444444` |
| Pressed кнопок | `#2a2a2a` |
| Рамки | `#444444` |
| Текст | `#FFFFFF` |
| Акцент (focus) | `#A3BFFA` |

### Кнопки

**Стандартная кнопка:**
```python
btn.setStyleSheet("""
    QPushButton { background-color: #333333; border-radius: 8px; padding: 5px 10px; }
    QPushButton:hover { background-color: #444444; }
    QPushButton:pressed { background-color: #2a2a2a; }
""")
```

**Круглая мини-кнопка (18×18):**
```python
btn = QPushButton("•")
btn.setFixedSize(18, 18)
# border-radius: 9px (половина размера)
```

| Тип | Default | Hover |
|-----|---------|-------|
| Добавить | `#3D8948` | `#2A6C34` |
| Удалить | `#FF5F57` | `#FF3B30` |
| Toggle ON | `#3D8948` | `#2A6C34` |
| Toggle OFF | `#676664` | `#DDDDDD` + текст `#000000` |

**Статусные кнопки (тест API/моделей):**

| Статус | Цвет | Hover |
|--------|------|-------|
| not_tested | `#6c757d` | `#5a6268` |
| testing | `#FFC107` | `#E0A800` |
| success | `#28A745` | `#218838` |
| error | `#DC3545` | `#C82333` |

### Поля ввода

```python
input.setStyleSheet("""
    QLineEdit {
        background-color: #2e2e2e;
        border: 1px solid #444444;
        border-radius: 10px;
        padding: 5px;
    }
    QLineEdit:focus { border: 1px solid #A3BFFA; }
""")
```

### Карточки (QFrame)

```python
card.setStyleSheet("background-color: #252525; border-radius: 15px; padding: 10px;")
```

### Правила

1. **border-radius**: 8-10px для кнопок, 10-15px для карточек, 9px для круглых мини-кнопок
2. **Круглые мини-кнопки**: всегда `QPushButton("•")` + `setFixedSize(18, 18)`
3. **Деструктивные действия**: красный hover (`#C82333` или `#FF3B30`)
4. **Позитивные действия**: зелёный (`#28A745` или `#3D8948`)
5. **Отступы**: `padding: 5px 10px` для кнопок, `15px` для контейнеров
