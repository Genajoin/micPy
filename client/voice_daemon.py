#!/usr/bin/env python3
"""
Фоновый сервис голосового ввода.

Активируется через Unix сокет, записывает аудио,
транскрибирует через Parakeet API и вставляет текст через буфер обмена.

Использование:
  1. Запустите демон: mic-stream daemon --socket
  2. Привяжите команду к хоткею в DE: mic-stream trigger
  3. GNOME: Settings → Keyboard → Custom Shortcuts
"""

import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from client.audio_buffer import AudioBuffer, play_sound
from client.parakeet_client import ParakeetClient

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('VoiceDaemon')

# Путь к сокету по умолчанию
DEFAULT_SOCKET_PATH = Path.home() / '.cache' / 'voice-input.sock'


class VoiceInputDaemon:
    """
    Демон голосового ввода.

    Активируется через Unix сокет, записывает аудио с микрофона,
    отправляет на транскрипцию и вставляет результат через буфер обмена.
    """

    def __init__(
        self,
        api_url: str = "http://localhost:5092/v1",
        model: str = "parakeet-tdt-0.6b-v3",
        socket_path: Optional[Path] = None
    ):
        """
        Инициализация демона.

        Args:
            api_url: URL Parakeet API
            model: Модель для транскрипции
            socket_path: Путь к Unix сокету
        """
        self.api_url = api_url
        self.model = model
        self.socket_path = socket_path or DEFAULT_SOCKET_PATH

        self.audio_buffer = AudioBuffer(sample_rate=16000, channels=1)
        self.api_client = ParakeetClient(api_url=api_url, model=model)
        self.is_recording = False
        self._lock = threading.Lock()
        self._running = False
        self._socket: Optional[socket.socket] = None
        self._recording_thread: Optional[threading.Thread] = None

        logger.info("VoiceInputDaemon initialized")
        logger.info(f"  API: {api_url}")
        logger.info(f"  Model: {model}")
        logger.info(f"  Socket: {self.socket_path}")

    def _check_dependencies(self) -> bool:
        """Проверка системных зависимостей."""
        # Для текущей реализации (только запись + буфер) системные зависимости не нужны
        # pyperclip работает через wl-clipboard/xclip автоматически
        return True

    def toggle_recording(self):
        """Переключение состояния записи."""
        with self._lock:
            if not self.is_recording:
                self._start_recording()
            else:
                self._stop_and_transcribe()

    def _recording_loop(self):
        """Цикл записи аудио (выполняется в отдельном потоке)."""
        while self.is_recording:
            self.audio_buffer.read_chunk()
            time.sleep(0.05)  # 50ms интервал для снижения нагрузки на CPU

    def _start_recording(self):
        """Начало записи."""
        logger.info("Starting recording...")

        # Начать запись аудио
        if not self.audio_buffer.start_recording():
            logger.error("Failed to start recording")
            return

        self.is_recording = True

        # Запустить поток записи
        self._recording_thread = threading.Thread(target=self._recording_loop, daemon=True)
        self._recording_thread.start()

        # Звук в фоне, не блокирует запись
        threading.Thread(target=play_sound, args=('start',), daemon=True).start()
        logger.info("Recording started - speak now")

    def _stop_and_transcribe(self):
        """Остановка записи и транскрипция."""
        logger.info("Stopping recording...")

        # Сначала останавливаем запись (это остановит поток)
        self.is_recording = False

        # Ждем завершения потока записи
        if self._recording_thread and self._recording_thread.is_alive():
            self._recording_thread.join(timeout=1.0)

        # Получаем записанные данные
        wav_bytes = self.audio_buffer.stop_recording()
        duration = self.audio_buffer.get_duration()
        logger.info(f"Recording stopped, duration: {duration:.1f}s")

        # Проверить длительность
        if duration < 0.5:
            logger.warning("Recording too short, skipping transcription")
            threading.Thread(target=play_sound, args=('end',), daemon=True).start()
            self.audio_buffer.clear()
            return

        # Сначала отправляем в API, потом звук в фоне
        logger.info("Sending to API...")
        result = self.api_client.transcribe_with_retry(wav_bytes, max_retries=2)

        # Звук после отправки запроса (не блокирует)
        threading.Thread(target=play_sound, args=('end',), daemon=True).start()

        if result["success"]:
            text = result["text"]
            if text:
                logger.info(f"Transcription: {text}")
                # Скопировать в буфер
                try:
                    import pyperclip
                    pyperclip.copy(text)
                    logger.info("Text copied to clipboard - press Ctrl+V to paste")
                except Exception as e:
                    logger.error(f"Failed to copy to clipboard: {e}")
            else:
                logger.warning("Empty transcription (no speech detected)")
        else:
            error = result.get("error", "Unknown error")
            logger.error(f"Transcription failed: {error}")

        # Очистить буфер
        self.audio_buffer.clear()

    def run(self):
        """Запуск демона."""
        logger.info("=" * 50)
        logger.info("Voice Input Daemon starting...")
        logger.info("=" * 50)

        # Проверка зависимостей
        if not self._check_dependencies():
            logger.error("Dependency check failed, exiting")
            sys.exit(1)

        # Проверка доступности API
        if self.api_client.health_check():
            logger.info(f"API is available: {self.api_url}")
        else:
            logger.warning(f"API health check failed: {self.api_url}")
            logger.warning("Daemon will start anyway, but transcription may fail")

        self._running = True
        self._run_socket_mode()

    def _run_socket_mode(self):
        """Запуск в режиме Unix сокета."""
        # Создаем директорию для сокета
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        # Удаляем старый сокет если есть
        if self.socket_path.exists():
            self.socket_path.unlink()

        # Создаем Unix сокет
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.bind(str(self.socket_path))
        self._socket.listen(1)
        self._socket.settimeout(1.0)  # Таймаут для проверки _running

        logger.info("=" * 50)
        logger.info("Voice Input Daemon is running!")
        logger.info(f"Socket: {self.socket_path}")
        logger.info("")
        logger.info("To trigger, run:")
        logger.info("  mic-stream trigger")
        logger.info("")
        logger.info("Or bind this command to a keyboard shortcut in your DE:")
        logger.info("  GNOME: Settings → Keyboard → Custom Shortcuts")
        logger.info("  KDE: System Settings → Shortcuts")
        logger.info("")
        logger.info("Press Ctrl+C to exit")
        logger.info("=" * 50)

        try:
            while self._running:
                try:
                    conn, _ = self._socket.accept()
                    with conn:
                        data = conn.recv(1024)
                        if data:
                            logger.info("Trigger received via socket")
                            self.toggle_recording()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self._running:
                        logger.error(f"Socket error: {e}")
        except KeyboardInterrupt:
            logger.info("\nShutting down...")
        finally:
            self._running = False
            self._cleanup_socket()

    def _cleanup_socket(self):
        """Очистка сокета."""
        if self._socket:
            self._socket.close()
            self._socket = None
        if self.socket_path.exists():
            self.socket_path.unlink()


def main():
    """Точка входа для демона."""
    import argparse

    parser = argparse.ArgumentParser(description="Voice Input Daemon")
    parser.add_argument(
        '--api-url',
        default=os.environ.get('PARAKEET_API_URL', 'http://localhost:5092/v1'),
        help='URL Parakeet API (default: http://localhost:5092/v1)'
    )
    parser.add_argument(
        '--model',
        default=os.environ.get('PARAKEET_MODEL', 'parakeet-tdt-0.6b-v3'),
        help='Model for transcription'
    )
    parser.add_argument(
        '--socket-path',
        type=Path,
        default=None,
        help=f'Unix socket path (default: {DEFAULT_SOCKET_PATH})'
    )

    args = parser.parse_args()

    daemon = VoiceInputDaemon(
        api_url=args.api_url,
        model=args.model,
        socket_path=args.socket_path
    )
    daemon.run()


def send_trigger(socket_path: Optional[Path] = None) -> bool:
    """
    Отправить триггер на демон через сокет.

    Args:
        socket_path: Путь к сокету

    Returns:
        True если успешно
    """
    path = str(socket_path or DEFAULT_SOCKET_PATH)

    if not Path(path).exists():
        logger.error(f"Socket not found: {path}")
        logger.error("Is the daemon running?")
        return False

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(path)
        sock.sendall(b'trigger')
        sock.close()
        return True
    except Exception as e:
        logger.error(f"Failed to send trigger: {e}")
        return False


if __name__ == '__main__':
    main()
