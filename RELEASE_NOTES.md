<!-- lang:ru -->
## Что нового в 2.4.1 и 2.4.2

• Исправлен запуск программы на компьютерах, где в пользовательском Python установлены свои версии пакетов (openai, pydantic и т.п.) — они больше не конфликтуют со встроенными
• Parakeet теперь действительно работает на видеокарте: установщик защищает GPU-библиотеку от перезаписи. Разница огромная — на RTX 3060 фраза на 7–8 секунд речи распознаётся за 0.1 секунды вместо ~1 секунды на процессоре
• Если вы уже установили Parakeet в версии 2.4.0 — программа сама заметит проблему, просто нажмите «Установить / Скачать» ещё раз, и установка починится
• В логах и статусе теперь видно, на чём реально загрузилась модель: CUDA или CPU — никаких догадок

Дальше — всё главное из версии 2.4.0, если вы её пропустили:

## Голосовой ввод

Зажмите горячую клавишу — говорите — отпустите. Распознанный текст мгновенно вставится туда, где стоит курсор: в мессенджер, браузер, редактор кода — куда угодно.

• Распознавание работает полностью на вашем компьютере — голос никуда не отправляется, ни в облако, ни по API
• Поддерживаются русский, английский и десятки других языков, язык определяется автоматически
• Голосовых клавиш может быть несколько: у каждой свой язык, словарь-подсказка для терминов и имён.

Как включить: Настройки → «Голосовая транскрибация» → включите и нажмите «Установить / Скачать» — программа сама установит компоненты и загрузит модель. Затем добавьте действие типа «Голосовая транскрибация» и назначьте клавишу. Понадобится установленный Python 3.10+ (бесплатно с python.org).

## Два движка на выбор

• **Whisper (OpenAI)** — 99 языков, максимум качества. Работает на видеокарте и на процессоре
• **Parakeet (NVIDIA)** — очень быстрый и лёгкий, 25 языков включая русский

Модели скачиваются с прогрессом и возможностью отмены и хранятся в папке Models рядом с программой. Для экономии памяти модель автоматически выгружается после простоя и подгружается при следующем нажатии.

## Статус всегда на виду

• Компактный оверлей в углу экрана: запись → распознавание → готово
• Иконка в трее меняет цвет: красная — идёт запись, жёлтая — распознавание
• Звуковые сигналы начала и конца записи (отключаются в настройках)
• Фильтр «галлюцинаций» отсекает фразы-паразиты, которые модели придумывают на тишине

## Надёжность

• Все служебные процессы гарантированно завершаются вместе с программой — память не «утекает» даже после сбоя или закрытия через диспетчер задач
• Распознавание уверенно стартует на медленных дисках и с активным антивирусом
• Установка компонентов и загрузка моделей не зависают молча: при проблемах вы увидите понятную ошибку
• Окно обновлений показывает новости на языке интерфейса с переключателем Русский/English
<!-- /lang -->

---

## 🇬🇧 English

<!-- lang:en -->
## What's new in 2.4.1 and 2.4.2

• Fixed startup on machines where the user's Python has its own copies of packages (openai, pydantic, etc.) — they no longer conflict with the bundled ones
• Parakeet now truly runs on your GPU: the installer protects the GPU library from being overwritten. The difference is dramatic — on an RTX 3060 a 7–8 second phrase is recognized in 0.1 seconds instead of ~1 second on the CPU
• Already installed Parakeet with 2.4.0? The app will notice the problem itself — just click "Install / Download" once more and the installation fixes itself
• The logs and the status now show where the model actually loaded: CUDA or CPU — no more guessing

Below is everything important from 2.4.0 in case you missed it:

## Voice input

Hold a hotkey — speak — release. The recognized text is instantly pasted right where your cursor is: a messenger, a browser, a code editor — anywhere.

• Recognition runs entirely on your computer — your voice never leaves it, no cloud, no APIs
• Russian, English and dozens of other languages are supported, with automatic language detection
• Set up several voice hotkeys: each with its own language and a hint dictionary for terms and names.

How to enable: Settings → "Voice transcription" → turn it on and click "Install / Download" — the app installs the components and downloads the model for you. Then add a "Voice transcription" action and assign a key. Python 3.10+ is required (free at python.org).

## Two engines to choose from

• **Whisper (OpenAI)** — 99 languages, maximum quality. Runs on GPU and CPU
• **Parakeet (NVIDIA)** — very fast and lightweight, 25 languages including Russian

Models download with a progress bar and can be cancelled; they live in the Models folder next to the app. To save memory the model unloads automatically after idle time and loads back on the next press.

## Status always in sight

• A compact overlay in the corner of the screen: recording → transcribing → done
• The tray icon changes color: red — recording, yellow — transcribing
• Start/stop sound feedback (can be disabled in settings)
• A hallucination filter drops the junk phrases speech models tend to invent on silence

## Reliability

• All helper processes are guaranteed to terminate together with the app — no memory leaks even after a crash or a Task Manager kill
• Recognition starts reliably on slow disks and with active antivirus
• Component installation and model downloads can't hang silently: you get a clear error message
• The update dialog shows release notes in your UI language with a Русский/English switcher
<!-- /lang -->
