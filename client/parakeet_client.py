#!/usr/bin/env python3
"""
Клиент для Parakeet API (OpenAI-совместимый API для транскрипции).

Отправка аудио на API и получение распознанного текста.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any
import requests

logger = logging.getLogger('ParakeetClient')

DEFAULT_GLOSSARY_PATH = Path.home() / '.config' / 'micpy' / 'glossary.txt'
PROMPT_PREFIX = (
    "Это диктовка разработчика. "
    "Английские технические термины пишутся латиницей"
)
# Whisper учитывает ~223 токена подсказки (≈ 50 терминов). Точную подгонку делает
# сервер micPy, здесь лишь защита от случайно огромного файла
MAX_PROMPT_CHARS = 1500


def load_glossary(path: Optional[Path] = None) -> list[str]:
    """
    Термины из файла словаря: по одному на строку или через запятую, # — комментарий.
    """
    path = path or Path(os.environ.get('MICPY_GLOSSARY', DEFAULT_GLOSSARY_PATH)).expanduser()
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    terms = []
    for line in lines:
        line = line.split('#', 1)[0]
        terms.extend(t.strip() for t in line.split(',') if t.strip())
    return terms


def build_prompt() -> Optional[str]:
    """
    Подсказка для модели: MICPY_PROMPT целиком или префикс + термины из словаря.

    Читается при каждом запросе, чтобы правки словаря работали без перезапуска.
    """
    explicit = os.environ.get('MICPY_PROMPT', '').strip()
    if explicit:
        return explicit
    terms = load_glossary()
    if not terms:
        return None
    prompt = f"{PROMPT_PREFIX}: {', '.join(terms)}."
    if len(prompt) > MAX_PROMPT_CHARS:
        logger.warning(f"Glossary prompt truncated to {MAX_PROMPT_CHARS} chars")
        prompt = prompt[:MAX_PROMPT_CHARS].rsplit(',', 1)[0] + '.'
    return prompt


class ParakeetClient:
    """
    Клиент для работы с Parakeet API.

    Поддерживает OpenAI-совместимый протокол (/v1/audio/transcriptions).
    """

    def __init__(
        self,
        api_url: str = "http://localhost:5092/v1",
        model: str = "parakeet-tdt-0.6b-v3",
        api_key: Optional[str] = None,
        timeout: int = 120
    ):
        """
        Инициализация клиента.

        Args:
            api_url: Базовый URL API (например, http://localhost:5092/v1)
            model: Название модели
            api_key: API ключ (опционально)
            timeout: Таймаут запроса в секундах
        """
        self.api_url = api_url.rstrip('/')
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

        logger.info(f"ParakeetClient initialized: {api_url}, model: {model}")

    def _get_headers(self) -> Dict[str, str]:
        """Получение заголовков для запроса."""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def health_check(self) -> bool:
        """
        Проверка доступности API.

        Returns:
            True если API доступен
        """
        try:
            # Пытаемся получить /health
            base_url = self.api_url.rsplit('/v1', 1)[0]
            health_url = f"{base_url}/health"
            response = requests.get(health_url, timeout=5)

            if response.status_code == 200:
                return True

            # Пробуем /v1/models как fallback
            models_url = f"{self.api_url}/models"
            response = requests.get(models_url, timeout=5, headers=self._get_headers())
            return response.status_code == 200

        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False

    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav"
    ) -> Dict[str, Any]:
        """
        Транскрипция аудио через API.

        Args:
            audio_bytes: Байты аудио файла (WAV формат)
            filename: Имя файла для отправки

        Returns:
            Словарь с результатом:
            {
                "text": str,           # Распознанный текст
                "duration": float,     # Длительность (если есть)
                "success": bool,       # Успешность
                "error": str           # Ошибка (если есть)
            }
        """
        result = {
            "text": "",
            "duration": 0.0,
            "success": False,
            "error": None
        }

        try:
            url = f"{self.api_url}/audio/transcriptions"

            files = {
                'file': (filename, audio_bytes, 'audio/wav')
            }
            data = {
                'model': self.model
            }
            language = os.environ.get('MICPY_LANGUAGE', '').strip()
            if language:
                data['language'] = language
            prompt = build_prompt()
            if prompt:
                data['prompt'] = prompt

            response = requests.post(
                url,
                files=files,
                data=data,
                headers=self._get_headers(),
                timeout=self.timeout
            )

            if response.status_code != 200:
                result["error"] = f"API error {response.status_code}: {response.text[:200]}"
                logger.error(result["error"])
                return result

            api_result = response.json()

            # Нормализуем результат
            result["text"] = api_result.get("text", "")
            result["duration"] = api_result.get("duration", 0.0)
            result["success"] = True

            logger.info(f"Transcription complete: {len(result['text'])} chars")

        except requests.exceptions.Timeout:
            result["error"] = f"Request timeout ({self.timeout}s)"
            logger.error(result["error"])
        except requests.exceptions.ConnectionError as e:
            result["error"] = f"Connection failed: {str(e)[:100]}"
            logger.error(result["error"])
        except Exception as e:
            result["error"] = f"Transcription error: {str(e)[:100]}"
            logger.error(result["error"])

        return result

    def transcribe_with_retry(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        Транскрипция с повторными попытками.

        Args:
            audio_bytes: Байты аудио файла
            filename: Имя файла
            max_retries: Максимальное количество повторных попыток

        Returns:
            Результат транскрипции
        """
        last_result = None

        for attempt in range(max_retries + 1):
            result = self.transcribe(audio_bytes, filename)

            if result["success"]:
                return result

            last_result = result

            if attempt < max_retries:
                logger.info(f"Retry {attempt + 1}/{max_retries}...")
                import time
                time.sleep(1)

        return last_result or {
            "text": "",
            "duration": 0.0,
            "success": False,
            "error": "All retries failed"
        }
