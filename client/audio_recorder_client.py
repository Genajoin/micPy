import io
import os
import sys
import threading
import time
import pyaudio
import soundfile as sf
import pyperclip
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Добавляем родительскую директорию в PYTHONPATH для импорта common
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.schemas import TranscribeRequest, TranscribeResponse
from common.audio_utils import encode_audio_to_base64
# text_inserter не используется, оставлена простая вставка

log = logging.getLogger(__name__)

class AudioRecorderClient:
    def __init__(
        self, server_url, script_dir,
        play_sound, tmp_output_file, keyboard_controller, keyboard_key,
        FORMAT, CHANNELS, RATE, FRAMES_PER_BUFFER,
        status_callback=None, message_callback=None, history_callback=None,
        connection_status_callback=None
    ):
        self.server_url = server_url.rstrip('/')
        self.script_dir = script_dir
        self.play_sound = play_sound
        log.info(f"AudioRecorderClient: инициализирован с play_sound={play_sound is not None}")
        self.tmp_output_file = tmp_output_file
        self.keyboard_controller = keyboard_controller
        self.Key = keyboard_key
        self.FORMAT = FORMAT
        self.CHANNELS = CHANNELS
        self.RATE = RATE
        self.FRAMES_PER_BUFFER = FRAMES_PER_BUFFER
        self.status_callback = status_callback
        self.message_callback = message_callback
        self.history_callback = history_callback
        self.connection_status_callback = connection_status_callback
        self.recording_active = False
        self.audio_data = []
        self.manual_mode = False
        self.server_connected = False
        self.last_connection_check = 0
        self.health_check_thread = None
        self.health_check_active = False
        
        
        # Настройка requests session с retry политикой
        self.session = requests.Session()
        retry_strategy = Retry(
            total=5,
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=1,
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Запуск health check
        self._start_health_check()
        
        # TextInserter убран, используется простая вставка

    def set_status_callback(self, cb):
        self.status_callback = cb

    def set_message_callback(self, cb):
        self.message_callback = cb

    def set_history_callback(self, cb):
        self.history_callback = cb

    def set_connection_status_callback(self, cb):
        self.connection_status_callback = cb

    def update_connection_status(self, connected, status_text=""):
        if self.connection_status_callback:
            self.connection_status_callback(connected, status_text)

    def update_status(self, status):
        if self.status_callback:
            self.status_callback(status)

    def update_message(self, msg):
        if self.message_callback:
            self.message_callback(msg)

    def add_history(self, msg):
        if self.history_callback:
            self.history_callback(msg)

    def _start_health_check(self):
        """Запуск фонового потока для проверки соединения с сервером"""
        if self.health_check_active:
            return
        
        self.health_check_active = True
        self.health_check_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self.health_check_thread.start()
        log.info("Health check поток запущен")

    def _health_check_loop(self):
        """Фоновая проверка соединения каждые 30 секунд"""
        last_suspend_time = time.time()
        
        while self.health_check_active:
            current_time = time.time()
            
            # Проверка на пробуждение после сна (если время скачка больше 60 сек)
            if current_time - last_suspend_time > 90:
                log.info("Обнаружено пробуждение системы, проверяем соединение")
                self.update_status("Проверка соединения после пробуждения...")
                self._check_connection_immediately()
            
            last_suspend_time = current_time
            
            try:
                response = self.session.get(f"{self.server_url}/status", timeout=3)
                if response.status_code == 200:
                    if not self.server_connected:
                        self.server_connected = True
                        log.info("Соединение с сервером восстановлено")
                        self.update_status("Соединение восстановлено")
                        self.update_connection_status(True)
                else:
                    self._handle_connection_loss()
            except Exception:
                self._handle_connection_loss()
            
            time.sleep(30)

    def _check_connection_immediately(self):
        """Немедленная проверка соединения (например, после пробуждения)"""
        try:
            response = self.session.get(f"{self.server_url}/status", timeout=5)
            if response.status_code == 200:
                self.server_connected = True
                log.info("Соединение с сервером подтверждено")
                self.update_status("Готово")
                self.update_connection_status(True)
            else:
                self._handle_connection_loss()
        except Exception as e:
            log.warning(f"Проверка соединения не удалась: {e}")
            self._handle_connection_loss()

    def _handle_connection_loss(self):
        """Обработка потери соединения"""
        if self.server_connected:
            self.server_connected = False
            log.warning("Потеря соединения с сервером")
            self.update_status("Нет соединения с сервером")
            self.update_connection_status(False, "Отключено")

    def _retry_request(self, func, *args, **kwargs):
        """Выполнение запроса с повторными попытками при ошибке соединения"""
        max_retries = 5
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.ConnectionError as e:
                if attempt == max_retries - 1:
                    log.error(f"Все попытки подключения исчерпаны: {e}")
                    raise
                
                delay = base_delay * (2 ** attempt)
                log.warning(f"Попытка {attempt + 1}/{max_retries} неудачна, повтор через {delay}с: {e}")
                self.update_status(f"Переподключение... (попытка {attempt + 1}/{max_retries})")
                self.update_connection_status(False, f"Переподключение ({attempt + 1}/{max_retries})")
                time.sleep(delay)
            except Exception as e:
                log.error(f"Неожиданная ошибка при запросе: {e}")
                raise

    def stop_health_check(self):
        """Остановка health check потока"""
        self.health_check_active = False
        if self.health_check_thread and self.health_check_thread.is_alive():
            self.health_check_thread.join(timeout=1)

    def start_recording(self, timeout=None):
        if self.recording_active:
            return
        self.recording_active = True
        self.audio_data = []
        self.manual_mode = timeout is None
        threading.Thread(target=self._record, args=(timeout,)).start()

    def stop_recording(self):
        self.recording_active = False

    def _record(self, timeout):
        total_start_time = time.perf_counter()
        log.info("[TIMING] _record: метод запущен")
        
        # Параллельный запуск звука и инициализации записи
        sound_thread = threading.Thread(target=self._play_start_sound_async, daemon=True)
        sound_thread.start()
        
        # Измеряем время создания PyAudio
        audio_init_start = time.perf_counter()
        log.info("[TIMING] Создаем PyAudio экземпляр")
        audio = pyaudio.PyAudio()
        audio_init_time = (time.perf_counter() - audio_init_start) * 1000
        log.info(f"[TIMING] PyAudio создан за {audio_init_time:.1f}мс")
        
        # Измеряем время открытия stream
        stream_init_start = time.perf_counter()
        log.info("[TIMING] Открываем audio stream")
        stream = audio.open(format=self.FORMAT,
                            channels=self.CHANNELS,
                            rate=self.RATE,
                            input=True,
                            frames_per_buffer=self.FRAMES_PER_BUFFER)
        stream_init_time = (time.perf_counter() - stream_init_start) * 1000
        log.info(f"[TIMING] Audio stream открыт за {stream_init_time:.1f}мс")
        
        total_init_time = (time.perf_counter() - total_start_time) * 1000
        log.info(f"[TIMING] Общее время инициализации записи: {total_init_time:.1f}мс")
        
        start_time = time.time()
        self.update_status("Запись...")
        log.info("Начало записи...")

        while self.recording_active:
            data = stream.read(self.FRAMES_PER_BUFFER)
            if data:
                self.audio_data.append(data)
            if not self.manual_mode and (time.time() - start_time) > timeout:
                self.recording_active = False

        # Измеряем время закрытия stream
        cleanup_start = time.perf_counter()
        stream.stop_stream()
        stream.close()
        audio.terminate()
        cleanup_time = (time.perf_counter() - cleanup_start) * 1000
        log.info(f"[TIMING] Очистка PyAudio ресурсов заняла {cleanup_time:.1f}мс")
        self.update_status("Запись завершена")
        log.info("Запись завершена")
        self.transcribe_audio_remote()

    def transcribe_audio_remote(self):
        transcription_start_time = time.perf_counter()
        self.update_status("Отправка на сервер...")
        log.info("[TIMING] Начало процесса транскрипции")
        try:
            # Измеряем время подготовки данных
            prep_start = time.perf_counter()
            audio_bytes = b''.join(self.audio_data)
            audio_base64 = encode_audio_to_base64(audio_bytes, self.RATE, self.CHANNELS)
            prep_time = (time.perf_counter() - prep_start) * 1000
            log.info(f"[TIMING] Подготовка аудио данных заняла {prep_time:.1f}мс")
            
            # Отправляем запрос на сервер
            request = TranscribeRequest(audio_data=audio_base64)
            
            self.update_status("Распознавание на сервере...")
            
            # Измеряем время сетевого запроса
            network_start = time.perf_counter()
            def make_request():
                return self.session.post(
                    f"{self.server_url}/transcribe",
                    json=request.dict(),
                    timeout=60
                )
            
            response = self._retry_request(make_request)
            network_time = (time.perf_counter() - network_start) * 1000
            log.info(f"[TIMING] Сетевой запрос занял {network_time:.1f}мс")
            
            if response.status_code == 200:
                result = TranscribeResponse(**response.json())
                if result.success:
                    transcribed_text = result.text
                    total_transcription_time = (time.perf_counter() - transcription_start_time) * 1000
                    log.info(f"[TIMING] Полное время транскрипции: {total_transcription_time:.1f}мс")
                    log.info(f"[TIMING] Время обработки на сервере: {result.processing_time * 1000:.1f}мс")
                    
                    # Параллельное выполнение финальных операций
                    self._handle_successful_transcription(transcribed_text)
                    self.server_connected = True
                else:
                    error_msg = f"Ошибка сервера: {result.error}"
                    log.error(error_msg)
                    self.update_status(error_msg)
            else:
                error_msg = f"Ошибка HTTP {response.status_code}: {response.text}"
                log.error(error_msg)
                self.update_status(error_msg)
                
        except requests.exceptions.ConnectionError:
            error_msg = "Не удается подключиться к серверу после всех попыток"
            log.error(error_msg)
            self.update_status(error_msg)
            self.server_connected = False
        except Exception as e:
            error_msg = f"Ошибка отправки: {e}"
            log.error(error_msg)
            self.update_status(error_msg)
        finally:
            self.audio_data.clear()

    def _play_start_sound_async(self):
        """Асинхронное воспроизведение звука начала записи"""
        try:
            sound_start = time.perf_counter()
            log.info("[TIMING] Запуск звука начала записи")
            self.play_sound('start')
            sound_time = (time.perf_counter() - sound_start) * 1000
            log.info(f"[TIMING] Звук начала записи воспроизведен за {sound_time:.1f}мс")
        except Exception as e:
            log.error(f"_play_start_sound_async: ошибка воспроизведения звука начала: {e}")
    
    def _handle_successful_transcription(self, transcribed_text):
        """Параллельная обработка успешной транскрипции"""
        # Измеряем время копирования в буфер обмена
        clipboard_start = time.perf_counter()
        try:
            pyperclip.copy(transcribed_text)
            clipboard_time = (time.perf_counter() - clipboard_start) * 1000
            log.info(f"[TIMING] Копирование в буфер обмена заняло {clipboard_time:.1f}мс")
        except Exception as e:
            log.warning(f"Не удалось скопировать в буфер обмена: {e}")
        
        # Обновляем GUI
        if self.message_callback:
            self.message_callback(transcribed_text)
        if self.history_callback:
            self.history_callback(transcribed_text)
        
        # Запускаем звук окончания и автовставку параллельно
        end_sound_thread = threading.Thread(target=self._play_end_sound_async, daemon=True)
        auto_paste_thread = threading.Thread(target=self._auto_paste_async, daemon=True)
        
        end_sound_thread.start()
        auto_paste_thread.start()
        
        self.update_status("Готово")
    
    def _play_end_sound_async(self):
        """Асинхронное воспроизведение звука окончания записи"""
        try:
            sound_start = time.perf_counter()
            log.info("[TIMING] Запуск звука окончания записи")
            self.play_sound('end')
            sound_time = (time.perf_counter() - sound_start) * 1000
            log.info(f"[TIMING] Звук окончания записи воспроизведен за {sound_time:.1f}мс")
        except Exception as e:
            log.error(f"_play_end_sound_async: ошибка воспроизведения звука окончания: {e}")
    
    def _auto_paste_async(self):
        """Асинхронная автовставка текста"""
        if not (self.keyboard_controller and self.Key):
            return
        
        try:
            paste_start = time.perf_counter()
            log.info("[TIMING] Начало автовставки")
            
            # Небольшая задержка чтобы звук успел начаться
            time.sleep(0.1)
            
            # Используем обычный Ctrl+V
            self.keyboard_controller.press(self.Key.ctrl)
            self.keyboard_controller.press('v')
            self.keyboard_controller.release('v')
            self.keyboard_controller.release(self.Key.ctrl)
            
            paste_time = (time.perf_counter() - paste_start) * 1000
            log.info(f"[TIMING] Автовставка выполнена за {paste_time:.1f}мс")
        except Exception as e:
            log.warning(f"Ошибка асинхронной автовставки: {e}")

    def __del__(self):
        """Очистка ресурсов при удалении объекта"""
        self.stop_health_check()
        
        # PyAudio ресурсы теперь создаются и очищаются в каждой сессии записи
        # Нет постоянных ресурсов для очистки
        
        if hasattr(self, 'session'):
            self.session.close()