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

# Инициализация модели Whisper
model_path = "medium" 
try_cuda = False # Пытаться искать GPU или экономим и используем CPU
# Параметры аудио потока
FORMAT = pyaudio.paInt16  # Формат данных 
CHANNELS = 1             # Моно звук
RATE = 44100              # Частота дискретизации
FRAMES_PER_BUFFER = 4096  # Размер буфера
timeout_duration = 30.0  # максимальная длительность записи в секундах
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

# Функция для запуска записи аудио
def start_recording():
    global recording_active, audio_data
    
    file_path = os.path.join(script_dir, "pop-long.wav")
    play_audio(file_path)

    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=FRAMES_PER_BUFFER)
    # Устанавливаем время начала записи
    start_time = time.time()
    log.info("Начало записи...")

    while recording_active:        
        data = stream.read(FRAMES_PER_BUFFER)
        if data:
            audio_data.append(data)
        if (time.time() - start_time) > timeout_duration:
            recording_active = False

    stream.stop_stream()
    stream.close()
    audio.terminate()
    log.info("Запись завершена")

    transcribe_audio()

def transcribe_audio():
    global audio_data
    
    # Преобразование записанных аудиоданных в байтовый поток
    audio_bytes = b''.join(audio_data)
    
    with io.BytesIO(audio_bytes) as audio_file:        
        # Чтение аудио данных из байтового потока с использованием soundfile
        audio, sample_rate = sf.read(audio_file, format='RAW', 
                                    samplerate=RATE, channels=CHANNELS, 
                                    subtype='PCM_16', dtype='float32')
        # Запись в файл wav для тестирования
        sf.write(tmp_output_file, audio, sample_rate)
        
        # Проверка количества каналов (если больше одного, оставляем только первый канал)
        if len(audio.shape) > 1:
            audio = audio[:, 0]
        result = model.transcribe(audio=tmp_output_file)
        transcribed_text = result['text']
        log.debug("Транскрибированный текст:", transcribed_text)
        pyperclip.copy(result["text"])  # Копируем текст в буфер обмена
        keyboard_controller.press(keyboard.Key.ctrl.value)
        keyboard_controller.press('v')
        keyboard_controller.release('v')
        keyboard_controller.release(keyboard.Key.ctrl.value) 

    audio_data.clear()  # Очищаем данные после использования
    file_path = os.path.join(script_dir, "pop-alert.wav")
    play_audio(file_path)

def on_press(key):
    global recording_active
    try:
        log.debug('alphanumeric key {0} pressed'.format(key.char))
        pass
    except AttributeError:
        log.debug('special key {0} pressed'.format(key))
        pressed_keys.add(key)
        if key == keyboard.Key.print_screen:
            if keyboard.Key.ctrl in pressed_keys and keyboard.Key.ctrl_r in pressed_keys:
                # Завершение программы    
                log.info("Ctrl + Ctrl + PrtScr нажато, завершаем программу...")
                return False  # Остановить слушатель событий
            elif keyboard.Key.ctrl in pressed_keys:
                # Активация или деактивация записи
                recording_active = not recording_active
                if recording_active:
                    threading.Thread(target=start_recording).start()
                log.info(f"Ctrl + PrtScr нажато, запись {'активирована' if recording_active else 'деактивирована'}")

def on_release(key):
    try:
        log.debug('key released {0} '.format(key))
        pressed_keys.remove(key)
    except KeyError:
        pass
 
listener = keyboard.Listener(on_press=on_press, on_release=on_release)

def handle_signal(signum, frame):
    log.info("Signal received, exiting...")
    cleanup()
    listener.stop()
    exit(0)

if not instance_running:
    log.error("Этот скрипт уже запущен.")
    exit()
try:

    signal.signal(signal.SIGINT, handle_signal)  # Ctrl+C
    signal.signal(signal.SIGTERM, handle_signal)  # Termination request

    device = 'cuda' if try_cuda and torch.cuda.is_available() else 'cpu'
    log.info(f"Используем {device}")
    model = whisper.load_model(model_path, device=device)

    with keyboard.Listener(
            on_press=on_press,
            on_release=on_release) as listener:
        log.info("Нажмите Ctrl + PrtScr чтобы активировать или деактивировать запись.")
        log.info("Нажмите Ctrl + Ctrl + PrtScr чтобы завершить программу.")
        listener.join()
 

finally:
    lock_file.close()  # Убедимся, что файл блокировки закрыт при завершении работы программы
