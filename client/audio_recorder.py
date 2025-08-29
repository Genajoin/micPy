import io
import os
import threading
import time
import pyaudio
import soundfile as sf
import pyperclip
import logging

log = logging.getLogger(__name__)

class AudioRecorder:
    def __init__(
        self, model, script_dir,
        play_audio, tmp_output_file, keyboard_controller, keyboard_key,
        FORMAT, CHANNELS, RATE, FRAMES_PER_BUFFER,
        status_callback=None, message_callback=None, history_callback=None
    ):
        self.model = model
        self.script_dir = script_dir
        self.play_audio = play_audio
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
        file_path = os.path.join(self.script_dir, "pop-long.wav")
        self.play_audio(file_path)
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
        audio.terminate()
        self.update_status("Запись завершена")
        log.info("Запись завершена")
        self.transcribe_audio()

    def transcribe_audio(self):
        audio_bytes = b''.join(self.audio_data)
        with io.BytesIO(audio_bytes) as audio_file:
            audio, sample_rate = sf.read(audio_file, format='RAW',
                                         samplerate=self.RATE, channels=self.CHANNELS,
                                         subtype='PCM_16', dtype='float32')
            sf.write(self.tmp_output_file, audio, sample_rate)
            if len(audio.shape) > 1:
                audio = audio[:, 0]
            result = self.model.transcribe(audio=self.tmp_output_file)
            transcribed_text = result['text']
            log.debug("Транскрибированный текст: %s", transcribed_text)
            try:
                pyperclip.copy(result["text"])
            except Exception as e:
                log.warning(f"Не удалось скопировать в буфер обмена: {e}")
            if self.message_callback:
                self.message_callback(transcribed_text)
            if self.history_callback:
                self.history_callback(transcribed_text)
        # --- Вставка текста в буфер обмена через эмуляцию Ctrl+V ---
        self.keyboard_controller.press(self.Key.ctrl)
        self.keyboard_controller.press('v')
        self.keyboard_controller.release('v')
        self.keyboard_controller.release(self.Key.ctrl)
        self.audio_data.clear()
        file_path = os.path.join(self.script_dir, "pop-alert.wav")
        self.play_audio(file_path)
        # Удаляем временный аудиофайл после использования
        try:
            os.remove(self.tmp_output_file)
            log.info(f"Временный файл {self.tmp_output_file} удалён.")
        except Exception as e:
            log.warning(f"Не удалось удалить временный файл {self.tmp_output_file}: {e}")