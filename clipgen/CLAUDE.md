# CLAUDE.md — Руководство разработчика ClipGen

Этот файл содержит всю необходимую информацию для доработки и развития проекта.

---

## Обзор проекта

**ClipGen** — Windows-утилита для автоматизации запросов к AI через буфер обмена. Пользователь выделяет текст, нажимает хоткей — текст заменяется на ответ нейросети без переключения окон.

**Поддерживаемые провайдеры:**
• Google Gemini (нативный API)
• OpenAI-compatible (OpenRouter, DeepSeek, локальные модели)

**Технологии:**
• Python 3.10+
• PyQt5 (UI)
• pynput (глобальные хоткеи)
• google-generativeai, openai (API клиенты)

---

## Правила оформления

• **Без эмодзи** — не использовать эмодзи в коде, документации, UI и релизах
• **Буллеты** — использовать символ `•` для списков, не `-` или `*`
• **Язык** — комментарии и коммиты на английском, текст UI из языковых файлов

---

## Команды разработки

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск приложения
python -m clipgen.main

# Сборка exe (PyInstaller)
build_clipgen.bat
```

---

## Архитектура

### Структура модулей

```
clipgen/
├── main.py                   # Точка входа
├── app.py                    # ClipGenApp — главный класс (композиция)
│
├── core/                     # Ядро
│   ├── config.py             # ConfigManager — загрузка/сохранение settings.json
│   ├── constants.py          # DEFAULT_CONFIG, __version__, пути
│   └── list_manager.py       # ConfigListManager — CRUD для списков (ключи, модели)
│
├── api/                      # Работа с AI API
│   ├── base.py               # APIProvider — абстрактный базовый класс
│   ├── gemini.py             # GeminiProvider
│   ├── openai_compat.py      # OpenAIProvider
│   └── processor.py          # TextProcessor — координация вызовов
│
├── hotkeys/                  # Горячие клавиши
│   ├── listener.py           # HotkeyListener — перехват через pynput
│   └── manager.py            # HotkeyManager — CRUD для хоткеев
│
├── testing/                  # Тестирование API
│   └── tester.py             # APITester — проверка ключей и моделей
│
├── ui/                       # Интерфейс (PyQt5)
│   ├── main_window.py        # MainWindow — главное окно с вкладками
│   ├── styles.py             # ⚠️ ВСЕ СТИЛИ ЗДЕСЬ — класс Styles
│   ├── widgets.py            # Переиспользуемые виджеты (StyledComboBox)
│   ├── tray.py               # TrayIconManager — иконка в трее
│   ├── dialogs.py            # CustomMessageBox
│   └── tabs/                 # Вкладки
│       ├── log_tab.py        # Логи
│       ├── settings_tab.py   # Настройки (API, прокси, язык)
│       ├── prompts_tab.py    # Промпты и хоткеи
│       └── help_tab.py       # Помощь
│
└── utils/                    # Утилиты
    ├── i18n.py               # Локализация (en/ru)
    ├── proxy.py              # Настройка прокси
    ├── autostart.py          # Автозапуск Windows (реестр)
    ├── updates.py            # Проверка обновлений GitHub
    └── clipboard.py          # Работа с буфером обмена
```

### Принципы архитектуры

1. **Композиция вместо наследования** — `ClipGenApp` объединяет компоненты
2. **Qt сигналы** — потокобезопасная коммуникация между UI и логикой
3. **Единый источник стилей** — класс `Styles` в `ui/styles.py`
4. **Модульность** — каждый компонент можно тестировать отдельно

### Потоковая модель

```
Main Thread (Qt Event Loop)
    │
    ├── HotkeyListener (daemon thread)
    │       └── pynput keyboard listener
    │
    ├── Queue Worker (daemon thread)
    │       └── обрабатывает события из очереди
    │
    └── API Worker Threads
            └── запросы к Gemini/OpenAI с cancellation
```

**Коммуникация через Qt сигналы:**
- `log_signal(str, str)` — добавить лог (текст, цвет)
- `start_working_signal()` — показать статус "работает"
- `success_signal(str)` — показать статус "успех" (время)
- `error_signal()` — показать статус "ошибка"

---

## Конфигурация

### settings.json

```json
{
    "provider": "gemini",
    "api_keys": [
        {"key": "...", "name": "Main", "active": true, "usage_timestamps": []}
    ],
    "openai_api_keys": [...],
    "openai_base_url": "https://openrouter.ai/api/v1",
    "gemini_models": [{"name": "gemini-2.0-flash"}],
    "openai_models": [{"name": "deepseek/deepseek-chat", "test_status": "not_tested"}],
    "active_model": "gemini-2.0-flash",
    "openai_active_model": "deepseek/deepseek-chat",
    "hotkeys": [
        {
            "combination": "Ctrl+F1",
            "name": "Коррекция",
            "prompt": "Fix grammar...",
            "log_color": "#FFFFFF",
            "use_custom_model": false,
            "custom_provider": null,
            "custom_model": null
        }
    ],
    "language": "ru",
    "ui_scale": 1.0,
    "proxy_enabled": false,
    "proxy_type": "HTTP",
    "proxy_string": ""
}
```

### Локализация

## ⛔ КРИТИЧЕСКОЕ ПРАВИЛО: ВСЕ ТЕКСТОВЫЕ ЭЛЕМЕНТЫ UI — ТОЛЬКО ИЗ ЯЗЫКОВЫХ ФАЙЛОВ!

> **ЭТО СТРОГОЕ ТРЕБОВАНИЕ. НАРУШЕНИЕ НЕДОПУСТИМО.**

Программа поддерживает несколько языков (русский, английский). **АБСОЛЮТНО ВСЕ** текстовые элементы интерфейса должны браться из языковых файлов `lang/en.json` и `lang/ru.json`:

- Надписи (QLabel)
- Тексты кнопок (QPushButton)
- Заголовки окон и вкладок
- Tooltips (подсказки)
- Сообщения в диалогах
- Placeholder'ы в полях ввода
- Тексты меню
- Сообщения об ошибках
- Логи, которые видит пользователь
- **ЛЮБОЙ текст, который видит пользователь**

### Почему это важно

1. Пользователь выбирает язык в настройках — интерфейс ДОЛЖЕН полностью переключаться
2. Захардкоженный текст на русском сломает интерфейс для англоязычных пользователей
3. Захардкоженный текст на английском сломает интерфейс для русскоязычных пользователей

### Как правильно

```python
# ✅ ПРАВИЛЬНО — текст из языкового файла с английским fallback
label = QLabel(self.lang.get("settings", {}).get("action_name_label", "Action name:"))
btn.setToolTip(self.lang.get("tooltips", {}).get("add_hotkey", "Add hotkey"))
btn.setText(self.lang.get("buttons", {}).get("save", "Save"))

# ❌ НЕПРАВИЛЬНО — захардкоженный текст
label = QLabel("Название действия:")  # НЕТ!
label = QLabel("Action name:")         # тоже НЕТ!
btn.setToolTip("Добавить хоткей")      # НЕТ!
```

### Формат с fallback

**Всегда** указывать значение по умолчанию на английском:
```python
self.lang.get("section", {}).get("key", "Default English text")
```

### Чеклист перед коммитом

- [ ] Все новые тексты добавлены в `lang/en.json`
- [ ] Все новые тексты добавлены в `lang/ru.json`
- [ ] Нет захардкоженных строк в UI-коде
- [ ] Метод `update_language()` обновляет все новые тексты

#### Структура языковых файлов

Файлы `lang/en.json` и `lang/ru.json`:

```json
{
    "settings": {
        "action_name_label": "Action name:",
        "prompt_label": "Prompt:",
        "custom_model_label": "Custom model:"
    },
    "logs": {
        "execution_time": "Executed in {seconds:.2f} sec.",
        "app_started": "ClipGen started"
    },
    "dialogs": {
        "confirm_delete_title": "Confirm Deletion",
        "confirm_delete_message": "Are you sure you want to delete '{name}'?"
    },
    "tooltips": {
        "add_hotkey": "Add new hotkey",
        "delete_hotkey": "Delete this hotkey"
    },
    "errors": {
        "empty_clipboard": "Clipboard is empty",
        "api_key_not_set": "API key not configured"
    }
}
```

#### Добавление новой строки

1. Добавить ключ в **оба** файла (`en.json` и `ru.json`)
2. В коде использовать `self.lang.get("section", {}).get("key", "fallback")`
3. Если компонент не имеет `self.lang` — передать через конструктор

#### Метод update_language()

Каждый виджет с текстом должен иметь метод для обновления при смене языка:

```python
def update_language(self, lang: dict) -> None:
    """Update UI text when language changes."""
    self.lang = lang
    self.title_label.setText(
        lang.get("settings", {}).get("title", "Settings")
    )
    self.save_btn.setToolTip(
        lang.get("tooltips", {}).get("save", "Save changes")
    )
```

---

## UI Style Guide

### ⚠️ ГЛАВНОЕ ПРАВИЛО

**Никогда не хардкодить стили!** Всегда использовать класс `Styles` из `ui/styles.py`:

```python
from clipgen.ui.styles import Styles

# ✅ ПРАВИЛЬНО
btn.setStyleSheet(Styles.button())
card.setStyleSheet(Styles.card())
input.setStyleSheet(Styles.input_field())

# ❌ НЕПРАВИЛЬНО
btn.setStyleSheet("background-color: #333; border-radius: 8px;")
```

### Доступные методы Styles

| Метод | Описание |
|-------|----------|
| `Styles.button()` | Стандартная кнопка |
| `Styles.mini_button(color, hover)` | Круглая 18×18 |
| `Styles.add_button()` | Зелёная кнопка добавления |
| `Styles.delete_button()` | Красная кнопка удаления |
| `Styles.toggle_button(active)` | Toggle вкл/выкл |
| `Styles.test_button(status)` | Кнопка теста (success/error/testing) |
| `Styles.input_field()` | Поле ввода QLineEdit |
| `Styles.text_edit()` | Многострочное поле QTextEdit |
| `Styles.card()` | Карточка QFrame |
| `Styles.combo_box()` | Выпадающий список |
| `Styles.scroll_area()` | Область прокрутки |

### Цветовые константы

```python
Styles.BACKGROUND = "#1e1e1e"      # Фон окна
Styles.CARD_BG = "#252525"         # Фон карточек
Styles.BUTTON_BG = "#333333"       # Фон кнопок
Styles.BUTTON_HOVER = "#404040"    # Hover кнопок
Styles.BORDER = "#444444"          # Рамки
Styles.TEXT = "#FFFFFF"            # Текст
Styles.ACCENT = "#A3BFFA"          # Акцент (focus)

Styles.ADD_GREEN = "#3D8948"       # Добавить
Styles.DELETE_RED = "#FF5F57"      # Удалить
Styles.SUCCESS = "#28A745"         # Успех
Styles.ERROR = "#DC3545"           # Ошибка
Styles.WARNING = "#FFC107"         # Предупреждение
```

### Правила UI

| Правило | Значение |
|---------|----------|
| border-radius кнопок | 8-10px |
| border-radius карточек | 15px |
| border-radius круглых кнопок | 9px (при 18×18) |
| Круглые мини-кнопки | `QPushButton("•")` + `setFixedSize(18, 18)` |
| Деструктивные действия | Красный hover |
| Позитивные действия | Зелёный |
| Отступы кнопок | `padding: 5px 10px` |
| Отступы контейнеров | 15px |

---

## Паттерны кода

### Добавление нового провайдера API

1. Создать файл `api/new_provider.py`
2. Унаследоваться от `APIProvider`:

```python
from .base import APIProvider

class NewProvider(APIProvider):
    @property
    def name(self) -> str:
        return "new_provider"

    @property
    def api_keys_key(self) -> str:
        return "new_provider_api_keys"

    @property
    def active_model_key(self) -> str:
        return "new_provider_active_model"

    def get_active_key(self):
        # ...

    def generate(self, prompt, text, cancel_event, is_image=False,
                 image_data=None, model_override=None) -> str:
        # ...

    def reconfigure(self, api_key):
        # ...
```

3. Добавить в `DEFAULT_CONFIG` в `core/constants.py`
4. Зарегистрировать в `ClipGenApp` в `app.py`

### Добавление новой вкладки UI

1. Создать файл `ui/tabs/new_tab.py`:

```python
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import pyqtSignal

class NewTab(QWidget):
    # Сигналы для коммуникации с MainWindow
    something_changed = pyqtSignal(str)

    def __init__(self, config: dict, lang: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.lang = lang
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        # ...

    def update_language(self, lang: dict):
        """Обновить текст при смене языка."""
        self.lang = lang
        # ...
```

2. Добавить в `MainWindow._setup_tabs()`
3. Подключить сигналы в `MainWindow._connect_*_signals()`

### Добавление поля в хоткей

1. Добавить в `DEFAULT_CONFIG["hotkeys"]` в `constants.py`
2. Добавить метод `update_*` в `HotkeyManager` в `hotkeys/manager.py`
3. Добавить UI в `HotkeyCard` в `ui/tabs/prompts_tab.py`
4. Добавить сигнал в `HotkeyCard` и `PromptsTab`
5. Подключить сигнал в `MainWindow._connect_prompts_signals()`
6. Добавить локализацию в `lang/*.json`

### Добавление элемента в настройки

1. Добавить в `DEFAULT_CONFIG` в `constants.py`
2. Добавить UI метод `_add_*_section()` в `SettingsTab`
3. Добавить сигнал в `SettingsTab`
4. Подключить в `MainWindow._connect_settings_signals()`
5. Обработать в `MainWindow._on_*()` методе
6. Добавить локализацию

---

## Сигналы и связи

### Поток данных UI → Logic

```
UI Widget (tab)
    │
    ├── emit signal (e.g., name_changed)
    │
    ▼
MainWindow (connects signals)
    │
    ├── lambda: self.app.manager.update_*(...)
    │
    ▼
Manager (HotkeyManager, ConfigListManager)
    │
    ├── updates config dict
    ├── calls save_callback()
    │
    ▼
ConfigManager.save() → settings.json
```

### Поток данных Logic → UI

```
Background Thread (API call, hotkey event)
    │
    ├── emit Qt signal (log_signal, success_signal)
    │
    ▼
MainWindow (slot connected)
    │
    ├── updates UI widgets
    ├── updates tray icon
    │
    ▼
UI reflects new state
```

---

## Windows-специфичные API

| Модуль | Использование |
|--------|---------------|
| `pywin32` | Симуляция клавиш (Ctrl+C/V), реестр (автозапуск) |
| `ctypes` | `SetCurrentProcessExplicitAppUserModelID` для taskbar |
| `win32api` | Dark titlebar Windows 11 |
| `PySocks` | Прокси HTTP/SOCKS5 |

---

## Версионирование

Версия хранится в `core/constants.py`:

```python
__version__ = "2.2.0"
```

**Правила:**
- Баги, мелкие правки: `2.2.0` → `2.2.1`
- Новые фичи: `2.2.0` → `2.3.0`
- Большие изменения: `2.2.0` → `3.0.0`

**Релиз:**
```bash
git tag v2.2.0
git push origin v2.2.0
```

GitHub Actions автоматически соберёт exe и создаст релиз.

---

## Чеклист перед коммитом

- [ ] Стили через `Styles.*`, не хардкод
- [ ] Новые строки добавлены в `lang/en.json` и `lang/ru.json`
- [ ] Сигналы подключены в `MainWindow`
- [ ] `DEFAULT_CONFIG` обновлён если добавлены новые настройки
- [ ] Код работает: `python -m clipgen.main`

---

*Последнее обновление: 2026-01-31, версия 2.2.0*
