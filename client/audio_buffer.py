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
import atexit
import signal
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
_KEEPALIVE_PROC = None


def _sound_settings() -> dict:
    """
    Настройки звуковых уведомлений из окружения.

    Нужны для обхода «спящего» аудиовыхода без правки системных конфигов:
    PipeWire паркует нод после 5 с тишины, а устройство (обычно HDMI на
    видеокарте) теряет первые сотни мс при пробуждении — короткий бип
    пропадает целиком. См. SOUND_DEBUGGING.md, Эксперимент 8.

    MICPY_SOUND_KEEPALIVE    1 — не давать выходу заснуть (самый надёжный обход)
    MICPY_SOUND_WARMUP_MS    тишина в начале WAV, «прогревает» устройство
    MICPY_SOUND_DURATION_MS  длительность бипа (0 — штатная: 80/120 мс)
    MICPY_SOUND_VOLUME       амплитуда 0.0–1.0 (по умолчанию 0.3)
    """
    def _num(name, default, cast):
        try:
            v = cast(os.environ.get(name, '').strip())
        except (ValueError, TypeError):
            return default
        return v if v >= 0 else default

    truthy = ('1', 'true', 'yes', 'on')
    return {
        'keepalive': os.environ.get('MICPY_SOUND_KEEPALIVE', '').strip().lower() in truthy,
        'warmup_ms': _num('MICPY_SOUND_WARMUP_MS', 0, int),
        'duration_ms': _num('MICPY_SOUND_DURATION_MS', 0, int),
        'volume': min(1.0, _num('MICPY_SOUND_VOLUME', 0.3, float)),
    }


def _clean_env() -> dict:
    """Чистое окружение для pw-play (см. SOUND_DEBUGGING.md, Эксперимент 7)."""
    return {
        'XDG_RUNTIME_DIR': f'/run/user/{os.getuid()}',
        'PATH': '/usr/bin:/bin:/usr/local/bin',
        'HOME': os.path.expanduser('~'),
        'LANG': 'en_US.UTF-8',
    }


def _get_beep_wav(sound_type: str) -> str:
    """Возвращает путь к WAV-файлу с beep-звуком (генерирует при первом вызове)."""
    cfg = _sound_settings()
    key = (sound_type, cfg['warmup_ms'], cfg['duration_ms'], cfg['volume'])
    if key in _SOUND_CACHE:
        return _SOUND_CACHE[key]

    params = {
        'start': {'freq': 600, 'duration': 0.08},
        'end': {'freq': 1200, 'duration': 0.12},
    }
    p = params.get(sound_type, params['end'])

    duration = cfg['duration_ms'] / 1000 if cfg['duration_ms'] else p['duration']
    amp = cfg['volume']
    warmup = cfg['warmup_ms'] / 1000

    # Имя файла зависит от параметров — иначе в /tmp останется старый кеш
    tag = f"_w{cfg['warmup_ms']}_d{int(duration * 1000)}_v{int(amp * 100)}"
    if key[1:] == (0, 0, 0.3):
        tag = ''
    path = os.path.join(tempfile.gettempdir(), f'micpy_{sound_type}{tag}.wav')

    if not os.path.exists(path):
        sr = 16000
        n = int(sr * duration)
        with wave.open(path, 'w') as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sr)
            fade_n = max(1, min(200, n // 4))
            frames = bytearray(b'\x00\x00' * int(sr * warmup))
            for i in range(n):
                fade = min(1.0, i / fade_n, (n - i) / fade_n)
                v = int(32767 * amp * fade * math.sin(2 * math.pi * p['freq'] * i / sr))
                frames += struct.pack('<h', v)
            f.writeframes(frames)

    _SOUND_CACHE[key] = path
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

    clean_env = _clean_env()

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


def _get_silence_wav(seconds: int = 10) -> str:
    """
    WAV с тишиной — «носитель» для keepalive-потока.

    Длительность заодно задаёт период, с которым keepalive проверяет,
    жив ли ещё родительский процесс.
    """
    path = os.path.join(tempfile.gettempdir(), f'micpy_silence_{seconds}s.wav')
    if not os.path.exists(path):
        sr = 8000
        with wave.open(path, 'w') as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sr)
            f.writeframes(b'\x00\x00' * (sr * seconds))
    return path


def start_keepalive() -> bool:
    """
    Не даёт аудиовыходу заснуть: непрерывно проигрывает тишину.

    Обход проблемы, когда PipeWire паркует нод после 5 с тишины, а устройство
    (обычно HDMI) съедает короткий бип на пробуждении. Делает то же, что
    системная настройка session.suspend-timeout-seconds=0, но из приложения
    и без правки конфигов WirePlumber.

    Включается через MICPY_SOUND_KEEPALIVE=1. Без неё — no-op.

    Returns:
        True если keepalive запущен
    """
    global _KEEPALIVE_PROC
    import logging
    logger = logging.getLogger('PlaySound')

    if not _sound_settings()['keepalive']:
        return False

    if _KEEPALIVE_PROC and _KEEPALIVE_PROC.poll() is None:
        return True

    pw_play = shutil.which('pw-play')
    if not pw_play:
        logger.warning("keepalive: pw-play not found, skipping")
        return False

    silence = _get_silence_wav()
    # Сторож по PID родителя: цикл завершится сам, даже если демон убит
    # сигналом и штатный stop_keepalive() не успел отработать (SIGTERM от
    # systemd, SIGKILL). Иначе keepalive остаётся сиротой и держит устройство.
    watchdog = f'while kill -0 {os.getpid()} 2>/dev/null; do'
    try:
        # Отдельная сессия — чтобы убить всю группу разом. Из cgroup systemd
        # процесс при этом не выходит, поэтому сиротой не останется.
        _KEEPALIVE_PROC = subprocess.Popen(
            ['bash', '-c', f'{watchdog} {pw_play} "{silence}" || sleep 1; done'],
            env=_clean_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    except Exception as e:
        logger.warning(f"keepalive failed: {e}")
        return False

    atexit.register(stop_keepalive)
    logger.info(f"keepalive started, pid={_KEEPALIVE_PROC.pid}")
    return True


def stop_keepalive():
    """Останавливает keepalive-поток (вместе с дочерним pw-play)."""
    global _KEEPALIVE_PROC
    proc, _KEEPALIVE_PROC = _KEEPALIVE_PROC, None
    if not proc or proc.poll() is not None:
        return

    try:
        # Убиваем всю группу: сам bash-цикл и запущенный им pw-play
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
