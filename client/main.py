import io
import os
import sys
import tempfile
import getpass
import threading
import pyaudio
import pyperclip
import time
import atexit
import signal
import logging
import subprocess
# from pynput import keyboard  # Импорт перенесен ниже
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
                "timeout_duration": float(data.get("record_timeout", 30)),
                "text_insert_method": data.get("text_insert_method", "auto")
            }
        except Exception as e:
            log.warning(f"Ошибка загрузки настроек: {e}")
    return {
        "server_url": "http://localhost:8000", 
        "timeout_duration": 30.0,
        "text_insert_method": "auto"
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

# Импорт pynput как в оригинале
from pynput import keyboard
pressed_keys = set()
keyboard_controller = keyboard.Controller()
use_pynput_hotkeys = '--use-pynput' in sys.argv

if use_pynput_hotkeys:
    log.info("Используется pynput для горячих клавиш")
else:
    log.info("pynput доступен для вставки текста")

log.info("PyAudio будет создаваться для каждого воспроизведения")

def cleanup():
    global lock_file
    log.info("Cleaning up resources")
    if lock_file:
        try:
            os.remove(lock_file.name)
        except OSError as e:
            log.info(f"Error removing lock file: {e}")

atexit.register(cleanup)

# Функция воспроизведения системных звуков
def play_sound(sound_type):
    """
    Воспроизводит системные звуки через canberra.
    sound_type: 'start' для начала записи, 'end' для окончания
    """
    sound_name = 'bell' if sound_type == 'start' else 'message'
    
    log.info(f"play_sound: воспроизводим системный звук '{sound_name}' для события '{sound_type}'")
    try:
        result = subprocess.run(
            ['canberra-gtk-play', '-i', sound_name],
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            timeout=2
        )
        if result.returncode == 0:
            log.info(f"play_sound: звук '{sound_name}' воспроизведен успешно")
        else:
            log.warning(f"play_sound: ошибка воспроизведения звука '{sound_name}', код: {result.returncode}")
    except subprocess.TimeoutExpired:
        log.warning(f"play_sound: таймаут воспроизведения звука '{sound_name}'")
    except Exception as e:
        log.error(f"play_sound: ошибка воспроизведения звука '{sound_name}': {e}")

# --- Класс для управления записью и распознаванием ---
from audio_recorder_client import AudioRecorderClient

# --- Основной запуск приложения ---
if __name__ == "__main__":
    import signal
    import sys
    import argparse

    def handle_signal(signum, frame):
        log.info("Signal received, exiting...")
        # Принудительно завершаем GUI если есть
        global app
        if app:
            try:
                app.quit()
                app.destroy()
            except:
                pass
        cleanup()
        os._exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    parser = argparse.ArgumentParser(description="micPy: голосовой ввод и транскрипция аудиофайлов")
    parser.add_argument("-f", "--file", type=str, help="Путь к аудиофайлу (wav, mp3, flac и др.) для транскрипции")
    parser.add_argument("--start", action="store_true", help="Начать запись (отправить команду работающему экземпляру)")
    parser.add_argument("--stop", action="store_true", help="Остановить запись (отправить команду работающему экземпляру)")
    parser.add_argument("--toggle", action="store_true", help="Переключить запись (отправить команду работающему экземпляру)")
    parser.add_argument("--status", action="store_true", help="Получить статус работающего экземпляра")
    parser.add_argument("--quit", action="store_true", help="Завершить работающий экземпляр")
    parser.add_argument("--use-pynput", action="store_true", help="Использовать pynput для горячих клавиш (старое поведение)")
    args = parser.parse_args()

    # --- Проверка на CLI команды для отправки работающему экземпляру ---
    cli_commands = args.start or args.stop or args.toggle or args.status or args.quit
    
    if cli_commands:
        if not instance_running:
            # Есть запущенный экземпляр, отправляем команду
            from ipc_server import send_command
            
            if args.start:
                log.info("Отправка команды START работающему экземпляру")
                result = send_command("START")
                log.info(f"Результат команды START: {result}")
                print(f"Команда START: {result}")
                sys.exit(0)
            elif args.stop:
                log.info("Отправка команды STOP работающему экземпляру")
                result = send_command("STOP")
                log.info(f"Результат команды STOP: {result}")
                print(f"Команда STOP: {result}")
                sys.exit(0)
            elif args.toggle:
                log.info("Отправка команды TOGGLE работающему экземпляру")
                result = send_command("TOGGLE")
                log.info(f"Результат команды TOGGLE: {result}")
                print(f"Команда TOGGLE: {result}")
                sys.exit(0)
            elif args.status:
                log.info("Запрос статуса у работающего экземпляра")
                result = send_command("STATUS")
                log.info(f"Результат запроса STATUS: {result}")
                print(f"Статус: {result}")
                sys.exit(0)
            elif args.quit:
                log.info("Отправка команды QUIT работающему экземпляру")
                result = send_command("QUIT")
                log.info(f"Результат команды QUIT: {result}")
                print(f"Команда QUIT: {result}")
                sys.exit(0)
        else:
            # Экземпляр не запущен
            log.error("micPy не запущен. Сначала запустите основное приложение: python main.py")
            print("❌ micPy не запущен. Запустите: python main.py")
            sys.exit(1)
    
    # --- Проверка на множественный запуск основного приложения ---
    if not instance_running:
        log.error("Этот скрипт уже запущен. Используйте CLI команды для управления.")
        sys.exit(1)

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
        play_sound=play_sound,
        tmp_output_file=tmp_output_file,
        keyboard_controller=keyboard_controller,
        keyboard_key=keyboard.Key,
        FORMAT=FORMAT,
        CHANNELS=CHANNELS,
        RATE=RATE,
        FRAMES_PER_BUFFER=FRAMES_PER_BUFFER
    )
    recorder.timeout_duration = timeout_duration
    log.info("AudioRecorderClient создан")

    # --- Callback'и для потокобезопасного обновления GUI ---
    app = None  # Глобальная переменная для GUI
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

    def gui_update_connection_status(connected, status_text=""):
        if app and hasattr(app, "update_connection_status"):
            app.after(0, app.update_connection_status, connected, status_text)

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
        recorder.set_connection_status_callback(gui_update_connection_status)

        # --- Запуск IPC сервера для внешних команд ---
        from ipc_server import IPCServer
        ipc_server = IPCServer(recorder, timeout_duration)
        ipc_server.start_server()
        
        # --- Опциональный запуск D-Bus сервиса ---
        dbus_service = None
        try:
            from dbus_service import MicPyRecorderService
            dbus_service = MicPyRecorderService(recorder)
            threading.Thread(target=dbus_service.start_service, daemon=True).start()
            log.info("D-Bus сервис запущен")
        except ImportError:
            log.warning("D-Bus недоступен, используется только IPC")
        except Exception as e:
            log.warning(f"Ошибка запуска D-Bus сервиса: {e}")
        
        # --- Опциональный запуск pynput Listener ---
        if use_pynput_hotkeys and keyboard and keyboard_controller:
            def listener_thread():
                def on_press(key):
                    global pressed_keys
                    pressed_keys.add(key)
                    if key == Key.print_screen:
                        if Key.ctrl in pressed_keys and Key.ctrl_r in pressed_keys:
                            log.info("Ctrl + Ctrl + PrtScr нажато, завершаем программу...")
                            handle_signal(signal.SIGTERM, None)
                        elif Key.ctrl in pressed_keys:
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
            log.info("pynput Listener thread запущен")
        else:
            log.info("Используйте CLI команды или системные горячие клавиши для управления записью")
            log.info("Команды: python main.py --start, --stop, --toggle, --status, --quit")

        # --- Очистка IPC сервера и health check при завершении ---
        def cleanup_ipc():
            if 'ipc_server' in locals():
                ipc_server.stop_server()
            if 'recorder' in locals():
                recorder.stop_health_check()
                
        atexit.register(cleanup_ipc)
        
        # --- Запуск mainloop только в главном потоке ---
        try:
            app.mainloop()
        finally:
            cleanup_ipc()
