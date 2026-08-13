#!/usr/bin/env python3
"""
Модуль буферизации аудио для записи с микрофона.

Кроссплатформенный захват аудио (Linux/macOS) с сохранением в WAV формат.
"""

import io
import os
import math
import struct
import shutil
import tempfile
import wave
import contextlib
import subprocess
import platform
from typing import Optional

try:
    import pyaudio
except ImportError as e:
    raise ImportError(
        f"PyAudio not installed: {e}\n"
        "Install with: pip install pyaudio\n"
        "On macOS: brew install portaudio && pip install pyaudio"
    ) from None


class AudioBuffer:
    """
    Класс для буферизации аудио с микрофона.

    Поддерживает кроссплатформенный захват (Linux/macOS) и сохранение в WAV.
    """

    def __init__(self, sample_rate: int = 16000, channels: int = 1, chunk_size: int = 1024):
        """
        Инициализация аудио буфера.

        Args:
            sample_rate: Частота дискретизации (по умолчанию 16000 Hz)
            channels: Количество каналов (по умолчанию 1 - моно)
            chunk_size: Размер чанка для чтения (по умолчанию 1024)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.sample_width = 2  # 16-bit PCM

        self.frames: bytes = b""
        self.is_recording = False
        self._pyaudio_instance: Optional[pyaudio.PyAudio] = None
        self._audio_stream = None
        self._start_time: float = 0

    @contextlib.contextmanager
    def _suppress_alsa_warnings(self):
        """Подавление ALSA warnings на Linux."""
        try:
            with open(os.devnull, 'w') as devnull:
                old_stderr = os.dup(2)
                os.dup2(devnull.fileno(), 2)
                try:
                    yield
                finally:
                    os.dup2(old_stderr, 2)
                    os.close(old_stderr)
        except Exception:
            # Если не удалось перенаправить stderr, просто продолжаем
            yield

    def _init_audio(self) -> bool:
        """
        Инициализация PyAudio и аудио потока.

        Returns:
            True если инициализация успешна, иначе False
        """
        try:
            if platform.system() == 'Darwin':  # macOS
                self._pyaudio_instance = pyaudio.PyAudio()
                self._audio_stream = self._pyaudio_instance.open(
                    format=pyaudio.paInt16,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=self.chunk_size
                )
            else:  # Linux и другие
                with self._suppress_alsa_warnings():
                    self._pyaudio_instance = pyaudio.PyAudio()
                    self._audio_stream = self._pyaudio_instance.open(
                        format=pyaudio.paInt16,
                        channels=self.channels,
                        rate=self.sample_rate,
                        input=True,
                        frames_per_buffer=self.chunk_size
                    )
            return True
        except Exception as e:
            print(f"Ошибка инициализации аудио: {e}")
            self._cleanup_audio()
            return False

    def _cleanup_audio(self):
        """Очистка ресурсов аудио."""
        try:
            if platform.system() == 'Darwin':  # macOS
                if self._audio_stream:
                    self._audio_stream.stop_stream()
                    self._audio_stream.close()
                    self._audio_stream = None
                if self._pyaudio_instance:
                    self._pyaudio_instance.terminate()
                    self._pyaudio_instance = None
            else:  # Linux
                with self._suppress_alsa_warnings():
                    if self._audio_stream:
                        self._audio_stream.stop_stream()
                        self._audio_stream.close()
                        self._audio_stream = None
                    if self._pyaudio_instance:
                        self._pyaudio_instance.terminate()
                        self._pyaudio_instance = None
        except Exception:
            # Ошибки очистки не критичны, игнорируем
            pass

    def start_recording(self) -> bool:
        """
        Начало записи аудио.

        Returns:
            True если запись началась успешно
        """
        if self.is_recording:
            return True

        if not self._init_audio():
            return False

        import time
        self.frames = b""
        self._start_time = time.time()
        self.is_recording = True
        return True

    def read_chunk(self) -> Optional[bytes]:
        """
        Чтение чанка аудио данных.

        Returns:
            Байты аудио или None если не записываем
        """
        if not self.is_recording or not self._audio_stream:
            return None

        try:
            data = self._audio_stream.read(self.chunk_size, exception_on_overflow=False)
            self.frames += data
            return data
        except Exception as e:
            print(f"Ошибка чтения аудио: {e}")
            return None

    def stop_recording(self) -> bytes:
        """
        Остановка записи и получение аудио данных.

        Returns:
            Байты аудио в формате WAV
        """
        if not self.is_recording:
            return b""

        self.is_recording = False
        self._cleanup_audio()

        # Конвертируем в WAV формат
        return self._create_wav_bytes(self.frames)

    def _create_wav_bytes(self, audio_data: bytes) -> bytes:
        """
        Создание WAV байтов из сырых аудио данных.

        Args:
            audio_data: Сырые аудио данные (PCM)

        Returns:
            WAV байты
        """
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(self.sample_width)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_data)

        return buffer.getvalue()

    def get_duration(self) -> float:
        """
        Получение длительности записанного аудио.

        Returns:
            Длительность в секундах
        """
        if not self.frames:
            return 0.0

        # Расчет длительности: bytes / (sample_rate * channels * sample_width)
        bytes_per_second = self.sample_rate * self.channels * self.sample_width
        return len(self.frames) / bytes_per_second

    def get_recording_duration(self) -> float:
        """
        Получение длительности текущей записи (во время записи).

        Returns:
            Длительность в секундах
        """
        if not self.is_recording:
            return 0.0

        import time
        return time.time() - self._start_time

    def save_to_wav(self, filepath: str) -> bool:
        """
        Сохранение записанного аудио в WAV файл.

        Args:
            filepath: Путь к файлу

        Returns:
            True если сохранение успешно
        """
        if not self.frames:
            return False

        try:
            wav_data = self._create_wav_bytes(self.frames)
            with open(filepath, 'wb') as f:
                f.write(wav_data)
            return True
        except Exception as e:
            print(f"Ошибка сохранения файла: {e}")
            return False

    def clear(self):
        """Очистка буфера."""
        self.frames = b""
        self._start_time = 0

    def get_wav_bytes(self) -> bytes:
        """
        Получение WAV байтов без остановки записи.

        Returns:
            WAV байты текущего буфера
        """
        return self._create_wav_bytes(self.frames)


_SOUND_CACHE: dict = {}


def _get_beep_wav(sound_type: str) -> str:
    """Возвращает путь к WAV-файлу с beep-звуком (генерирует при первом вызове)."""
    if sound_type in _SOUND_CACHE:
        return _SOUND_CACHE[sound_type]

    params = {
        'start': {'freq': 600, 'duration': 0.08},
        'end': {'freq': 1200, 'duration': 0.12},
    }
    p = params.get(sound_type, params['end'])

    path = os.path.join(tempfile.gettempdir(), f'micpy_{sound_type}.wav')
    if not os.path.exists(path):
        sr = 16000
        n = int(sr * p['duration'])
        with wave.open(path, 'w') as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sr)
            fade_n = min(200, n // 4)
            frames = bytearray()
            for i in range(n):
                fade = min(1.0, i / fade_n, (n - i) / fade_n)
                v = int(32767 * 0.3 * fade * math.sin(2 * math.pi * p['freq'] * i / sr))
                frames += struct.pack('<h', v)
            f.writeframes(frames)

    _SOUND_CACHE[sound_type] = path
    return path


def _play_wav_pyaudio(wav_path: str) -> bool:
    """Проиграть WAV через PyAudio output stream (fallback для систем без pw-play)."""
    try:
        if platform.system() != 'Darwin':
            cm = _suppress_alsa_warnings_ctx()
        else:
            cm = contextlib.nullcontext()

        with cm:
            wf = wave.open(wav_path, 'rb')
            pa = pyaudio.PyAudio()
            try:
                stream = pa.open(
                    format=pa.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True
                )
                stream.start_stream()
                data = wf.readframes(wf.getnframes())
                stream.write(data)

                import time as _time
                audio_ms = len(data) / (wf.getframerate() * wf.getsampwidth() * wf.getnchannels()) * 1000
                _time.sleep(audio_ms / 1000 + 0.05)

                stream.stop_stream()
                stream.close()
            finally:
                pa.terminate()
                wf.close()

        return True
    except Exception:
        return False


@contextlib.contextmanager
def _suppress_alsa_warnings_ctx():
    """Подавление ALSA warnings."""
    try:
        with open(os.devnull, 'w') as devnull:
            old_stderr = os.dup(2)
            os.dup2(devnull.fileno(), 2)
            try:
                yield
            finally:
                os.dup2(old_stderr, 2)
                os.close(old_stderr)
    except Exception:
        yield


def play_sound(sound_type: str = 'start'):
    """
    Воспроизведение звука-уведомления.

    Использует оторванный subprocess с чистым окружением и задержкой —
    чтобы дать PipeWire время освободить ресурсы записи.

    Args:
        sound_type: 'start' для начала записи, 'end' для окончания
    """
    import logging
    logger = logging.getLogger('PlaySound')

    wav_path = _get_beep_wav(sound_type)

    uid = os.getuid()
    clean_env = {
        'XDG_RUNTIME_DIR': f'/run/user/{uid}',
        'PATH': '/usr/bin:/bin:/usr/local/bin',
        'HOME': os.path.expanduser('~'),
        'LANG': 'en_US.UTF-8',
    }

    pw_play = shutil.which('pw-play')
    if pw_play:
        delay = '0.15' if sound_type == 'end' else '0'
        try:
            proc = subprocess.Popen(
                ['bash', '-c', f'sleep {delay} && exec {pw_play} "{wav_path}"'],
                env=clean_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            logger.info(f"pw-play pid={proc.pid}, sound={sound_type}")
            return
        except Exception as e:
            logger.warning(f"pw-play failed: {e}")

    if _play_wav_pyaudio(wav_path):
        logger.info(f"played via pyaudio fallback, sound={sound_type}")
        return

    try:
        print('\a', end='', flush=True)
    except Exception:
        pass
