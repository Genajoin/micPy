"""
micPy Whisper server — OpenAI-compatible STT endpoint on top of faster-whisper.

POST /v1/audio/transcriptions  (file, model, language, prompt, response_format)
GET  /health
GET  /v1/models

Настройки через переменные окружения (см. docker-compose.yml).
"""
import io
import logging
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from typing import Optional

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio

MODEL_NAME = os.getenv("WHISPER_MODEL", "large-v3-turbo")
DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE") or ("float16" if DEVICE == "cuda" else "int8")
CPU_THREADS = int(os.getenv("WHISPER_CPU_THREADS", "0"))
BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
DEFAULT_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "ru") or None
DEFAULT_PROMPT = os.getenv("WHISPER_PROMPT") or None
SAMPLE_RATE = 16000

# Фразы, которые Whisper выдумывает на тишине и шуме (наследие субтитров в обучающих данных)
HALLUCINATIONS = {
    "продолжение следует",
    "спасибо за просмотр",
    "спасибо за внимание",
    "субтитры сделал dimatorzok",
    "субтитры создавал dimatorzok",
    "редактор субтитров а синецкая корректор а егорова",
    "субтитры подогнал симон",
    "подписывайтесь на канал",
    "thank you for watching",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("micpy-whisper")

_model: Optional[WhisperModel] = None
_lock = threading.Lock()


def _norm(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", text.lower().replace("ё", "е"))
    return re.sub(r"\s+", " ", text).strip()


def _load_audio(data: bytes) -> np.ndarray:
    try:
        audio, sr = sf.read(io.BytesIO(data), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != SAMPLE_RATE:
            # Нестандартная частота — отдаём декодеру faster-whisper (ffmpeg/av с ресемплингом)
            raise ValueError(sr)
        return audio
    except Exception:
        return decode_audio(io.BytesIO(data), sampling_rate=SAMPLE_RATE)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _model
    t0 = time.time()
    log.info("Loading %s on %s (%s)", MODEL_NAME, DEVICE, COMPUTE_TYPE)
    model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE, cpu_threads=CPU_THREADS)
    # Прогрев: первый вызов инициализирует CUDA-ядра
    list(model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), language="ru")[0])
    _model = model
    log.info("Model ready in %.1fs", time.time() - t0)
    yield


app = FastAPI(title="micPy Whisper server", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {
        "status": "healthy" if _model else "loading",
        "model": MODEL_NAME,
        "device": DEVICE,
        "compute_type": COMPUTE_TYPE,
    }


@app.get("/v1/models")
def models() -> dict:
    return {"object": "list", "data": [{"id": MODEL_NAME, "object": "model", "owned_by": "micpy"}]}


@app.post("/v1/audio/transcriptions")
async def transcriptions(
    file: UploadFile = File(...),
    model: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
    response_format: str = Form("json"),
    temperature: Optional[float] = Form(None),
):
    del model, temperature  # модель одна, температуру выбирает faster-whisper (fallback-сетка)
    model_ = _model
    if model_ is None:
        raise HTTPException(503, "model is loading")

    data = await file.read()
    try:
        audio = _load_audio(data)
    except Exception as exc:
        raise HTTPException(400, f"cannot decode audio: {exc}") from exc

    duration = len(audio) / SAMPLE_RATE
    t0 = time.time()
    with _lock:
        segments, info = model_.transcribe(
            audio,
            language=language or DEFAULT_LANGUAGE,
            initial_prompt=prompt or DEFAULT_PROMPT,
            beam_size=BEAM_SIZE,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 300},
            condition_on_previous_text=False,
        )
        segments = [s for s in segments if not (s.no_speech_prob > 0.6 and s.avg_logprob < -1.0)]

    text = " ".join(s.text.strip() for s in segments).strip()
    if _norm(text) in HALLUCINATIONS:
        log.info("dropped hallucination: %r", text)
        text = ""
    log.info("transcribed %.2fs audio in %.0fms: %d chars", duration, (time.time() - t0) * 1000, len(text))

    if response_format == "text":
        return PlainTextResponse(text)
    result = {"text": text, "duration": duration}
    if response_format == "verbose_json":
        result.update(
            language=info.language,
            segments=[{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments],
        )
    return result
