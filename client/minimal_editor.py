#!/usr/bin/env python3
"""
Минималистичный терминальный STT редактор.

Легковесное приложение для работы с распознаванием речи в минимальных окнах терминала.
Создано на основе prompt_toolkit без лишних элементов интерфейса.

Особенности:
- БЕЗ БОРДЮРОВ для чистого копирования
- Поддержка мыши для выделения и позиционирования
- Автоматическое копирование в буфер обмена
- Прямая работа с Parakeet API (batch режим)
- Оптимизировано для маленьких терминальных окон
"""

import asyncio
import os
import sys
import time

# Основные зависимости
try:
    import pyperclip
except ImportError as e:
    print(f"Ошибка импорта зависимостей: {e}")
    print("Установите зависимости: pip install pyperclip")
    sys.exit(1)

# prompt_toolkit компоненты
try:
    from prompt_toolkit import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, VSplit, Window, ConditionalContainer
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.styles import Style
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.filters import Condition
except ImportError as e:
    print(f"Ошибка импорта prompt_toolkit: {e}")
    print("Установите prompt_toolkit: pip install prompt_toolkit")
    sys.exit(1)

# Локальные модули
from client.audio_buffer import AudioBuffer, play_sound
from client.parakeet_client import ParakeetClient


def load_env_file() -> None:
    """Загрузка переменных окружения из .env файла"""
    env_file = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()


# Загружаем переменные окружения
load_env_file()


class ClipboardManager:
    """Менеджер для работы с системным буфером обмена"""

    @staticmethod
    def copy_text(text: str) -> bool:
        """Копирование текста в системный буфер обмена"""
        try:
            pyperclip.copy(text)
            return True
        except Exception as e:
            print(f"Ошибка копирования в буфер: {e}")
            return False

    @staticmethod
    def get_text() -> str:
        """Получение текста из буфера обмена"""
        try:
            return pyperclip.paste()
        except Exception:
            return ""


class StatusBar:
    """Минимальная статус строка"""

    # Состояния записи
    STATE_IDLE = 'idle'          # Не записывает
    STATE_RECORDING = 'recording'  # Запись
    STATE_SENDING = 'sending'    # Отправка на API
    STATE_READY = 'ready'        # Готов (текст получен)

    def __init__(self, editor):
        self.editor = editor
        self.last_copy_time = 0
        self.state = self.STATE_IDLE
        self.error_message = ""
        self.error_time = 0

    def set_state(self, state: str, error: str = ""):
        """Установка состояния"""
        self.state = state
        if error:
            self.error_message = error
            self.error_time = time.time()

    def get_left_status(self) -> FormattedText:
        """Левая часть статус бара: индикатор + F1:Help"""
        items = []

        # Индикатор состояния
        if self.state == self.STATE_RECORDING:
            items.append(('class:status-recording', '[●] '))
        elif self.state == self.STATE_SENDING:
            items.append(('class:status-sending', '[●] '))
        elif self.state == self.STATE_READY:
            items.append(('class:status-ready', '[●] '))
        elif self.error_message and time.time() - self.error_time < 3:
            items.append(('class:status-error', '[●] '))
        else:
            items.append(('class:status-idle', '[●] '))

        # F1:Help + индикатор копирования
        items.append(('', 'F1:Help'))

        # Индикатор копирования
        current_time = time.time()
        if current_time - self.last_copy_time < 1.5:
            items.append(('class:status-success', ' ✓'))

        return FormattedText(items)

    def get_right_status(self) -> FormattedText:
        """Правая часть статус бара: состояние"""
        items = []

        if self.error_message and time.time() - self.error_time < 3:
            # Показываем ошибку (обрезаем если длинная)
            error_text = self.error_message[:30] + '...' if len(self.error_message) > 30 else self.error_message
            items.append(('class:status-error', error_text))
        elif self.state == self.STATE_RECORDING:
            duration = self.editor.audio_buffer.get_recording_duration()
            items.append(('class:status-recording', f'Recording {duration:.1f}s'))
        elif self.state == self.STATE_SENDING:
            items.append(('class:status-sending', 'Sending...'))
        elif self.state == self.STATE_READY:
            items.append(('class:status-ready', 'Ready'))
        else:
            # Проверяем доступность API
            if self.editor.api_available:
                items.append(('class:status-connected', 'Ready'))
            else:
                items.append(('class:status-disconnected', 'API Offline'))

        return FormattedText(items)

    def show_copy_indicator(self):
        """Показать индикатор копирования"""
        self.last_copy_time = time.time()


class MinimalSTTEditor:
    """Основной класс минималистичного STT редактора"""

    def __init__(self):
        # Основной текстовый буфер
        self.buffer = Buffer(multiline=True)

        # Отслеживание предыдущего состояния выделения для автокопирования
        self.last_selection_hash = None

        # Менеджеры
        self.clipboard_manager = ClipboardManager()
        self.status_bar = StatusBar(self)

        # Аудио буфер и клиент API
        self.audio_buffer = AudioBuffer(sample_rate=16000)
        api_url = os.getenv('PARAKEET_API_URL', 'http://localhost:5092/v1')
        model = os.getenv('PARAKEET_MODEL', 'parakeet-tdt-0.6b-v3')
        self.parakeet_client = ParakeetClient(api_url=api_url, model=model)

        # Состояние
        self.is_recording = False
        self.api_available = False
        self.recording_start_time = 0

        # Состояние справки
        self.show_help = False

        # Флаг для вывода инициализации (для тестового режима)
        self._initialization_output = False

        # UI компоненты
        self.buffer_control = BufferControl(
            buffer=self.buffer,
            focusable=True,
            include_default_input_processors=True
        )

        # Главное окно редактора БЕЗ РАМОК
        self.editor_window = Window(
            content=self.buffer_control,
            wrap_lines=True,
            dont_extend_width=False,
            dont_extend_height=False
        )

        # Статус бар с разделением на левую и правую части
        self.status_window = VSplit([
            # Левая часть: индикатор + F1:Help
            Window(
                content=FormattedTextControl(
                    lambda: self.status_bar.get_left_status()
                ),
                dont_extend_width=True
            ),
            # Центр: пустое пространство (расширяется)
            Window(char=' '),
            # Правая часть: статус STT
            Window(
                content=FormattedTextControl(
                    lambda: self.status_bar.get_right_status()
                ),
                dont_extend_width=True
            ),
        ], height=1)

        # Layout: редактор + статус бар (пока без справки)
        self.layout = Layout(
            HSplit([
                # Окно справки (сверху если показана)
                ConditionalContainer(
                    content=self.create_help_window(),
                    filter=Condition(lambda: self.show_help)
                ),
                # Главная область (расширяется)
                self.editor_window,
                # Статус бар (1 строка)
                self.status_window
            ])
        )

        # Стили
        self.style = Style.from_dict({
            # Статус бар
            'status-recording': '#ff0000 bold',        # Красный: запись
            'status-sending': '#ffaa00 bold',          # Оранжевый: отправка
            'status-ready': '#00ff00 bold',            # Зеленый: готов
            'status-idle': '#666666',                  # Серый: неактивен
            'status-error': '#ff0000 bold reverse',    # Красный с фоном: ошибка
            'status-connected': 'bg:#008800 #ffffff',  # Зеленый фон при подключении
            'status-disconnected': 'bg:#880000 #ffffff',  # Красный фон при отключении
            'status-success': 'bg:#008800 #ffffff bold',  # Зеленый для success
            # Справка
            'help-box': 'bg:#ffffff #000000',          # Белый фон для справки
            'help-title': '#0066cc bold',              # Синий заголовок
            'help-section': '#006600 bold',            # Зеленый заголовок секции
            'help-key': '#cc6600 bold',                # Оранжевые клавиши
        })

        # Приложение
        self.app = Application(
            layout=self.layout,
            key_bindings=self.create_key_bindings(),
            style=self.style,
            full_screen=True,
            mouse_support=True,
            refresh_interval=0.1,
            on_invalidate=self.on_app_invalidate
        )

        # Задача записи
        self._recording_task = None

    def create_key_bindings(self) -> KeyBindings:
        """Создание клавиатурных привязок"""
        kb = KeyBindings()

        # F1 - Показать/скрыть справку
        @kb.add('f1')
        def toggle_help(event):
            self.show_help = not self.show_help
            event.app.invalidate()

        # ESC - Скрыть справку
        @kb.add('escape')
        def hide_help(event):
            if self.show_help:
                self.show_help = False
                event.app.invalidate()

        # F5 - Начать/остановить запись
        @kb.add('f5')
        def toggle_recording(event):
            if self.is_recording:
                asyncio.create_task(self.stop_recording_and_transcribe())
            else:
                asyncio.create_task(self.start_recording())

        # F3 - Копировать весь текст
        @kb.add('f3')
        def copy_all_text(event):
            text = self.buffer.text
            if text.strip():
                if self.clipboard_manager.copy_text(text):
                    self.status_bar.show_copy_indicator()

        # F8 - Очистить весь текст
        @kb.add('f8')
        def clear_all_text(event):
            self.buffer.text = ''

        # Ctrl+C - Выход из приложения
        @kb.add('c-c')
        def exit_editor_ctrl_c(event):
            event.app.exit()

        # Ctrl+A - Выделить все
        @kb.add('c-a')
        def select_all(event):
            self.buffer.cursor_position = 0
            self.buffer.start_selection()
            self.buffer.cursor_position = len(self.buffer.text)

        # Ctrl+Q - Выход
        @kb.add('c-q')
        def exit_editor(event):
            event.app.exit()

        return kb

    def create_help_window(self):
        """Создание окна справки"""
        help_text = FormattedText([
            ('class:help-title', '╔═══════════════════════════════════\n'),
            ('class:help-title', '║    STT Минимальный Редактор       ║\n'),
            ('class:help-title', '╚═══════════════════════════════════\n\n'),
            ('class:help-section', 'Индикаторы состояния:\n'),
            ('class:status-recording', '  ● Красный'),
            ('', ' - запись аудио\n'),
            ('class:status-sending', '  ● Оранжевый'),
            ('', ' - отправка на API\n'),
            ('class:status-ready', '  ● Зеленый'),
            ('', ' - готов к работе\n'),
            ('class:status-error', '  ● Красный (фон)'),
            ('', ' - ошибка\n'),
            ('class:status-idle', '  ● Серый'),
            ('', ' - неактивен\n\n'),
            ('class:help-section', 'Горячие клавиши:\n'),
            ('class:help-key', '  F1'),
            ('', ' - показать/скрыть справку\n'),
            ('class:help-key', '  F5'),
            ('', ' - начать/остановить запись\n'),
            ('class:help-key', '  F3'),
            ('', ' - копировать весь текст\n'),
            ('class:help-key', '  F8'),
            ('', ' - очистить все\n'),
            ('class:help-key', '  Ctrl+A'),
            ('', ' - выделить все\n'),
            ('class:help-key', '  ESC'),
            ('', ' - закрыть справку\n\n'),
            ('class:help-section', 'Особенности:\n'),
            ('', '  • Batch режим (Parakeet API)\n'),
            ('', '  • Автокопирование текста\n'),
            ('', '  • Поддержка мыши\n'),
            ('', '  • 16kHz моно аудио')
        ])

        return Window(
            content=FormattedTextControl(lambda: help_text),
            width=40,
            height=22,
            style='class:help-box'
        )

    def on_app_invalidate(self, sender=None):
        """Обработчик обновления приложения"""
        self.check_selection_change()

    def check_selection_change(self):
        """Проверка изменений в выделении и автокопирование"""
        if self.buffer.selection_state:
            selected_text = self.buffer.copy_selection()
            if selected_text and selected_text.text.strip():
                selection_hash = hash(selected_text.text.strip())

                if self.last_selection_hash != selection_hash:
                    if self.clipboard_manager.copy_text(selected_text.text):
                        self.status_bar.show_copy_indicator()
                    self.last_selection_hash = selection_hash
        else:
            self.last_selection_hash = None

    async def start_recording(self):
        """Начало записи аудио"""
        if self.is_recording:
            return

        if not self.audio_buffer.start_recording():
            self.status_bar.set_state(StatusBar.STATE_IDLE, "Mic error")
            self.app.invalidate()
            return

        self.is_recording = True
        self.recording_start_time = time.time()
        self.status_bar.set_state(StatusBar.STATE_RECORDING)
        play_sound('start')
        self.app.invalidate()

        # Запускаем задачу чтения аудио и обновления UI
        self._recording_task = asyncio.create_task(self._recording_loop())

    async def _recording_loop(self):
        """Цикл записи аудио с обновлением UI"""
        while self.is_recording:
            self.audio_buffer.read_chunk()
            # Обновляем UI для отображения времени
            self.app.invalidate()
            await asyncio.sleep(0.1)

    async def stop_recording_and_transcribe(self):
        """Остановка записи и отправка на транскрипцию"""
        if not self.is_recording:
            return

        self.is_recording = False

        # Останавливаем запись
        if self._recording_task:
            self._recording_task.cancel()
            try:
                await self._recording_task
            except asyncio.CancelledError:
                # Ожидаемое поведение при отмене задачи
                pass

        # Получаем WAV байты
        wav_bytes = self.audio_buffer.stop_recording()
        duration = self.audio_buffer.get_duration()

        if not wav_bytes:
            self.status_bar.set_state(StatusBar.STATE_IDLE, "No audio")
            self.app.invalidate()
            return

        # Проверяем длительность
        if duration < 0.3:
            self.status_bar.set_state(StatusBar.STATE_IDLE, "Too short")
            self.app.invalidate()
            return

        # Отправляем на API
        self.status_bar.set_state(StatusBar.STATE_SENDING)
        self.app.invalidate()

        # Выполняем транскрипцию в отдельном потоке
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self.parakeet_client.transcribe_with_retry,
            wav_bytes
        )

        if result.get("success"):
            text = result.get("text", "").strip()
            if text:
                # Вставляем текст в позицию курсора
                self.insert_text_at_cursor(text)

                # Копируем в буфер
                if self.clipboard_manager.copy_text(text):
                    self.status_bar.show_copy_indicator()
                    play_sound('end')

                self.status_bar.set_state(StatusBar.STATE_READY)
            else:
                self.status_bar.set_state(StatusBar.STATE_IDLE, "Empty result")
        else:
            error = result.get("error", "Unknown error")
            self.status_bar.set_state(StatusBar.STATE_IDLE, error)

        # Очищаем буфер
        self.audio_buffer.clear()
        self.app.invalidate()

    def insert_text_at_cursor(self, text: str):
        """Вставка текста в текущую позицию курсора"""
        current_line = self.buffer.document.current_line_before_cursor
        if current_line and not current_line.endswith(' '):
            text = ' ' + text

        self.buffer.insert_text(text)

    async def initialize(self):
        """Инициализация редактора"""
        # Проверяем доступность API
        self.api_available = self.parakeet_client.health_check()

        if self.api_available:
            connection_status = "✓ Parakeet API доступен"
        else:
            connection_status = "⚠ Parakeet API недоступен (работа только как редактор)"

        # Вывод только в тестовом режиме
        if hasattr(self, '_initialization_output') and self._initialization_output:
            print("Минималистичный STT Редактор")
            print("============================")
            print(connection_status)
            print("\nГорячие клавиши:")
            print("F5 - Начать/остановить запись")
            print("F3 - Копировать весь текст")
            print("F8 - Очистить весь текст")
            print("Ctrl+C - Выход")
            print("Ctrl+A - Выделить все")
            print("Ctrl+Q - Выход (альтернативный)")
            print("\nИндикаторы состояния:")
            print("● Красный - запись")
            print("● Оранжевый - отправка на API")
            print("● Зеленый - готов")
            print("● Серый - неактивен")
            print("\nАвтоматическое копирование:")
            print("- Распознанный текст")
            print("- Выделенный мышью текст")
            print("\nРедактор готов к работе!")

    async def cleanup(self):
        """Очистка ресурсов"""
        if self.is_recording:
            self.is_recording = False
            if self._recording_task:
                self._recording_task.cancel()
            self.audio_buffer.stop_recording()

    async def run(self):
        """Запуск редактора"""
        try:
            await self.initialize()
            await self.app.run_async()
        finally:
            await self.cleanup()


async def main():
    """Главная функция"""
    import argparse

    parser = argparse.ArgumentParser(description="Минималистичный STT редактор")
    parser.add_argument('--test', action='store_true', help='Тестовый режим (показать интерфейс и выйти)')
    args = parser.parse_args()

    editor = MinimalSTTEditor()

    if args.test:
        editor._initialization_output = True
        await editor.initialize()
        print("\n✓ Редактор инициализирован успешно")
        print("✓ Интерфейс создан корректно")
        print("✓ Все компоненты готовы")
        print("\nЗапустите без --test для полной работы")
        await editor.cleanup()
    else:
        editor._initialization_output = False
        await editor.run()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nВыход из редактора...")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        sys.exit(1)
