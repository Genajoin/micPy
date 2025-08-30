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

# Добавляем родительскую директорию в PYTHONPATH для импорта common
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.schemas import TranscribeRequest, TranscribeResponse
from common.audio_utils import encode_audio_to_base64
# text_inserter не используется, оставлена простая вставка

log = logging.getLogger(__name__)

class AudioRecorderClient:
    def __init__(
        self, server_url, script_dir,
        play_audio, tmp_output_file, keyboard_controller, keyboard_key,
        FORMAT, CHANNELS, RATE, FRAMES_PER_BUFFER,
        status_callback=None, message_callback=None, history_callback=None
    ):
        self.server_url = server_url.rstrip('/')
        self.script_dir = script_dir
        self.play_audio = play_audio
        log.info(f"AudioRecorderClient: инициализирован с play_audio={play_audio is not None}, script_dir={script_dir}")
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
        self.recording_active = False
        self.audio_data = []
        self.manual_mode = False
        
        # TextInserter убран, используется простая вставка

    def set_status_callback(self, cb):
        self.status_callback = cb

    def set_message_callback(self, cb):
        self.message_callback = cb

    def set_history_callback(self, cb):
        self.history_callback = cb

    def update_status(self, status):
        if self.status_callback:
            self.status_callback(status)

    def update_message(self, msg):
        if self.message_callback:
            self.message_callback(msg)

    def add_history(self, msg):
        if self.history_callback:
            self.history_callback(msg)

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
        log.info("_record: метод запущен")
        file_path = os.path.join(self.script_dir, "pop-alert.wav")
        log.info(f"_record: пытаемся воспроизвести начальный звук {file_path}")
        try:
            self.play_audio(file_path)
            log.info("_record: начальный звук воспроизведен")
        except Exception as e:
            log.error(f"_record: ошибка воспроизведения начального звука: {e}")
        
        # Создаем новый PyAudio экземпляр для записи
        log.info("_record: создаем PyAudio экземпляр для записи")
        audio = pyaudio.PyAudio()
        stream = audio.open(format=self.FORMAT,
                            channels=self.CHANNELS,
                            rate=self.RATE,
                            input=True,
                            frames_per_buffer=self.FRAMES_PER_BUFFER)
        start_time = time.time()
        self.update_status("Запись...")
        log.info("Начало записи...")

        while self.recording_active:
            data = stream.read(self.FRAMES_PER_BUFFER)
            if data:
                self.audio_data.append(data)
            if not self.manual_mode and (time.time() - start_time) > timeout:
                self.recording_active = False

        stream.stop_stream()
        stream.close()
        log.info("_record: завершаем PyAudio экземпляр для записи")
        audio.terminate()
        self.update_status("Запись завершена")
        log.info("Запись завершена")
        self.transcribe_audio_remote()

    def transcribe_audio_remote(self):
        self.update_status("Отправка на сервер...")
        try:
            # Конвертируем аудио данные
            audio_bytes = b''.join(self.audio_data)
            
            # Кодируем в base64
            audio_base64 = encode_audio_to_base64(audio_bytes, self.RATE, self.CHANNELS)
            
            # Отправляем запрос на сервер
            request = TranscribeRequest(audio_data=audio_base64)
            
            self.update_status("Распознавание на сервере...")
            response = requests.post(
                f"{self.server_url}/transcribe",
                json=request.dict(),
                timeout=60
            )
            
            if response.status_code == 200:
                result = TranscribeResponse(**response.json())
                if result.success:
                    transcribed_text = result.text
                    log.info(f"Транскрипция завершена за {result.processing_time:.2f}s")
                    
                    # Копируем в буфер обмена
                    try:
                        pyperclip.copy(transcribed_text)
                    except Exception as e:
                        log.warning(f"Не удалось скопировать в буфер обмена: {e}")
                    
                    if self.message_callback:
                        self.message_callback(transcribed_text)
                    if self.history_callback:
                        self.history_callback(transcribed_text)
                    
                    # Умная автовставка - пробуем обе комбинации
                    if self.keyboard_controller and self.Key:
                        try:
                            # Сначала пробуем Ctrl+Shift+V (для терминалов)
                            self.keyboard_controller.press(self.Key.ctrl)
                            self.keyboard_controller.press(self.Key.shift) 
                            self.keyboard_controller.press('v')
                            self.keyboard_controller.release('v')
                            self.keyboard_controller.release(self.Key.shift)
                            self.keyboard_controller.release(self.Key.ctrl)
                            
                            time.sleep(0.05)  # Короткая пауза
                            
                            # Затем пробуем обычный Ctrl+V (для остальных приложений)
                            self.keyboard_controller.press(self.Key.ctrl)
                            self.keyboard_controller.press('v')
                            self.keyboard_controller.release('v')
                            self.keyboard_controller.release(self.Key.ctrl)
                            
                            log.info("Автовставка выполнена (обе комбинации)")
                        except Exception as e:
                            log.warning(f"Ошибка автовставки: {e}")
                    
                    self.update_status("Готово")
                else:
                    error_msg = f"Ошибка сервера: {result.error}"
                    log.error(error_msg)
                    self.update_status(error_msg)
            else:
                error_msg = f"Ошибка HTTP {response.status_code}: {response.text}"
                log.error(error_msg)
                self.update_status(error_msg)
                
        except requests.exceptions.ConnectionError:
            error_msg = "Не удается подключиться к серверу"
            log.error(error_msg)
            self.update_status(error_msg)
        except Exception as e:
            error_msg = f"Ошибка отправки: {e}"
            log.error(error_msg)
            self.update_status(error_msg)
        finally:
            self.audio_data.clear()
            file_path = os.path.join(self.script_dir, "pop-alert.wav")
            self.play_audio(file_path)