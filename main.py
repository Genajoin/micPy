import io
import os
import threading
import pyaudio
import whisper
import pyperclip
import torch
from pynput import keyboard
import soundfile as sf
import time
from single_instance import check_single_instance


# Инициализация модели Whisper
model_path = "medium" 
# Параметры аудио потока
FORMAT = pyaudio.paInt16  # Формат данных 
CHANNELS = 1             # Моно звук
RATE = 44100              # Частота дискретизации
FRAMES_PER_BUFFER = 4096  # Размер буфера
timeout_duration = 30.0  # максимальная длительность записи в секундах
lock_file_path = "/tmp/micpy.lock"  # Путь к файлу блокировки
script_dir = os.path.dirname(os.path.abspath(__file__))
tmp_output_file = "/tmp/micpy-output.wav"  # Путь к файлу выходного звука
# Глобальная переменная для хранения состояния активации микрофона
recording_active = False
audio_data = []


instance_running, lock_file = check_single_instance(lock_file_path)

if not instance_running:
    print("Этот скрипт уже запущен.")
    exit()
try:

    if torch.cuda.is_available():
        print("GPU доступен")
    else:
        print("GPU недоступен")
    # Загрузите модель и переместите её на GPU, если доступен
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = whisper.load_model(model_path).to(device)



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
        print("Начало записи...")

        while recording_active:        
            data = stream.read(FRAMES_PER_BUFFER)
            if data:
                audio_data.append(data)
            if (time.time() - start_time) > timeout_duration:
                recording_active = False

        stream.stop_stream()
        stream.close()
        audio.terminate()
        print("Запись завершена")

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
            print("Транскрибированный текст:", transcribed_text)
            pyperclip.copy(result["text"])  # Копируем текст в буфер обмена

        audio_data.clear()  # Очищаем данные после использования
        file_path = os.path.join(script_dir, "pop-alert.wav")
        play_audio(file_path);

    def toggle_recording():
        global recording_active
        
        if not recording_active:
            recording_active = True
            threading.Thread(target=start_recording).start()
        else:
            recording_active = False

    # Функция для обработки нажатия клавиш
    def on_press(key):
        if key == keyboard.Key.ctrl_r:
            toggle_recording()



    # Создание слушателя клавиатуры
    with keyboard.Listener(on_press=on_press) as listener:
        print("Нажмите Ctrl чтобы активировать или деактивировать запись.")
        listener.join()
finally:
    lock_file.close()  # Убедимся, что файл блокировки закрыт при завершении работы программы
