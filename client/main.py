import io
import os
import sys
import tempfile
import getpass
import threading
import pyaudio
import pyperclip
import soundfile as sf
import time
import atexit
import signal
import logging
from pynput import keyboard
from single_instance import check_single_instance

# Добавляем родительскую директорию в PYTHONPATH для импорта common
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
                "server_url": data.get("server_url", "http://localhost:8000"),
                "timeout_duration": float(data.get("record_timeout", 30))
            }
        except Exception as e:
            log.warning(f"Ошибка загрузки настроек: {e}")
    return {
        "server_url": "http://localhost:8000", 
        "timeout_duration": 30.0
    }

settings = load_settings()
server_url = settings["server_url"]
# Параметры аудио потока
FORMAT = pyaudio.paInt16  # Формат данных
CHANNELS = 1             # Моно звук
RATE = 44100              # Частота дискретизации
FRAMES_PER_BUFFER = 4096  # Размер буфера
timeout_duration = settings["timeout_duration"]  # максимальная длительность записи в секундах
lock_file_path = os.path.join(
    tempfile.gettempdir(),
    f"micpy-{getpass.getuser()}.lock"
)  # Кроссплатформенный путь к lock-файлу

script_dir = os.path.dirname(os.path.abspath(__file__))

# Создаём временный wav-файл и сразу закрываем дескриптор
tmp_fd, tmp_output_file = tempfile.mkstemp(suffix=".wav")
os.close(tmp_fd)
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
from audio_recorder_client import AudioRecorderClient

# --- Основной запуск приложения ---
if __name__ == "__main__":
    import signal
    import sys
    import argparse

    def handle_signal(signum, frame):
        log.info("Signal received, exiting...")
        cleanup()
        os._exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    parser = argparse.ArgumentParser(description="micPy: голосовой ввод и транскрипция аудиофайлов")
    parser.add_argument("-f", "--file", type=str, help="Путь к аудиофайлу (wav, mp3, flac и др.) для транскрипции")
    args = parser.parse_args()

    if not instance_running:
        log.error("Этот скрипт уже запущен.")
        sys.exit()

    log.info(f"Подключаемся к серверу: {server_url}")
    
    # --- Проверка доступности сервера ---
    try:
        import requests
        response = requests.get(f"{server_url}/status", timeout=5)
        log.info(f"Сервер доступен: {response.json()}")
    except Exception as e:
        log.error(f"Не удается подключиться к серверу: {e}")

    # --- Транскрипция аудиофайла, если указан аргумент --file ---
    if args.file:
        audio_path = args.file
        if not os.path.isfile(audio_path):
            log.error(f"Файл не найден: {audio_path}")
            sys.exit(1)
        try:
            log.info(f"Отправляем файл на сервер: {audio_path}")
            # Читаем файл и кодируем в base64
            with open(audio_path, 'rb') as f:
                import base64
                audio_base64 = base64.b64encode(f.read()).decode('utf-8')
            
            # Отправляем на сервер
            import requests
            from common.schemas import TranscribeRequest, TranscribeResponse
            
            request = TranscribeRequest(audio_data=audio_base64)
            response = requests.post(f"{server_url}/transcribe", json=request.dict(), timeout=120)
            
            if response.status_code == 200:
                result = TranscribeResponse(**response.json())
                if result.success:
                    print("Распознанный текст:\\n")
                    print(result.text)
                    try:
                        pyperclip.copy(result.text)
                        print("\\nТекст скопирован в буфер обмена.")
                    except Exception as e:
                        print(f"Не удалось скопировать в буфер обмена: {e}")
                else:
                    log.error(f"Ошибка транскрипции: {result.error}")
                    sys.exit(2)
            else:
                log.error(f"Ошибка сервера: {response.status_code}")
                sys.exit(2)
        except Exception as e:
            log.error(f"Ошибка отправки файла: {e}")
            sys.exit(2)
        sys.exit(0)

    recorder = AudioRecorderClient(
        server_url=server_url,
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
    log.info("AudioRecorderClient создан")

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
            manual_stop_callback=manual_stop,
            model=None
        )
        log.info("SettingsWindow создан")
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
        log.info("Listener thread запущен")

        # --- Запуск mainloop только в главном потоке ---
        app.mainloop()
