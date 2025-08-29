import os
import sys
import tempfile
import time
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import whisper
import torch

# Добавляем родительскую директорию в PYTHONPATH для импорта common
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.schemas import TranscribeRequest, TranscribeResponse, ServerStatus
from common.audio_utils import decode_base64_to_audio

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="micPy Server", description="Speech-to-text service using Whisper")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальная модель Whisper
model = None
model_size = None
device = None

def load_whisper_model(size: str = "medium") -> None:
    global model, model_size, device
    if model_size == size and model is not None:
        return
    
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    log.info(f"Загружаем модель Whisper {size} на {device}")
    model = whisper.load_model(size, device=device)
    model_size = size
    log.info("Модель загружена успешно")

@app.on_event("startup")
async def startup_event():
    model_size_env = os.getenv("WHISPER_MODEL_SIZE", "medium")
    load_whisper_model(model_size_env)

@app.get("/status", response_model=ServerStatus)
async def get_status():
    return ServerStatus(
        status="ready" if model is not None else "loading",
        model_loaded=model is not None,
        gpu_available=torch.cuda.is_available(),
        current_model=model_size or "none"
    )

@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(request: TranscribeRequest):
    if model is None:
        raise HTTPException(status_code=503, detail="Модель не загружена")
    
    start_time = time.time()
    
    try:
        # Декодируем base64 аудио
        audio_data = decode_base64_to_audio(request.audio_data)
        
        # Создаем временный файл
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_file.write(audio_data)
            tmp_path = tmp_file.name
        
        try:
            # Загружаем модель нужного размера если отличается
            if request.model_size and request.model_size != model_size:
                load_whisper_model(request.model_size)
            
            # Транскрибируем
            result = model.transcribe(tmp_path, language=request.language)
            text = result["text"].strip()
            
            processing_time = time.time() - start_time
            log.info(f"Транскрипция завершена за {processing_time:.2f}s: {text[:50]}...")
            
            return TranscribeResponse(
                text=text,
                success=True,
                processing_time=processing_time
            )
            
        finally:
            # Удаляем временный файл
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
                
    except Exception as e:
        log.error(f"Ошибка транскрипции: {e}")
        return TranscribeResponse(
            text="",
            success=False,
            error=str(e),
            processing_time=time.time() - start_time
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)