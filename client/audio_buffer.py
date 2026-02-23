#!/usr/bin/env python3
"""
Модуль буферизации аудио для записи с микрофона.

Кроссплатформенный захват аудио (Linux/macOS) с сохранением в WAV формат.
"""

import io
import os
import wave
import contextlib
import subprocess
import platform
from typing import Optional, Tuple

try:
    import pyaudio
except ImportError as e:
    raise ImportError(
        f"PyAudio not installed: {e}\n"
        "Install with: pip install pyaudio\n"
        "On macOS: brew install portaudio && pip install pyaudio"
    )


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


def play_sound(sound_type: str = 'start'):
    """
    Кроссплатформенное воспроизведение системных звуков.

    Args:
        sound_type: 'start' для начала записи, 'end' для окончания
    """
    try:
        if platform.system() == 'Darwin':  # macOS
            sound_file = '/System/Library/Sounds/Ping.aiff'
            subprocess.run(
                ['afplay', sound_file],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2
            )
        else:  # Linux
            sound_name = 'bell' if sound_type == 'start' else 'message'
            result = subprocess.run(
                ['canberra-gtk-play', '-i', sound_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2
            )
            if result.returncode == 0:
                return
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Fallback: терминальный bell
    try:
        print('\a', end='', flush=True)
    except Exception:
        pass
