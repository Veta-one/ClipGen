import os
import sys
import time
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTextBrowser, QStackedWidget, QLineEdit, QTextEdit, QLabel, QScrollArea, 
                             QFrame, QDialog, QColorDialog, QComboBox, QKeySequenceEdit, QMessageBox,
                             QRadioButton, QButtonGroup, QSystemTrayIcon, QMenu, QAction, QSizePolicy) 
from PyQt5.QtGui import QTextCursor, QColor, QIcon, QPainter, QFont, QPixmap
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QPoint, QSize

import pyperclip

def resource_path(relative_path):
    """Возвращает правильный путь к ресурсу, работает и в .py, и в .exe."""
    try:
        # PyInstaller создает временную папку и сохраняет путь в _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class CustomMessageBox(QDialog):
    """Кастомное диалоговое окно в стиле приложения."""
    def __init__(self, parent, title, text, yes_text="Yes", no_text="No"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        
        self.setMinimumWidth(400) 

        # Применяем темную тему к заголовку
        parent.set_dark_titlebar(int(self.winId()))

        # Главный слой
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # Текст сообщения
        message_label = QLabel(text)
        message_label.setWordWrap(True) # Автоматический перенос текста
        main_layout.addWidget(message_label)

        # Слой для кнопок
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # Кнопка "ДА" (или "ОК")
        self.yes_button = QPushButton(yes_text)
        self.yes_button.setObjectName("acceptButton") # Для стилизации
        self.yes_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.yes_button.clicked.connect(self.accept) # Возвращает 1
        button_layout.addWidget(self.yes_button)

        # Кнопка "НЕТ" (или "Отмена")
        self.no_button = QPushButton(no_text)
        self.no_button.setObjectName("rejectButton") # Для стилизации
        self.no_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.no_button.clicked.connect(self.reject) # Возвращает 0
        button_layout.addWidget(self.no_button)
        
        main_layout.addLayout(button_layout)

        # Применение стилей
        self.setStyleSheet("""
            QDialog {
                background-color: #252525;
                border: 1px solid #444444;
            }
            QLabel {
                color: #FFFFFF;
                font-size: 12px; 
                background-color: transparent;
            }
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-size: 12px;
                padding: 10px 0;
                min-height: 16px;
            }
            QPushButton#rejectButton:hover {
                background-color: #3D8948; /* Зеленый */
            }
            QPushButton#acceptButton:hover {
                background-color: #C82333; /* Красный */
            }
        """)

class FocusExpandingTextEdit(QTextEdit):
    focusIn = pyqtSignal()

    def focusInEvent(self, event):
        # Сообщаем, что на нас кликнули
        self.focusIn.emit()
        # Выполняем стандартное поведение
        super().focusInEvent(event)

class ClipGenView(QMainWindow):
    log_signal = pyqtSignal(str, str)
    flash_tray_signal = pyqtSignal() 

    def __init__(self):
        super().__init__()
        self.model_time_labels = {}
        # --- НАЧАЛО ИСПРАВЛЕННОГО БЛОКА ---
        # Устанавливаем иконку для всего приложения (окно, панель задач)
        # используя правильный путь, который работает и в .py, и в .exe
        icon_path = resource_path("ClipGen.ico")
        if os.path.exists(icon_path):
            app_icon = QIcon(icon_path)
            self.setWindowIcon(app_icon)
            # Эта строка важна для иконки на панели задач
            from PyQt5.QtWidgets import QApplication
            QApplication.instance().setWindowIcon(app_icon)
        else:
            print(f"Главная иконка не найдена по пути: {icon_path}")
        # --- КОНЕЦ ИСПРАВЛЕННОГО БЛОКА ---
        
        self.setWindowTitle(self.lang["app_title"])
        self.setGeometry(100, 100, 554, 632)
        self.setMinimumSize(300, 200)

        # Apply styles
        self.apply_styles()

        # Main widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)  # Add some space between elements

        # Create UI elements
        self.setup_buttons()
        self.setup_tabs()
        
        # Connect logs with colors via signals
        self.log_signal.connect(self.append_log)
        
        # Button update on resize
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.update_buttons)

        # Системный трей
        self.setup_tray_icon()

    def setup_buttons(self):
        self.button_widget = QWidget()
        self.button_layout = QVBoxLayout(self.button_widget)
        self.button_layout.setAlignment(Qt.AlignTop)
        self.button_layout.setSpacing(5)
        self.layout.addWidget(self.button_widget, stretch=0)

        self.buttons = {}
        self.update_buttons()

    def setup_tabs(self):
        # Create a stacked widget to hold pages
        self.content_stack = QStackedWidget(self)
        
        # Create navigation buttons layout
        nav_widget = QWidget()
        nav_layout = QHBoxLayout(nav_widget)
        nav_layout.setContentsMargins(15, 5, 15, 5)
        
        # Create Buttons
        self.logs_button = QPushButton(self.lang["tabs"]["logs"])
        self.logs_button.setToolTip(self.lang["tooltips"]["logs_tab"])
        
        self.settings_button = QPushButton(self.lang["tabs"]["settings"])
        self.settings_button.setToolTip(self.lang["tooltips"]["settings_tab"])
        
        # --- НОВАЯ КНОПКА ---
        self.prompts_button = QPushButton(self.lang["tabs"]["prompts"])
        self.prompts_button.setToolTip("Настройка горячих клавиш и промптов")
        
        self.help_button = QPushButton(self.lang["tabs"]["help"])
        self.help_button.setToolTip(self.lang["tooltips"]["help_tab"])
        
        # Style buttons
        button_style = """
            QPushButton {
                background-color: #333333;
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
                min-width: 80px;
            }
            QPushButton:hover { background-color: #444444; color: #FFFFFF; }
            QPushButton:pressed { background-color: #2a2a2a; }
            QPushButton[active="true"] { background-color: #4A4A4A; }
        """
        
        self.logs_button.setStyleSheet(button_style)
        self.settings_button.setStyleSheet(button_style)
        self.prompts_button.setStyleSheet(button_style)
        self.help_button.setStyleSheet(button_style)
        
        # Connect button signals (Индексы: 0=Logs, 1=Settings, 2=Prompts, 3=Help)
        self.logs_button.clicked.connect(lambda: self.switch_page(0))
        self.settings_button.clicked.connect(lambda: self.switch_page(1))
        self.prompts_button.clicked.connect(lambda: self.switch_page(2))
        self.help_button.clicked.connect(lambda: self.switch_page(3))
        
        # Add buttons to navigation layout
        nav_layout.addWidget(self.logs_button)
        nav_layout.addWidget(self.settings_button)
        nav_layout.addWidget(self.prompts_button)
        nav_layout.addWidget(self.help_button)
        nav_layout.addStretch()

        # Кнопка пина
        self.pin_button = QPushButton("•")
        self.pin_button.setToolTip(self.lang["tooltips"]["pin_window"])
        self.pin_button.setFixedSize(28, 28)
        self.pin_button.setObjectName("pinButton")
        self.pin_button.setStyleSheet("""
            QPushButton#pinButton {
                font-size: 16px; background-color: transparent; border: none; color: #888888;
            }
            QPushButton#pinButton:hover { color: #A3BFFA; }
        """)
        nav_layout.addWidget(self.pin_button)
        
        self.layout.addWidget(nav_widget)
        self.layout.addWidget(self.content_stack, 1)
        
        # Create pages (ВАЖЕН ПОРЯДОК!)
        self.setup_log_tab()      # Index 0
        self.setup_settings_tab() # Index 1
        self.setup_prompts_tab()  # Index 2
        self.setup_help_tab()     # Index 3
        
        self.switch_page(0)

    def switch_page(self, index):
        self.content_stack.setCurrentIndex(index)
        
        # Update button states
        self.logs_button.setProperty("active", index == 0)
        self.settings_button.setProperty("active", index == 1)
        self.prompts_button.setProperty("active", index == 2)
        self.help_button.setProperty("active", index == 3)
        
        # Force style update
        for btn in [self.logs_button, self.settings_button, self.prompts_button, self.help_button]:
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        
    def setup_log_tab(self):
        self.log_tab = QWidget()
        self.log_layout = QVBoxLayout(self.log_tab)
        self.log_layout.setContentsMargins(15, 15, 15, 15)
        
        # Create content widget
        log_content = QWidget()
        log_content_layout = QVBoxLayout(log_content)
        log_content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Log area
        self.log_area = QTextBrowser()
        self.log_area.setStyleSheet("""
            background-color: #252525; 
            color: #FFFFFF; 
            border: none; 
            border-radius: 10px;
            padding: 15px;
            line-height: 1.5;
            font-family: 'Consolas', 'Courier New', monospace;
            selection-background-color: #A3BFFA;
            selection-color: #1e1e1e;
        """)
        self.log_area.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse)
        self.log_area.setCursorWidth(2)
        log_content_layout.addWidget(self.log_area)
        
        # Log action buttons
        log_actions = QHBoxLayout()
        self.clear_logs_button = QPushButton(self.lang["logs"]["clear_logs"])
        self.clear_logs_button.setToolTip(self.lang["tooltips"]["clear_logs"])
        self.clear_logs_button.clicked.connect(lambda: self.log_area.clear())
        self.clear_logs_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
                max-width: 150px;
            }
            QPushButton:hover {
                background-color: #444444;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
        """)
        log_actions.addWidget(self.clear_logs_button)
        
        # (Кнопка clear_logs_button остается выше без изменений)
        
        self.check_updates_button = QPushButton(self.lang["logs"]["check_updates"])
        self.check_updates_button.setToolTip("Проверить наличие новой версии на GitHub")
        # Обработчик подключим в ClipGen.py, здесь только создание
        self.check_updates_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
                max-width: 150px;
            }
            QPushButton:hover {
                background-color: #444444;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
        """)
        log_actions.addWidget(self.check_updates_button)

        # Новая кнопка "Остановить"
        self.stop_task_button = QPushButton(self.lang["logs"]["stop_task"])
        self.stop_task_button.setToolTip(self.lang["tooltips"]["stop_task"])
        self.stop_task_button.clicked.connect(self.stop_current_task)
        self.stop_task_button.setStyleSheet("""
            QPushButton {
                background-color: #333333; /* Default gray color */
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
                max-width: 150px;
            }
            QPushButton:hover {
                background-color: #c82333; /* Red on hover */
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #a01c29;
            }
        """)
        log_actions.addWidget(self.stop_task_button)

        # Новая кнопка "Инструкция"
        self.instructions_button = QPushButton(self.lang["logs"]["instructions"])
        self.instructions_button.setToolTip(self.lang["tooltips"]["instructions"])
        self.instructions_button.clicked.connect(self.show_instructions)
        self.instructions_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
                max-width: 150px;
            }
            QPushButton:hover {
                background-color: #444444;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
        """)
        log_actions.addWidget(self.instructions_button)
        log_actions.addStretch()
        
        log_content_layout.addLayout(log_actions)
        
        # Create QScrollArea and set content widget
        self.log_scroll = QScrollArea()
        self.log_scroll.setWidget(log_content)
        self.log_scroll.setWidgetResizable(True)
        
        # Styles for scrollbar - thin and more visible
        self.log_scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent; 
                border: none;
            }
            QScrollBar:vertical {
                background: #1e1e1e;
                width: 4px;
                margin: 0px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: #666666;
                min-height: 20px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: #888888;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { 
                background: none; 
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { 
                background: none; 
            }
            QWidget#qt_scrollarea_viewport {
                background-color: transparent;
            }
        """)
        
        # Add QScrollArea to the main tab layout
        self.log_layout.addWidget(self.log_scroll)
        
        # Add to content stack instead of tabs
        self.content_stack.addWidget(self.log_tab)

    def show_instructions(self):
        """Отображает инструкцию по использованию в логах"""
        # Этот метод только определен здесь, но реализация будет в ClipGen.py
        pass

    def setup_settings_tab(self):
        self.settings_tab = QWidget()
        self.settings_tab.setStyleSheet("background-color: #1e1e1e;")
        self.settings_layout = QVBoxLayout(self.settings_tab)
        self.settings_layout.setSpacing(15)
        self.settings_layout.setContentsMargins(15, 15, 15, 15)
        
        # --- БЛОК ПРОКСИ ---
        proxy_group = QFrame()
        proxy_group.setStyleSheet("background-color: #252525; border-radius: 10px; padding: 5px;")
        proxy_layout = QVBoxLayout(proxy_group)
        proxy_layout.setSpacing(10)

        # Верхняя строка: Заголовок + Чекбокс
        top_row = QHBoxLayout()
        # ИЗМЕНЕНО: Берём текст из JSON
        proxy_label = QLabel(self.lang["settings"]["proxy_title"])
        proxy_label.setStyleSheet("border: none;")
        top_row.addWidget(proxy_label)
        top_row.addStretch()

        from PyQt5.QtWidgets import QCheckBox, QComboBox
        
        # Добавляем текстовую метку
        # ИЗМЕНЕНО: Берём текст из JSON
        enable_label = QLabel(self.lang["settings"]["proxy_enable_label"])
        enable_label.setStyleSheet("color: #FFFFFF; border: none;")
        top_row.addWidget(enable_label)

        # Создаем круглую кнопку-переключатель
        self.proxy_enable_check = QPushButton("•")
        self.proxy_enable_check.setFixedSize(18, 18)
        self.proxy_enable_check.setCheckable(True)
        self.proxy_enable_check.setChecked(self.config.get("proxy_enabled", False))
        
        # Функция для обновления цвета кнопки
        def update_proxy_btn_style(checked):
            if checked:
                # ВАЖНО: padding: 0px убирает глобальный отступ и точка становится маленькой и по центру
                self.proxy_enable_check.setStyleSheet("""
                    QPushButton { 
                        background-color: #3D8948; 
                        color: white; 
                        border-radius: 9px; 
                        font-weight: bold; 
                        font-size: 5px;
                        margin: 0px;
                        border: none;
                    }
                    QPushButton:hover { background-color: #2A6C34; }
                """)
            else:
                self.proxy_enable_check.setStyleSheet("""
                    QPushButton { 
                        background-color: #676664; 
                        color: #FFFFFF; 
                        border-radius: 9px; 
                        font-weight: bold; 
                        font-size: 5px;
                        margin: 0px;
                        border: none;
                    }
                    QPushButton:hover { background-color: #DDDDDD; color: #000000; }
                """)
        
        update_proxy_btn_style(self.proxy_enable_check.isChecked())
        self.proxy_enable_check.toggled.connect(update_proxy_btn_style)
        
        self.proxy_enable_check.toggled.connect(self.toggle_proxy_enable)
        top_row.addWidget(self.proxy_enable_check)
        proxy_layout.addLayout(top_row)

        # Нижняя строка: Тип + Поле ввода
        input_row = QHBoxLayout()
        input_row.setSpacing(10)

        self.proxy_type_combo = QComboBox()
        self.proxy_type_combo.addItems(["HTTP", "SOCKS5"])
        current_type = self.config.get("proxy_type", "HTTP")
        index = self.proxy_type_combo.findText(current_type)
        if index >= 0: self.proxy_type_combo.setCurrentIndex(index)
        self.proxy_type_combo.setFixedWidth(80)
        self.proxy_type_combo.setStyleSheet("""
            QComboBox { background-color: #333; color: white; border: 1px solid #444; border-radius: 5px; padding: 5px; }
            QComboBox::drop-down { border: none; }
        """)
        self.proxy_type_combo.currentTextChanged.connect(self.update_proxy_type)
        input_row.addWidget(self.proxy_type_combo)

        self.proxy_input = QLineEdit(self.config.get("proxy_string", ""))
        self.proxy_input.setPlaceholderText("user:pass@ip:port")
        self.proxy_input.setStyleSheet("""
            QLineEdit { background-color: #2a2a2a; color: white; border: 1px solid #444; border-radius: 5px; padding: 5px; }
        """)
        self.proxy_input.textChanged.connect(self.update_proxy_string)
        input_row.addWidget(self.proxy_input)
        proxy_layout.addLayout(input_row)
        
        hint = QLabel(self.lang["settings"]["proxy_hint"])
        hint.setStyleSheet("color: #666; font-size: 10px; border: none; margin-left: 2px;")
        proxy_layout.addWidget(hint)

        self.update_proxy_ui_state(self.config.get("proxy_enabled", False))
        self.settings_layout.addWidget(proxy_group)
        # --- КОНЕЦ БЛОКА ПРОКСИ ---
        
        # --- API Keys ---
        api_key_container = QFrame()
        api_key_container.setStyleSheet("QFrame { background-color: transparent; border-radius: 10px; padding: 0px; }")
        api_key_main_layout = QVBoxLayout(api_key_container)
        api_key_main_layout.setContentsMargins(0, 10, 0, 10)
        api_key_main_layout.setSpacing(10)

        header_row = QHBoxLayout()
        self.api_key_label = QLabel(self.lang["settings"]["api_key_label"])
        self.api_key_label.setStyleSheet("font-size: 16px;")
        header_row.addWidget(self.api_key_label)

        self.toggle_keys_button = QPushButton("•")
        self.toggle_keys_button.setFixedSize(18, 18)
        self.toggle_keys_button.setToolTip(self.lang["tooltips"]["toggle_keys_visibility"])
        self.toggle_keys_button.setStyleSheet("""
            QPushButton { background-color: #676664; color: #FFFFFF; border-radius: 9px; font-weight: bold; font-size: 10px; }
            QPushButton:hover { background-color: #DDDDDD; }
        """)
        self.toggle_keys_button.clicked.connect(self.toggle_api_key_visibility)
        header_row.addWidget(self.toggle_keys_button)
        
        self.auto_switch_button = QPushButton("•")
        self.auto_switch_button.setFixedSize(18, 18)
        self.auto_switch_button.setToolTip(self.lang["tooltips"]["auto_switch_keys"])
        self.auto_switch_button.clicked.connect(self.toggle_auto_switch)
        header_row.addWidget(self.auto_switch_button)

        self.add_key_button = QPushButton("•")
        self.add_key_button.setFixedSize(18, 18)
        self.add_key_button.setToolTip(self.lang["tooltips"]["add_api_key"])
        self.add_key_button.setStyleSheet("""
            QPushButton { background-color: #3D8948; color: white; border-radius: 9px; font-weight: bold; font-size: 10px; }
            QPushButton:hover { background-color: #2A6C34; }
        """)
        self.add_key_button.clicked.connect(self.add_api_key_entry)
        header_row.addWidget(self.add_key_button)
        header_row.addStretch()

        # Language
        language_layout = QHBoxLayout()
        self.language_label = QLabel(self.lang["settings"]["language_label"])
        language_layout.addWidget(self.language_label)
        self.language_combo = QComboBox()
        self.language_combo.setToolTip(self.lang["tooltips"]["language_selection"])
        self.language_combo.setMinimumWidth(100)
        self.language_combo.setStyleSheet("border-radius: 8px; border: 1px solid #444444; padding: 5px; background-color: #2a2a2a; color: white;")
        for lang in self.get_available_languages():
            self.language_combo.addItem(lang)
        current_index = self.language_combo.findText(self.config.get("language", "en"))
        if current_index >= 0: self.language_combo.setCurrentIndex(current_index)
        self.language_combo.currentTextChanged.connect(self.update_language)
        language_layout.addWidget(self.language_combo)
        header_row.addLayout(language_layout)
        
        api_key_main_layout.addLayout(header_row)

        self.api_keys_layout = QVBoxLayout()
        self.api_keys_layout.setSpacing(5)
        self.key_radio_group = QButtonGroup(self)
        self.key_radio_group.buttonClicked[int].connect(self.set_active_api_key_index)
        self.refresh_api_key_list()
        
        api_key_main_layout.addLayout(self.api_keys_layout)
        self.settings_layout.addWidget(api_key_container)

        # --- Models ---
        self.setup_model_selection_ui()
        
        self.settings_layout.addStretch()
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidget(self.settings_tab)
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setStyleSheet("""
            QScrollArea { background-color: transparent; border: none; }
            QScrollBar:vertical { background: #1e1e1e; width: 4px; margin: 0px; border-radius: 2px; }
            QScrollBar::handle:vertical { background: #666666; min-height: 20px; border-radius: 2px; }
            QWidget#qt_scrollarea_viewport { background-color: transparent; }
        """)

        self.content_stack.addWidget(self.settings_scroll)
        # Инициализация кнопки автосмены
        if hasattr(self, 'config'):
             is_active = self.config.get("auto_switch_api_keys", False)
             color = "#5085D0" if is_active else "#676664"
             self.auto_switch_button.setStyleSheet(f"""
                QPushButton {{ background-color: {color}; color: #FFFFFF; border-radius: 9px; font-weight: bold; font-size: 10px; }}
                QPushButton:hover {{ background-color: #DDDDDD; color: #000000; }}
            """)
        
    def setup_prompts_tab(self):
        """Создает вкладку с настройкой промптов и горячих клавиш"""
        self.prompts_tab = QWidget()
        self.prompts_tab.setStyleSheet("background-color: #1e1e1e;")
        self.prompts_layout = QVBoxLayout(self.prompts_tab)
        self.prompts_layout.setSpacing(15)
        self.prompts_layout.setContentsMargins(15, 15, 15, 15)

        # Заголовок
        self.hotkeys_title = QLabel(self.lang["settings"]["hotkeys_title"])
        self.hotkeys_title.setStyleSheet("font-size: 16px;")
        self.prompts_layout.addWidget(self.hotkeys_title)
        
        # Контейнер для списка
        self.hotkeys_list_layout = QVBoxLayout()
        self.hotkeys_list_layout.setSpacing(10)
        self.prompts_layout.addLayout(self.hotkeys_list_layout)

        # Заполнение списка (Метод refresh_hotkey_list должен уже существовать)
        self.refresh_hotkey_list()
        
        # Кнопка добавления
        hotkey_buttons_layout = QHBoxLayout()
        self.add_hotkey_button = QPushButton(self.lang["settings"]["add_hotkey_button"])
        self.add_hotkey_button.setToolTip(self.lang["tooltips"]["add_hotkey"])
        self.add_hotkey_button.setStyleSheet("""
            QPushButton {
                background-color: #3D8948;
                color: white;
                border-radius: 8px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2A6C34; }
        """)
        self.add_hotkey_button.clicked.connect(self.add_new_hotkey)
        hotkey_buttons_layout.addWidget(self.add_hotkey_button)
        hotkey_buttons_layout.addStretch()
        self.prompts_layout.addLayout(hotkey_buttons_layout)
        
        self.prompts_layout.addStretch()
        
        # Скролл
        self.prompts_scroll = QScrollArea()
        self.prompts_scroll.setWidget(self.prompts_tab)
        self.prompts_scroll.setWidgetResizable(True)
        self.prompts_scroll.setStyleSheet("""
            QScrollArea { background-color: transparent; border: none; }
            QScrollBar:vertical { background: #1e1e1e; width: 4px; border-radius: 2px; }
            QScrollBar::handle:vertical { background: #666666; min-height: 20px; border-radius: 2px; }
            QWidget#qt_scrollarea_viewport { background-color: transparent; }
        """)

        self.content_stack.addWidget(self.prompts_scroll)

    def update_proxy_ui_state(self, enabled):
        """Блокирует/разблокирует поля ввода"""
        self.proxy_type_combo.setEnabled(enabled)
        self.proxy_input.setEnabled(enabled)
        # Делаем визуально прозрачнее, если выключено
        opacity = "1.0" if enabled else "0.5"
        self.proxy_type_combo.setStyleSheet(self.proxy_type_combo.styleSheet() + f"QComboBox {{ opacity: {opacity}; }}")
        self.proxy_input.setStyleSheet(self.proxy_input.styleSheet() + f"QLineEdit {{ opacity: {opacity}; }}")

    # Эти методы мы переопределим в ClipGen.py для логики, 
    # но здесь они нужны, чтобы интерфейс не падал
    def toggle_proxy_enable(self, checked):
        self.config["proxy_enabled"] = checked
        self.update_proxy_ui_state(checked)
        self.save_settings()

    def update_proxy_type(self, text):
        self.config["proxy_type"] = text
        self.save_settings()

    def update_proxy_string(self, text):
        self.config["proxy_string"] = text.strip()
        self.save_settings()

    def toggle_api_key_visibility(self):
        """Переключает видимость API ключей и сохраняет состояние."""
        # 1. Получаем текущее состояние и инвертируем его
        current_state = self.config.get("api_keys_visible", False)
        new_state_is_visible = not current_state

        # 2. Сохраняем новое состояние в конфиг
        self.update_api_key_visibility(new_state_is_visible)

        # 3. Применяем новое состояние ко всем полям ввода
        for key_input in self.api_key_inputs:
            if new_state_is_visible:
                key_input.setEchoMode(QLineEdit.Normal)
            else:
                key_input.setEchoMode(QLineEdit.Password)

    def setup_model_selection_ui(self):
        """Создает UI блок для выбора, добавления и удаления моделей Gemini."""
        model_container = QFrame()
        model_container.setStyleSheet("background-color: transparent;")
        model_layout = QVBoxLayout(model_container)
        model_layout.setContentsMargins(0, 10, 0, 10)
        model_layout.setSpacing(10)

        # --- Заголовок и кнопка "Добавить" ---
        header_layout = QHBoxLayout()
        models_label = QLabel(self.lang["settings"]["gemini_models_label"])
        models_label.setStyleSheet("font-size: 16px;")
        header_layout.addWidget(models_label)
        
        self.add_model_button = QPushButton("•")
        self.add_model_button.setFixedSize(18, 18)
        self.add_model_button.setToolTip(self.lang["tooltips"]["add_model"])
        self.add_model_button.setStyleSheet("""
            QPushButton { background-color: #3D8948; color: white; border-radius: 9px; font-weight: bold; font-size: 10px; }
            QPushButton:hover { background-color: #2A6C34; }
        """)
        self.add_model_button.clicked.connect(self.add_new_model)
        header_layout.addWidget(self.add_model_button)
        header_layout.addStretch()
        model_layout.addLayout(header_layout)

        # --- Область со списком моделей ---
        self.models_list_layout = QVBoxLayout()
        self.models_list_layout.setSpacing(5)
        self.model_radio_group = QButtonGroup(self)
        self.model_radio_group.buttonClicked[int].connect(self.set_active_model)
        
        model_layout.addLayout(self.models_list_layout)
        self.settings_layout.addWidget(model_container)

        # --- Первичное заполнение списка ---
        self.refresh_model_list()

    def refresh_model_list(self):
        """Очищает и заново отрисовывает только список моделей."""
        # Очищаем старые виджеты
        while self.models_list_layout.count():
            child = self.models_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Сбрасываем группу кнопок
        for button in self.model_radio_group.buttons():
            self.model_radio_group.removeButton(button)

        all_models = self.config.get("gemini_models", [])
        active_model = self.config.get("active_model", "")

        for i, model_data in enumerate(all_models):
            model_name = model_data.get("name", "")
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)

            radio = QRadioButton()
            radio.setToolTip(self.lang["tooltips"]["select_model"])
            radio.setChecked(model_name == active_model)
            radio.setFixedSize(18, 18)
            radio.setStyleSheet("""
                QRadioButton::indicator { width: 18px; height: 18px; border-radius: 9px; }
                QRadioButton::indicator:unchecked { background-color: #353535; }
                QRadioButton::indicator:unchecked:hover { background-color: #4f4f4f; }
                QRadioButton::indicator:checked { background-color: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #FFFFFF, stop:0.1 #FFFFFF, stop:0.21 #5085D0, stop:1 #5085D0); }
            """)
            self.model_radio_group.addButton(radio, i)
            row_layout.addWidget(radio)

            name_input = QLineEdit(model_name)
            name_input.setStyleSheet("border-radius: 8px; border: 1px solid #444444; padding: 5px; background-color: #2a2a2a; color: #FFFFFF;")
            name_input.textChanged.connect(lambda text, idx=i: self.update_model_name(idx, text))
            row_layout.addWidget(name_input, 1)

            test_time = self.model_test_times.get(i, 0.0)
            time_text = f"{test_time:.1f}s" if test_time > 0 else "0.0s"
            if self.model_test_statuses.get(i) == 'error':
                time_text = "err"

            time_label = QLabel(time_text)
            time_label.setToolTip(self.lang["tooltips"]["model_test_time_tooltip"])
            time_label.setStyleSheet("color: #888888; font-size: 12px;")
            time_label.setFixedWidth(50)
            time_label.setAlignment(Qt.AlignCenter)
            row_layout.addWidget(time_label)
            self.model_time_labels[i] = time_label

            test_btn = QPushButton("•")
            test_btn.setToolTip("Проверить модель, отправив тестовый запрос")
            test_btn.setFixedSize(18, 18)
            test_btn.clicked.connect(lambda _, idx=i: self.start_model_test(idx))
            
            status = self.model_test_statuses.get(i, 'not_tested')
            if status == 'success':
                test_btn.setStyleSheet("QPushButton { background-color: #28A745; color: white; border-radius: 9px; } QPushButton:hover { background-color: #218838; }")
            elif status == 'error':
                test_btn.setStyleSheet("QPushButton { background-color: #DC3545; color: white; border-radius: 9px; } QPushButton:hover { background-color: #C82333; }")
            elif status == 'testing':
                test_btn.setStyleSheet("QPushButton { background-color: #FFC107; color: white; border-radius: 9px; } QPushButton:hover { background-color: #E0A800; }")
            else:
                test_btn.setStyleSheet("QPushButton { background-color: #6c757d; color: white; border-radius: 9px; } QPushButton:hover { background-color: #5a6268; }")
            row_layout.addWidget(test_btn)
            
            del_btn = QPushButton("•")
            del_btn.setFixedSize(18, 18)
            del_btn.setToolTip(self.lang["tooltips"]["delete_model"])
            del_btn.setStyleSheet("QPushButton { background-color: #FF5F57; color: white; border-radius: 9px; font-weight: bold; font-size: 10px; } QPushButton:hover { background-color: #FF3B30; }")
            del_btn.clicked.connect(lambda _, idx=i: self.delete_model(idx))
            row_layout.addWidget(del_btn)

            self.models_list_layout.addWidget(row_widget)

    def refresh_api_key_list(self):
        # --- Список для хранения полей ввода ключей ---
        self.api_key_inputs = [] 
        
        # Clear existing items
        while self.api_keys_layout.count():
            child = self.api_keys_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Get keys from config
        api_keys = self.config.get("api_keys", [])
        # --- Получаем текущее состояние видимости ---
        is_visible = self.config.get("api_keys_visible", False)
        
        for i, key_data in enumerate(api_keys):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)

            # Radio Button (Active selector)
            radio = QRadioButton()
            radio.setToolTip(self.lang["tooltips"]["select_api_key"])
            radio.setChecked(key_data.get("active", False))
            radio.setFixedSize(18, 18) # <-- Задаем размер всей кнопке
            radio.setStyleSheet("""
                QRadioButton {
                    spacing: 0; /* Убираем отступ для текста */
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                }
                /* СТИЛЬ НЕАКТИВНОЙ КНОПКИ */
                QRadioButton::indicator:unchecked {
                    background-color: #353535; /* Фон как вы просили */
                }
                QRadioButton::indicator:unchecked:hover {
                    background-color: #4f4f4f; /* Чуть светлее при наведении */
                }
                /* СТИЛЬ АКТИВНОЙ КНОПКИ */
                QRadioButton::indicator:checked {
                    background-color: qradialgradient(
                        cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                        stop:0 #FFFFFF, stop:0.1 #FFFFFF, /* <--- УМЕНЬШИЛИ РАДИУС ТОЧКИ (было 0.4) */
                        stop:0.21 #5085D0, stop:1 #5085D0
                    );
                }
            """)
            self.key_radio_group.addButton(radio, i)
            row_layout.addWidget(radio)

            # Key Input
            key_input = QLineEdit(key_data.get("key", ""))
            
            # --- ПРИМЕНЯЕМ ВИДИМОСТЬ СРАЗУ ---
            if not is_visible:
                key_input.setEchoMode(QLineEdit.Password)

            key_input.setStyleSheet("""
                border-radius: 8px; border: 1px solid #444444;
                padding: 5px; background-color: #2a2a2a; color: #FFFFFF;
            """)
            key_input.textChanged.connect(lambda text, idx=i: self.update_api_key_value(idx, text))
            row_layout.addWidget(key_input, 1) # Stretch
            
            # --- СОХРАНЯЕМ ССЫЛКУ НА ПОЛЕ ВВОДА ---
            self.api_key_inputs.append(key_input)

            # --- НОВОЕ ПОЛЕ ДЛЯ ИМЕНИ ---
            name_input = QLineEdit(key_data.get("name", ""))
            name_input.setPlaceholderText("Имя ключа...")
            name_input.setFixedWidth(80)
            name_input.setStyleSheet("""
                border-radius: 8px; border: 1px solid #444444;
                padding: 5px; background-color: #2a2a2a; color: #FFFFFF;
            """)
            name_input.textChanged.connect(lambda text, idx=i: self.update_api_key_name(idx, text))
            row_layout.addWidget(name_input)

            # --- ОБНОВЛЕННЫЙ СЧЕТЧИК (24 ЧАСА) ---
            timestamps = key_data.get("usage_timestamps", [])
            now = time.time()
            recent_usage = len([ts for ts in timestamps if now - ts < 24 * 3600])
            count_label = QLabel(str(recent_usage))
            count_label.setToolTip(self.lang["tooltips"]["api_usage_tooltip"])
            count_label.setStyleSheet("color: #888888; font-size: 12px;")
            count_label.setFixedWidth(50) # <--- ИЗМЕНЕНО НА 50
            count_label.setAlignment(Qt.AlignCenter)
            row_layout.addWidget(count_label)

            # --- НОВАЯ КНОПКА ТЕСТИРОВАНИЯ ---
            test_btn = QPushButton("•")
            test_btn.setToolTip(self.lang["tooltips"]["test_api_key"])
            test_btn.setFixedSize(18, 18)
            test_btn.clicked.connect(lambda _, idx=i: self.start_api_key_test(idx))
            
            # Логика окрашивания кнопки
            status = self.api_key_test_statuses.get(i, 'not_tested')
            if status == 'success':
                test_btn.setStyleSheet("""
                    QPushButton { background-color: #28A745; color: white; border-radius: 9px; font-weight: bold; font-size: 10px; }
                    QPushButton:hover { background-color: #218838; }
                """)
            elif status == 'error':
                test_btn.setStyleSheet("""
                    QPushButton { background-color: #DC3545; color: white; border-radius: 9px; font-weight: bold; font-size: 10px; }
                    QPushButton:hover { background-color: #C82333; }
                """)
            elif status == 'testing':
                test_btn.setStyleSheet("""
                    QPushButton { background-color: #FFC107; color: white; border-radius: 9px; font-weight: bold; font-size: 10px; }
                    QPushButton:hover { background-color: #E0A800; }
                """)
            else: # not_tested
                test_btn.setStyleSheet("""
                    QPushButton { background-color: #6c757d; color: white; border-radius: 9px; font-weight: bold; font-size: 10px; }
                    QPushButton:hover { background-color: #5a6268; }
                """)

            row_layout.addWidget(test_btn)
            # ------------------------------------

            # --- ОБНОВЛЕННАЯ КНОПКА УДАЛЕНИЯ ---
            del_btn = QPushButton("•")
            del_btn.setToolTip(self.lang["tooltips"]["delete_api_key"])
            del_btn.setFixedSize(18, 18)
            del_btn.setStyleSheet("""
                QPushButton {
                    background-color: #FF5F57; color: white;
                    border-radius: 9px;
                    font-weight: bold; font-size: 10px;
                }
                QPushButton:hover { background-color: #FF3B30; }
            """)
            del_btn.clicked.connect(lambda _, idx=i: self.delete_api_key_entry(idx))
            row_layout.addWidget(del_btn)

            self.api_keys_layout.addWidget(row_widget)

    # Placeholder methods to be implemented in ClipGen.py
    def add_api_key_entry(self): pass
    def set_active_api_key_index(self, index): pass
    def update_api_key_value(self, index, text): pass
    def delete_api_key_entry(self, index): pass

    def setup_hotkey_card(self, hotkey, i):
        hotkey_card = QFrame()
        hotkey_card.setStyleSheet(f"""
            QFrame {{
                background-color: #252525;
                border-radius: 15px;
                padding: 10px;
            }}
        """)
        hotkey_layout = QVBoxLayout(hotkey_card)
        hotkey_layout.setSpacing(8)
        
        # Combine elements in top row: hotkey combination, delete button and color
        hotkey_header = QHBoxLayout()
        
        # Hotkey combination
        hotkey_edit = QKeySequenceEdit()
        hotkey_edit.setToolTip(self.lang["tooltips"]["hotkey_input"])
        hotkey_edit.setKeySequence(hotkey["combination"])
        hotkey_edit.setStyleSheet("""
            QKeySequenceEdit {
                background-color: #333333;
                color: white;
                border-radius: 5px;
                padding: 5px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        hotkey_edit.keySequenceChanged.connect(
            lambda seq, h=hotkey: self.update_hotkey_from_sequence(h, seq.toString())
        )
        hotkey_header.addWidget(hotkey_edit)

        # Color selection section
        color_layout = QHBoxLayout()
        color_layout.setSpacing(5)
        
        color_label = QLabel(self.lang["settings"]["log_color_label"])
        color_layout.addWidget(color_label)
        
        color_input = QLineEdit(hotkey["log_color"].replace("#", ""))
        color_input.setFixedWidth(70)
        color_input.setStyleSheet("""
            border-radius: 8px; 
            border: 1px solid #444444;
            padding: 5px;
            background-color: #2a2a2a;
        """)
        color_input.textChanged.connect(lambda text, h=hotkey: self.update_color(h, f"#{text}"))
        
        color_preview = QPushButton()
        # Устанавливаем черный цвет текста для подсказки через HTML
        color_preview.setToolTip(f"<p style='color: #000000;'>{self.lang['tooltips']['color_picker']}</p>")
        color_preview.setFixedSize(20, 20)  # Smaller preview
        color_preview.setStyleSheet(f"background-color: {hotkey['log_color']}; border-radius: 5px; border: none;")
        color_preview.clicked.connect(lambda checked, h=hotkey, inp=color_input, btn=color_preview: self.open_color_picker(h, inp, btn))
        
        color_layout.addWidget(color_input)
        color_layout.addWidget(color_preview)
        hotkey_header.addLayout(color_layout)
        
        # Delete button - smaller by 30%
        delete_button = QPushButton("•") # Используем точку, как и в API
        delete_button.setToolTip(self.lang["tooltips"]["delete_hotkey"])
        delete_button.setFixedSize(18, 18)
        delete_button.setStyleSheet("""
            QPushButton {
                background-color: #FF5F57;
                color: white;
                border-radius: 9px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #FF3B30;
            }
        """)
        delete_button.clicked.connect(lambda *, h=hotkey: self.delete_hotkey(h))
        hotkey_header.addWidget(delete_button)
        
        hotkey_layout.addLayout(hotkey_header)
        
        # Action name field
        name_layout = QHBoxLayout()
        name_label = QLabel(self.lang["settings"]["action_name_label"])
        name_layout.addWidget(name_label)
        
        name_input = QLineEdit(hotkey["name"])
        name_input.setStyleSheet("""
            border-radius: 8px; 
            border: 1px solid #444444;
            padding: 8px;
            background-color: #2a2a2a;
        """)
        name_input.textChanged.connect(lambda text, h=hotkey: self.update_name(h, text))
        name_layout.addWidget(name_input)
        hotkey_layout.addLayout(name_layout)
        self.name_inputs[hotkey["combination"]] = name_input
        
        # Prompt field with auto-height
        prompt_label = QLabel(self.lang["settings"]["prompt_label"])
        hotkey_layout.addWidget(prompt_label)
        
        # --- ИСПОЛЬЗУЕМ НАШ НОВЫЙ КЛАСС ВМЕСТО QTextEdit ---
        prompt_input = FocusExpandingTextEdit(hotkey["prompt"])
        
        # Setup appearance
        prompt_input.setStyleSheet("""
            border-radius: 8px; 
            border: 1px solid #444444;
            padding: 8px;
            background-color: #2a2a2a;
        """)
        
        # Add size adjustment function
        def adjust_height():
            doc_height = prompt_input.document().size().height()
            new_height = max(80, min(250, doc_height + 30))
            prompt_input.setMinimumHeight(int(new_height))
            prompt_input.setMaximumHeight(int(new_height))
        
        # --- ДОБАВЛЯЕМ РЕАКЦИЮ НА КЛИК (ФОКУС) ---
        prompt_input.focusIn.connect(adjust_height)
        
        # Оставляем старую реакцию на изменение текста (полезно, если текст переносится на новую строку)
        prompt_input.textChanged.connect(adjust_height)
        prompt_input.textChanged.connect(lambda h=hotkey, pi=prompt_input: self.update_prompt(h, pi.toPlainText()))
        
        QTimer.singleShot(0, adjust_height)
        
        hotkey_layout.addWidget(prompt_input)
        self.prompt_inputs[hotkey["combination"]] = prompt_input
        
        return hotkey_card

    def refresh_hotkey_list(self):
        """Очищает и заново отрисовывает только список карточек с горячими клавишами."""
        # Очищаем старые виджеты из контейнера
        while self.hotkeys_list_layout.count():
            child = self.hotkeys_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Сбрасываем словари для инпутов
        self.prompt_inputs = {}
        self.name_inputs = {}
        self.color_pickers = {}
        self.hotkey_combos = {}

        # Создаем и добавляем карточки заново
        for i, hotkey in enumerate(self.config["hotkeys"]):
            hotkey_card = self.setup_hotkey_card(hotkey, i)
            self.hotkeys_list_layout.addWidget(hotkey_card)

    def add_new_hotkey(self):
        """Добавляет новую горячую клавишу и обновляет интерфейс."""
        new_hotkey = {
            "combination": "Ctrl+N",
            "name": self.lang["default_action_name"],
            "log_color": "#FFFFFF",
            "prompt": self.lang["default_prompt"]
        }
        self.config["hotkeys"].append(new_hotkey)
        self.save_settings()

        # Обновляем только нужные части интерфейса
        self.update_buttons()
        self.refresh_hotkey_list()
        self.update_logger_colors()

        # Сбрасываем состояние клавиш
        self.key_states = {"ctrl": False, "alt": False, "shift": False, "meta": False}

    def reload_settings_tab(self):
        self.model_time_labels.clear()
        # Сохраняем текущую активную вкладку (скорее всего, это "Настройки")
        current_index = self.content_stack.currentIndex()
        
        while self.content_stack.count() > 0:
            widget = self.content_stack.widget(0)
            self.content_stack.removeWidget(widget)
            widget.deleteLater()

        # 2. Создаем все три вкладки заново в их правильном порядке
        self.setup_log_tab()
        self.setup_settings_tab()
        self.setup_help_tab()
        
        # Возвращаемся на ту вкладку, на которой был пользователь 
        # (если индекс корректен, иначе на вкладку настроек по умолчанию)
        self.switch_page(current_index if current_index != -1 else 1)

    def update_hotkey_from_sequence(self, hotkey, sequence):
        """Update hotkey combination from the new key sequence"""
        if not sequence:  # If sequence is empty
            return
            
        # Update in configuration
        old_combo = hotkey["combination"]
        
        # Check if combination is already in use
        if any(h["combination"] == sequence for h in self.config["hotkeys"] if h != hotkey):
            # Show warning
            self.show_themed_message_box(
                QMessageBox.Warning,
                self.lang["dialogs"]["duplicate_hotkey_title"],
                self.lang["dialogs"]["duplicate_hotkey_message"].format(combo=sequence),
                QMessageBox.Ok,
                QMessageBox.Ok
            )
            return
        
        # Update combination
        hotkey["combination"] = sequence
        
        # Update key_states and interface
        self.update_hotkey(old_combo, sequence)

    def delete_hotkey(self, hotkey):
        """Удаляет горячую клавишу и обновляет интерфейс."""
        dialog = CustomMessageBox(self,
            self.lang["dialogs"]["confirm_delete_title"],
            self.lang["dialogs"]["confirm_delete_message"].format(action_name=hotkey['name']),
            yes_text=self.lang["dialogs"]["yes_button"],
            no_text=self.lang["dialogs"]["no_button"]
        )
        
        if dialog.exec_() == QDialog.Accepted:
            self.config["hotkeys"].remove(hotkey)
            self.save_settings()

            # Обновляем только нужные части интерфейса
            self.update_buttons()
            self.refresh_hotkey_list()
            
        # Сбрасываем состояние клавиш
        self.key_states = {"ctrl": False, "alt": False, "shift": False, "meta": False}

    def apply_styles(self):
        # --- ТЕМНЫЙ СТИЛЬ ПОДСКАЗОК (Глобально) ---
        QApplication.instance().setStyleSheet("""
            QToolTip {
                background-color: #2b2b2b;  /* Темный фон */
                color: #ffffff;             /* Белый текст */
                border: 1px solid #3c3c3c;  /* Тонкая рамка */
                border-radius: 5px;         /* Закругленные углы */
                padding: 5px;               /* Отступ */
                font-size: 12px;            /* Размер шрифта */
            }
        """)

        # Остальные стили для самого окна
        self.setStyleSheet("""
            QStackedWidget { 
                background-color: #1e1e1e; 
                border: none; 
                border-radius: 10px; 
            }
            QWidget {
                background-color: #1e1e1e;
            }
            QFrame {
                background-color: #252525;
            }
            QPushButton { 
                background-color: #333333; 
                border-radius: 10px; 
                padding: 8px; 
                color: #FFFFFF;
            }
            QPushButton:hover { 
                background-color: #404040; 
            }
            QPushButton:pressed { 
                background-color: #2a2a2a; 
            }
            QLineEdit, QTextEdit { 
                background-color: #2e2e2e; 
                color: #FFFFFF; 
                border: 1px solid #444444; 
                border-radius: 10px; 
                padding: 5px;
            }
            QLineEdit:focus, QTextEdit:focus { 
                border: 1px solid #A3BFFA; 
            }
            QLabel { 
                color: #FFFFFF; 
                background-color: transparent;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background: transparent;
                width: 8px;
                height: 8px;
                margin: 0px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: #555555;
                min-height: 20px;
                min-width: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
                background: #666666;
            }
            QScrollBar::add-line, QScrollBar::sub-line { 
                background: none; 
                height: 0px;
                width: 0px;
            }
            QScrollBar::add-page, QScrollBar::sub-page { 
                background: none; 
            }
            QTextBrowser {
                background-color: #252525; 
                color: #FFFFFF; 
                border: none; 
                border-radius: 10px;
                padding: 10px;
                selection-background-color: #A3BFFA;
                selection-color: #1e1e1e;
            }
            QScrollArea, QScrollArea * {
                background-color: #1e1e1e;
            }
            QComboBox {
                background-color: #333333;
                border-radius: 8px;
                padding: 5px;
                color: white;
                border: 1px solid #444444;
            }
            QComboBox::drop-down {
                width: 20px;
                border-left: 1px solid #444444;
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
            }
            QComboBox::down-arrow {
                image: url(dropdown.png);
                width: 12px;
                height: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #333333;
                color: white;
                selection-background-color: #444444;
                selection-color: white;
                border: 1px solid #444444;
                border-radius: 0px;
            }
        """)

    def update_buttons(self):
        for widget in self.button_widget.findChildren(QPushButton):
            widget.deleteLater()
        self.buttons.clear()

        width = self.button_widget.width()
        if width <= 0:
            return

        buttons_per_row = max(1, width // 160)
        rows = [[] for _ in range((len(self.config["hotkeys"]) + buttons_per_row - 1) // buttons_per_row)]

        for i, hotkey in enumerate(self.config["hotkeys"]):
            row_idx = i // buttons_per_row
            btn = QPushButton(f"{hotkey['name']}")
            btn.setToolTip(self.lang["tooltips"]["main_action_button"].format(combination=hotkey['combination']))
            btn.setFixedHeight(30)  # Reduced button height
            color = hotkey['log_color']
            btn.setStyleSheet(f"""
                QPushButton {{ 
                    color: {color}; 
                    background-color: #333333;
                    border-radius: 10px;
                    padding: 5px 10px;
                }}
                QPushButton:hover {{ 
                    background-color: {color}; 
                    color: #333333;
                }}
                QPushButton:pressed {{ 
                    background-color: {color}80; 
                }}
            """)
            btn.clicked.connect(lambda checked, h=hotkey: self.queue.put(h["name"]))
            rows[row_idx].append(btn)
            self.buttons[hotkey["combination"]] = btn

        for row in rows:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)
            for btn in row:
                btn.setMinimumWidth(0)
                row_layout.addWidget(btn, stretch=1)
            self.button_layout.addLayout(row_layout)

    def append_log(self, msg, color):
        self.log_area.moveCursor(QTextCursor.End)
        
        # Determine log type for formatting
        if self.lang["logs"]["execution_time"].split()[0] in msg:
            # Execution time message
            self.log_area.setTextColor(QColor("#888888"))
            self.log_area.append(f"    {msg}")
        elif any(f"{hotkey['combination']}: {hotkey['name']}" in msg for hotkey in self.config["hotkeys"]):
            # Action header
            self.log_area.setTextColor(QColor(color))
            
            # Add separator if not the first message
            cursor = self.log_area.textCursor()
            if not cursor.atStart():
                self.log_area.append("\n" + "─" * 40 + "\n")
                
            self.log_area.append(f"{msg}")
        elif "Error:" in msg:
            # Error message
            self.log_area.setTextColor(QColor("#FF5555"))
            # Добавляем пустую строку перед ошибкой (\n) и отступ
            self.log_area.append(f"\n    x {msg}")
        elif self.lang["errors"]["empty_clipboard"] in msg:
            # Warning
            self.log_area.setTextColor(QColor("#FFDD55"))
            self.log_area.append(f"⚠️ {msg}")
        else:
            # Processing result or other message
            self.log_area.setTextColor(QColor(color))
            
            # If result, add indentation and formatting
            if not self.lang["logs"]["app_started"] in msg:
                self.log_area.append(f"    {msg}")
            else:
                self.log_area.append(msg)
        
        # Scroll to bottom
        self.log_area.ensureCursorVisible()

    def open_color_picker(self, hotkey, color_input, color_button):
        color = QColorDialog.getColor(QColor(hotkey["log_color"]), self, "Choose color")
        if color.isValid():
            hex_color = color.name()
            color_input.setText(hex_color.replace("#", ""))
            self.update_color(hotkey, hex_color)
            # Сразу обновляем цвет кнопки-индикатора
            color_button.setStyleSheet(f"background-color: {hex_color}; border-radius: 5px; border: none;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'resize_timer'):
            self.resize_timer.start(200)

    def setup_tray_icon(self):
        """Создает иконку и меню в системном трее."""
        self.tray_icon = QSystemTrayIcon(self)
        self.set_tray_icon_default() # Устанавливаем иконку по умолчанию

        # Создаем меню
        self.tray_menu = QMenu()
        
        # --- НАЧАЛО НОВОГО КОДА ---
        # Применяем стили к контекстному меню
        self.tray_menu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b; /* Темный фон */
                color: #FFFFFF;            /* Белый текст */
                border: 1px solid #444444; /* Тонкая рамка */
                border-radius: 8px;         /* Закругленные углы */
                padding: 5px;               /* Внутренние отступы */
            }
            QMenu::item {
                padding: 8px 25px;          /* Отступы для каждого пункта (верт/гориз) */
                margin: 2px 0px;            /* Внешний вертикальный отступ */
                border-radius: 5px;         /* Закругление для подсветки при наведении */
            }
            QMenu::item:selected {
                background-color: #4a4a4a; /* Цвет фона при наведении/выборе */
            }
            QMenu::separator {
                height: 1px;                /* Высота разделителя */
                background: #444444;        /* Цвет разделителя */
                margin: 5px 0px;            /* Отступы для разделителя */
            }
        """)
        # --- КОНЕЦ НОВОГО КОДА ---

        self.show_hide_action = QAction("Показать/Скрыть", self)
        self.quit_action = QAction("Выход", self)

        self.tray_menu.addAction(self.show_hide_action)
        self.tray_menu.addAction(self.quit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

    def set_dark_titlebar(self, hwnd):
        """Установка темной темы для стандартного заголовка Windows"""
        try:
            # Константы для Windows API
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            
            # Включение темной темы для заголовка окна
            from ctypes import windll, c_int, byref
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 
                byref(c_int(1)), c_int(4) # sizeof(c_int)
            )
        except Exception as e:
            print(f"Не удалось установить темную тему для заголовка: {e}")

    def _create_dynamic_icon(self, color, text=None, text_color="#000000"):
        """Создает динамическую иконку с заданным цветом и текстом."""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Рисуем квадрат с закругленными углами
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, 64, 64, 12, 12)
        
        # Рисуем текст, если он есть
        if text:
            # Используем переданный цвет текста (по умолчанию черный)
            painter.setPen(QColor(text_color)) 
            font = QFont()
            # Динамически подбираем размер шрифта
            if len(str(text)) > 3: # Для чисел вроде "12.3"
                font.setPointSize(20)
            elif len(str(text)) > 2:
                font.setPointSize(24)
            else:
                font.setPointSize(32)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
            
        painter.end()
        return QIcon(pixmap)

    def set_tray_icon_default(self):
        """Устанавливает стандартную иконку приложения."""
        # Используем правильную версию с resource_path для совместимости с .exe
        icon_path = resource_path("ClipGen.ico")
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else: # Запасной вариант, если иконка не найдена
            self.tray_icon.setIcon(self._create_dynamic_icon("#555555"))

    def set_tray_icon_working_with_time(self, time_str):
        """Устанавливает 'рабочую' желтую иконку с таймером."""
        self.tray_icon.setIcon(self._create_dynamic_icon("#FFBF08", time_str))

    def set_tray_icon_success(self, duration_str):
        """Устанавливает зеленую иконку успеха с временем выполнения."""
        # Используем финальную версию с более ярким цветом и таймаутом в 3 сек
        self.tray_icon.setIcon(self._create_dynamic_icon("#28A745", duration_str))
        QTimer.singleShot(3000, self.set_tray_icon_default)

    def set_tray_icon_error(self):
        """Устанавливает красную иконку ошибки."""
        # Используем финальную версию с белым восклицательным знаком
        self.tray_icon.setIcon(self._create_dynamic_icon("#F33100", "!", text_color="#FFFFFF"))

    def set_tray_icon_update(self):
        """Устанавливает синюю иконку уведомления."""
        # Яркий синий цвет (#007AFF - как в iOS)
        self.tray_icon.setIcon(self._create_dynamic_icon("#007AFF", "!", text_color="#FFFFFF"))

    def flash_tray_icon_warning(self):
        """Мигает красным два раза, затем возвращает желтую (рабочую) иконку."""
        # 1. Красный
        self.set_tray_icon_error()
        # 2. Через 200мс желтый (время текущее)
        current_time_str = f"{(time.time() - self.start_time):.1f}" if self.start_time > 0 else "..."
        QTimer.singleShot(200, lambda: self.set_tray_icon_working_with_time(current_time_str))
        # 3. Через 400мс снова Красный
        QTimer.singleShot(400, self.set_tray_icon_error)
        # 4. Через 600мс снова желтый и работаем дальше
        QTimer.singleShot(600, lambda: self.set_tray_icon_working_with_time(current_time_str))

    def setup_help_tab(self):
        """Создает красивую и информативную вкладку 'Help'."""
        help_tab = QWidget()
        help_layout = QVBoxLayout(help_tab)
        help_layout.setContentsMargins(15, 15, 15, 15)
        help_layout.setSpacing(15)

        # --- Текстовый блок, который будет растягиваться ---
        help_browser = QTextBrowser()
        help_browser.setOpenExternalLinks(True)
        help_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        help_browser.setStyleSheet("""
            QTextBrowser { 
                background-color: #252525;
                border-radius: 10px;
                padding: 15px;
                border: none;
                color: #FFFFFF;
                font-size: 13px;
                line-height: 1.5;
            }
        """)
        
        help_html = """
        <h2 style='color: #A3BFFA; font-size: 20px;'>Welcome to ClipGen!</h2>
        <p>This is your personal AI assistant, built right into your clipboard.</p>
        
        <hr style='border: 1px solid #333;'>

        <h2 style='color: #A3BFFA; font-size: 16px;'>How It Works</h2>

        <h3 style='color: #FFFFFF; font-size: 14px;'>Step 1: Get an API Key (Required)</h3>
        <p>ClipGen works via the Gemini API. Without a key, it won't work. It's free and fast.</p>
        <ul style='margin-left: 20px;'>
            <li>Go to the <a href='https://aistudio.google.com/api-keys' style='color: #81b3f0;'>Google AI Studio</a> page and get your key.</li>
            <li>Paste it in the <b>Settings</b> tab. You can add multiple keys if you hit the usage limits.</li>
            <li>Check if the key is working by clicking the gray status indicator button next to it.</li>
        </ul>

        <h3 style='color: #FFFFFF; font-size: 14px;'>Step 2: Select, Press, and Get the Result</h3>
        <p>ClipGen only reads your clipboard at the moment you press a hotkey. Simply select text (or copy an image) in <b>any program</b> (browser, messenger, code editor) and press a hotkey. ClipGen will copy the content, process it, and paste the result back in place of the selection. If there's nowhere to paste, the result will appear in the logs.</p>
        
        <h3 style='color: #FFFFFF; font-size: 14px;'>Step 3: Watch the Tray Icon</h3>
        <p>The system tray icon shows the status: <b style='color:#FFBF08;'>yellow</b> for processing, <b style='color:#28A745;'>green</b> for success, and <b style='color:#F33100;'>red</b> for an error.</p>

        <hr style='border: 1px solid #333;'>
        
        <h2 style='color: #A3BFFA; font-size: 16px;'>Personalization</h2>
        <p>The power of ClipGen is its flexibility. Go to the <b>Settings</b> tab to:</p>
        <ul style='margin-left: 20px;'>
            <li><b>Create your own hotkeys.</b> Add new actions, delete old ones, and assign any key combination you like.</li>
            <li><b>Experiment with prompts.</b> I've created prompts that are perfect for me, but you can write your own to solve your unique, repetitive tasks.</li>
            <li><b>Manage Gemini models.</b> Add new models (find the current list <a href='https://ai.google.dev/gemini-api/docs/models' style='color: #81b3f0;'>here</a>), test their speed, and choose the best one for your needs. Remember: smarter models take longer to respond.</li>
        </ul>
        
        <hr style='border: 1px solid #333;'>

        <h2 style='color: #A3BFFA; font-size: 16px;'>Feedback and New Projects</h2>
        <p>My name is <b>VETA (Vitalii Kalistratov)</b>. If you have any questions or suggestions, you can write them in my <a href='https://t.me/VETA14' style='color: #81b3f0;'>Telegram channel</a>, where I share my new works, thoughts, and experiments. Feel free to join!</p>
        <p><b>My website:</b> <a href='http://vetaone.site/' style='color: #81b3f0;'>vetaone.site</a></p>

        <hr style='border: 1px solid #333;'>

        <h2 style='color: #FAF089; font-size: 16px;'>Support the Project</h2>
        <p style='color: #FBD38D;'>If you find ClipGen useful, please consider supporting its future development. It motivates me to add new features.</p>
        """

        help_browser.setHtml(help_html)
        
        help_layout.addWidget(help_browser, 1)

        # --- Нижний блок с кошельком (футер) ---
        donate_widget = QWidget()
        donate_layout = QHBoxLayout(donate_widget)
        donate_layout.setContentsMargins(0, 0, 0, 0)
        donate_layout.setSpacing(10)
        
        wallet_address = "TYgsAvTkkrRqArgo3Q5BYMghbYn6DViVqQ"
        
        wallet_input = QLineEdit(wallet_address)
        wallet_input.setReadOnly(True)
        wallet_input.setStyleSheet("""
            QLineEdit {
                background-color: #2a2a2a; color: #FFFFFF; border: 1px solid #444444; 
                border-radius: 8px; padding: 8px; font-family: 'Consolas', monospace;
            }
        """)
        
        # Сохраняем оригинальный стиль в переменную
        original_copy_style = """
            QPushButton { background-color: #3D8948; border-radius: 8px; padding: 8px; }
            QPushButton:hover { background-color: #2A6C34; }
        """
        
        copy_button = QPushButton("Copy")
        copy_button.setToolTip("Copy wallet address to clipboard")
        copy_button.setFixedWidth(80)
        copy_button.setStyleSheet(original_copy_style)
        
        # Подключаем наш новый, умный обработчик клика
        copy_button.clicked.connect(
            lambda: self.handle_copy_button_click(copy_button, wallet_address, original_copy_style)
        )
        
        donate_layout.addWidget(QLabel("USDT (TRC-20):"))
        donate_layout.addWidget(wallet_input)
        donate_layout.addWidget(copy_button)
        
        help_layout.addWidget(donate_widget)

        self.content_stack.addWidget(help_tab)

    def handle_copy_button_click(self, button, text_to_copy, original_style):
        """Копирует текст, меняет вид кнопки и возвращает его через 1 сек."""
        # 1. Сначала выполняем основное действие - копирование
        pyperclip.copy(text_to_copy)

        # 2. Меняем текст и стиль кнопки на "Copied"
        button.setText("Copied")
        button.setStyleSheet("""
            QPushButton { 
                background-color: #28A745; /* Ярко-зеленый */
                border-radius: 8px; 
                padding: 8px; 
            }
        """)

        # 3. Запускаем таймер, который через 1000 мс (1 сек) вернет все обратно
        QTimer.singleShot(1000, lambda: (
            button.setText("Copy"),
            button.setStyleSheet(original_style)
        ))

    # Placeholder method
    def start_api_key_test(self, index): pass

    # Placeholder methods
    def start_api_key_test(self, index): pass
    def add_new_model(self): pass
    def delete_model(self, index): pass
    def update_model_name(self, index, name): pass
    def set_active_model(self, index): pass
    def start_model_test(self, index): pass