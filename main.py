import io
import os
import threading
import pyaudio
import whisper
import pyperclip
import torch
import soundfile as sf
import time
import atexit
import signal
import logging
from pynput import keyboard
from single_instance import check_single_instance
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# --- Импорт окна настроек ---
try:
    from settings_gui import SettingsWindow
except ImportError:
    SettingsWindow = None

# --- Загрузка настроек из settings.json ---
import json

def load_settings():
    settings_file = "settings.json"
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "model_path": data.get("model_size", "medium"),
                "try_cuda": data.get("use_gpu", False),
                "timeout_duration": float(data.get("record_timeout", 30))
            }
        except Exception as e:
            log.warning(f"Ошибка загрузки настроек: {e}")
    return {
        "model_path": "medium",
        "try_cuda": False,
        "timeout_duration": 30.0
    }

settings = load_settings()
model_path = settings["model_path"]
try_cuda = settings["try_cuda"]
# Параметры аудио потока
FORMAT = pyaudio.paInt16  # Формат данных
CHANNELS = 1             # Моно звук
RATE = 44100              # Частота дискретизации
FRAMES_PER_BUFFER = 4096  # Размер буфера
timeout_duration = settings["timeout_duration"]  # максимальная длительность записи в секундах
lock_file_path = "/tmp/micpy.lock"  # Путь к файлу блокировки
script_dir = os.path.dirname(os.path.abspath(__file__))
tmp_output_file = "/tmp/micpy-output.wav"  # Путь к файлу выходного звука
audio_data = []

instance_running, lock_file = check_single_instance(lock_file_path)
recording_active = False # Флаг для записи
pressed_keys = set() # Множество для отслеживания текущих нажатых клавиш
keyboard_controller = keyboard.Controller()

def cleanup():
    global lock_file
    log.info("Cleaning up resources")
    if lock_file:
        try:
            os.remove(lock_file.name)
        except OSError as e:
            log.info(f"Error removing lock file: {e}")

atexit.register(cleanup)

# Функция воспроизведения звукового файла. В качестве параметра на вход принимает имя файла.
def play_audio(filename):
    data, samplerate = sf.read(filename, dtype='int16')
    # Используем pyaudio для воспроизведения аудио
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=samplerate, output=True)
    stream.write(data.tobytes())
    stream.stop_stream()
    stream.close()
    p.terminate()

# --- Класс для управления записью и распознаванием ---
from audio_recorder import AudioRecorder

# --- Основной запуск приложения ---
if __name__ == "__main__":
    import signal
    import sys

    def handle_signal(signum, frame):
        log.info("Signal received, exiting...")
        cleanup()
        os._exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if not instance_running:
        log.error("Этот скрипт уже запущен.")
        sys.exit()

    device = 'cuda' if try_cuda and torch.cuda.is_available() else 'cpu'
    log.info(f"Используем {device}")
    model = whisper.load_model(model_path, device=device)

    recorder = AudioRecorder(
        model=model,
        script_dir=script_dir,
        play_audio=play_audio,
        tmp_output_file=tmp_output_file,
        keyboard_controller=keyboard_controller,
        keyboard_key=keyboard.Key,
        FORMAT=FORMAT,
        CHANNELS=CHANNELS,
        RATE=RATE,
        FRAMES_PER_BUFFER=FRAMES_PER_BUFFER,
    )

    # --- Callback'и для потокобезопасного обновления GUI ---
    app = None
    def gui_set_status(status):
        if app and hasattr(app, "status"):
            app.after(0, app.status.set, status)
            # Блокировка/разблокировка кнопок по статусу
            if status.startswith("Запись"):
                # Блокировать обе только для автоматического режима
                if not getattr(recorder, "manual_mode", False):
                    app.after(0, app.block_record_buttons)
            if "завершена" in status or "остановлена" in status or "ожидание" in status.lower():
                app.after(0, app.unblock_record_buttons)

    def gui_set_message(msg):
        if app and hasattr(app, "current_message"):
            app.after(0, app.current_message.set, msg)

    def gui_add_history(msg):
        if app and hasattr(app, "add_to_history"):
            app.after(0, app.add_to_history, msg)

    # --- Запуск GUI ---
    if SettingsWindow is not None:
        def manual_start():
            if app:
                app.after(0, app.block_start_button)
                app.after(0, app.unblock_stop_button)
            recorder.start_recording(timeout=None)
        def manual_stop():
            recorder.stop_recording()
            if app:
                app.after(0, app.unblock_start_button)
                app.after(0, app.block_stop_button)
        app = SettingsWindow(
            manual_start_callback=manual_start,
            manual_stop_callback=manual_stop
        )
        # Передаем callback'и
        recorder.set_status_callback(gui_set_status)
        recorder.set_message_callback(gui_set_message)
        recorder.set_history_callback(gui_add_history)

        # --- Запуск Listener в отдельном потоке ---
        def listener_thread():
            def on_press(key):
                global pressed_keys
                pressed_keys.add(key)
                if key == keyboard.Key.print_screen:
                    if keyboard.Key.ctrl in pressed_keys and keyboard.Key.ctrl_r in pressed_keys:
                        log.info("Ctrl + Ctrl + PrtScr нажато, завершаем программу...")
                        handle_signal(signal.SIGTERM, None)
                    elif keyboard.Key.ctrl in pressed_keys:
                        if not recorder.recording_active:
                            recorder.start_recording(timeout=timeout_duration)
                        else:
                            recorder.stop_recording()
                        log.info(f"Ctrl + PrtScr нажато, запись {'активирована' if recorder.recording_active else 'деактивирована'}")

            def on_release(key):
                try:
                    pressed_keys.remove(key)
                except KeyError:
                    pass

            with keyboard.Listener(
                    on_press=on_press,
                    on_release=on_release) as listener:
                log.info("Нажмите Ctrl + PrtScr чтобы активировать или деактивировать запись.")
                log.info("Нажмите Ctrl + Ctrl + PrtScr чтобы завершить программу.")
                listener.join()

        t = threading.Thread(target=listener_thread, daemon=True)
        t.start()

        # --- Запуск mainloop только в главном потоке ---
        app.mainloop()
