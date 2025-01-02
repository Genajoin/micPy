import io
import threading
import pyaudio
import whisper
import pyperclip
import torch
from pynput import keyboard
import soundfile as sf

# Инициализация модели Whisper
model_path = "medium" 
# Параметры аудио потока
FORMAT = pyaudio.paInt16  # Формат данных 
CHANNELS = 1             # Моно звук
RATE = 44100              # Частота дискретизации
FRAMES_PER_BUFFER = 4096  # Размер буфера

# Глобальная переменная для хранения состояния активации микрофона
recording_active = False
audio_data = []

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
    
    play_audio("pop-long.wav");

    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=FRAMES_PER_BUFFER)
    print("Начало записи...")
    
    while recording_active:
        data = stream.read(FRAMES_PER_BUFFER)
        if data:
            audio_data.append(data)

    stream.stop_stream()
    stream.close()
    audio.terminate()

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
        sf.write('output.wav', audio, sample_rate)
        
        # Проверка количества каналов (если больше одного, оставляем только первый канал)
        if len(audio.shape) > 1:
            audio = audio[:, 0]
        result = model.transcribe(audio="output.wav")
        transcribed_text = result['text']
        print("Транскрибированный текст:", transcribed_text)
        pyperclip.copy(result["text"])  # Копируем текст в буфер обмена

    audio_data.clear()  # Очищаем данные после использования
    play_audio("pop-alert.wav");

def toggle_recording():
    global recording_active
    
    if not recording_active:
        recording_active = True
        threading.Thread(target=start_recording).start()
        print("Запись активирована")
    else:
        recording_active = False
        transcribe_audio()
        print("Запись завершена и транскрибция выполнена")

# Функция для обработки нажатия клавиш
def on_press(key):
    if key == keyboard.Key.ctrl_r:
        toggle_recording()


# Создание слушателя клавиатуры
with keyboard.Listener(on_press=on_press) as listener:
    print("Нажмите Ctrl чтобы активировать или деактивировать запись.")
    listener.join()

